import logging
import pprint
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Union, Optional, Dict, List

import discord
import yaml
from discord.ext import commands
from sqlalchemy import create_engine, or_
from sqlalchemy.orm import sessionmaker, Session

import cogs.hostbot_schema as hbs
from core.bot import Bot
from utils import spreadsheet
import ast
import csv
from discord import File

session_maker = None  # type: Union[None, Callable[[], Session]]
# connection = None  # type: Optional[spreadsheet.SheetConnection]

cooldown_delta = timedelta(minutes=30)
cooldown_max = 3


class NotFoundMember:
    def __init__(self, name_and_discriminator: str):
        regex = r'(?P<name>.+)#(?P<disc>\d+)'
        matches = re.match(regex, name_and_discriminator)
        if matches is None:
            self.name = name_and_discriminator
            self.discriminator = '----'
        else:
            self.name = matches.group('name')
            self.discriminator = int(matches.group('disc'))

    def __str__(self):
        return f'{self.name}#{self.discriminator}'


class HostBot(commands.Cog):
    """
    Welcome to EiMM HostBot!

    This is a bit more complex than I want to explain here, instead, visit my README at:
    https://github.com/euklyd/EiMM-Hostbot/blob/master/cogs/hostbot_readme.md
    """

    def __init__(self, bot: Bot):
        self.bot = bot

        self.confessional_cooldowns = {}  # type: Dict[int, List]

        self.connection = spreadsheet.SheetConnection(bot.google_creds, bot.google_scope)

        global session_maker
        db_dir = 'databases/'
        db_file = f'{db_dir}/hostbot.db'
        if not Path(db_file).exists():
            # TODO: Don't technically need this condition?
            # Adds a bit of clarity though, so keeping it in for now.
            Path(db_dir).mkdir(exist_ok=True)

        engine = create_engine(f'sqlite:///{db_file}')
        session_maker = sessionmaker(bind=engine)

        hbs.Base.metadata.create_all(engine)

    @commands.group(invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def init(self, ctx: commands.Context):
        """
        HostBot server initialization commandgroup.
        """
        await ctx.send(f"This isn't a command! Use `{ctx.bot.default_command_prefix}help init`.")

    @init.command(name='server')
    @commands.has_permissions(administrator=True)
    async def init_server(self, ctx: commands.Context, *, yml_config: str):
        """
        Initialize a game server with channels and roles.

        For instructions and examples, see:
        https://github.com/euklyd/EiMM-Hostbot/blob/master/cogs/hostbot_readme.md
        """
        session = session_maker()
        server = session.query(hbs.Server).filter_by(id=ctx.guild.id).one_or_none()
        if server is not None:
            await ctx.send("This server has already been set up; duplicates setups aren't going to work.")
            return

        yml_config = yaml.load(yml_config.strip('```yml\n'))
        # await ctx.send(f'parsed:```json\n{pprint.pformat(yml)}```')

        server = hbs.Server(
            id=ctx.guild.id,
            name=yml_config['name'],
            sheet=yml_config['sheet'],
            addspec_on=False,
        )
        roles = []
        channels = []

        for key, role in yml_config['roles'].items():
            perms = discord.Permissions()
            mentionable = False
            if key == 'host':
                perms.update(**{
                    'manage_channels': True,
                    'manage_roles': True,
                    'change_nickname': True,
                    'manage_nicknames': True,
                    'manage_messages': True,
                    'mention_everyone': True,
                    'mute_members': True,
                })
                mentionable = True
            new_role = await ctx.guild.create_role(
                name=role['name'],
                color=discord.Color(role['color']),
                permissions=perms,
                hoist=True,
                mentionable=mentionable,
                reason=f'The {key} role.',
            )
            role['role'] = new_role
            roles.append(hbs.Role(id=new_role.id, type=key))
        server.roles = roles

        for key, channel_name in yml_config['channels'].items():
            roles = yml_config['roles']
            overwrites = {
                ctx.guild.default_role: discord.PermissionOverwrite(send_messages=False),
                roles['host']['role']: discord.PermissionOverwrite(
                    read_messages=True, send_messages=True, manage_messages=True),
            }
            if key == 'gamechat':
                overwrites[roles['player']['role']] = discord.PermissionOverwrite(send_messages=True)
                logging.info(f'gamechat: creating {channel_name} for {key}')
            if key == 'graveyard':
                overwrites[ctx.guild.default_role] = discord.PermissionOverwrite(read_messages=False,
                                                                                 send_messages=None)
                overwrites[roles['dead']['role']] = discord.PermissionOverwrite(read_messages=True)
                overwrites[roles['host']['role']] = discord.PermissionOverwrite(read_messages=True)
                overwrites[roles['spec']['role']] = discord.PermissionOverwrite(read_messages=True)
                logging.info(f'graveyard: creating {channel_name} for {key}')

            if key == 'music':
                overwrites[ctx.guild.default_role] = discord.PermissionOverwrite(read_messages=False)

            new_channel = await ctx.guild.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
            )
            channels.append(hbs.Channel(id=new_channel.id, type=key))
            logging.info(f'created {channel_name} `[{key}]` with overwrites:\n{pprint.pformat(overwrites)}\n')
        server.channels = channels

        # Turn off @everyone ping
        default_role = ctx.guild.default_role
        perms = default_role.permissions
        perms.mention_everyone = False
        await default_role.edit(permissions=perms)

        session.add(server)
        session.commit()

        await ctx.send('Created channels and roles.')

    @staticmethod
    def _player_channel_name(player: discord.Member):
        name = player.name
        name = re.sub(r'[\W_ -]+', '', name)
        name = re.sub(r' ', '-', name)
        return f'{name}-{player.discriminator:>04}'

    # NOTE: This command is essentially deprecated and people keep trying to use it. Don't use it.
    # @init.command(name='rolepms')
    # @commands.has_permissions(administrator=True)
    async def init_rolepms(self, ctx: commands.Context, page: str = 'Rolesheet', column: str = 'Account'):
        """
        Create Role PM channels for players and enrole each.

        Must be used after "init server".
        If a player is not on the server, or their name is typo'd on the sheet, will create the channel without enroling the player in the player role.
        """
        session = session_maker()

        server = session.query(hbs.Server).filter_by(id=ctx.guild.id).one_or_none()

        spec_role_id = session.query(hbs.Role).filter_by(server_id=ctx.guild.id, type='spec').one_or_none()
        spec_role = ctx.guild.get_role(spec_role_id.id)

        host_role_id = session.query(hbs.Role).filter_by(server_id=ctx.guild.id, type='host').one_or_none()
        host_role = ctx.guild.get_role(host_role_id.id)

        player_role_ids = session.query(hbs.Role).filter_by(server_id=ctx.guild.id, type='player').all()
        player_roles = [ctx.guild.get_role(role_id.id) for role_id in player_role_ids]

        logging.debug(f'spec_role_id: {spec_role_id}')
        logging.debug(f'host_role_id: {spec_role_id}')

        sheet_name = server.sheet
        logging.debug(f'getting page {page} from sheet {sheet_name}')
        ws = self.connection.get_page(sheet_name, page)
        logging.debug(ws)
        ls_usernames = spreadsheet.get_column_values(ws, column)
        logging.debug(ls_usernames)

        players = []
        error_names = []
        error = 'Error finding players: ```\n'
        for name in ls_usernames:
            player = ctx.guild.get_member_named(name)
            if player is None:
                error_names.append(name)
                error += f'{name}\n'
                players.append(NotFoundMember(name))
            else:
                players.append(player)
        error += '```_(Created channels without permissions instead.)_'

        players = sorted(players, key=lambda p: p.name.lower())
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            ctx.guild.me: discord.PermissionOverwrite(read_messages=True),
            host_role: discord.PermissionOverwrite(read_messages=True, manage_messages=True),
            # spec_role: discord.PermissionOverwrite(read_messages=True),
        }
        for player_role in player_roles:
            overwrites[player_role] = discord.PermissionOverwrite(manage_messages=True)
        category = await ctx.guild.create_category('Role PMs', overwrites=overwrites)  # type: discord.CategoryChannel

        for player in players:
            overwrites = {
                ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                ctx.guild.me: discord.PermissionOverwrite(read_messages=True),
                host_role: discord.PermissionOverwrite(read_messages=True, manage_messages=True),
                # spec_role: discord.PermissionOverwrite(read_messages=True),
            }
            for player_role in player_roles:
                overwrites[player_role] = discord.PermissionOverwrite(manage_messages=True)
            if type(player) is discord.Member:
                if len(player_roles) == 1:
                    if player_roles[0] not in player.roles:
                        await player.edit(roles=player.roles + [player_roles[0]])
                # manage needed so players can pin messages
                overwrites[player] = discord.PermissionOverwrite(read_messages=True, manage_messages=True)
            topic = f"{player}'s Role PM"
            await category.create_text_channel(HostBot._player_channel_name(player), overwrites=overwrites, topic=topic)

        server = session.query(hbs.Server).filter_by(id=ctx.guild.id).one_or_none()
        server.rolepms_id = category.id
        session.commit()

        if len(error_names) > 0:
            await ctx.send(error)

    @init.command(name='pmlist')
    @commands.has_permissions(administrator=True)
    async def init_pmlist(self, ctx: commands.Context, *, playerlist: str):
        """
        Create Role PM channels for players and enrole each, no sheet involved.

        Must be used after "init server".
        Unlike "init rolepms", passes in a linebreak-separated list as the playerlist argument.
        """
        session = session_maker()

        server = session.query(hbs.Server).filter_by(id=ctx.guild.id).one_or_none()
        if server is None:
            await ctx.send('Server is not set up')
            return

        spec_role_id = session.query(hbs.Role).filter_by(server_id=ctx.guild.id, type='spec').one_or_none()
        spec_role = ctx.guild.get_role(spec_role_id.id)

        host_role_id = session.query(hbs.Role).filter_by(server_id=ctx.guild.id, type='host').one_or_none()
        host_role = ctx.guild.get_role(host_role_id.id)

        player_role_ids = session.query(hbs.Role).filter_by(server_id=ctx.guild.id, type='player').all()
        player_roles = [ctx.guild.get_role(role_id.id) for role_id in player_role_ids]

        ls_usernames = playerlist.strip('```').strip('\n').split('\n')

        players = []
        error_names = []
        error = 'Error finding players: ```\n'
        for name in ls_usernames:
            player = ctx.guild.get_member_named(name)
            if player is None:
                error_names.append(name)
                error += f'{name}\n'
                players.append(NotFoundMember(name))
            else:
                players.append(player)
        error += '```_(Created channels without permissions instead.)_'

        players = sorted(players, key=lambda p: p.name.lower())
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            ctx.guild.me: discord.PermissionOverwrite(read_messages=True),
            host_role: discord.PermissionOverwrite(read_messages=True, manage_messages=True),
        }
        for player_role in player_roles:
            overwrites[player_role] = discord.PermissionOverwrite(manage_messages=True)
        category = await ctx.guild.create_category('Role PMs', overwrites=overwrites)  # type: discord.CategoryChannel

        for player in players:
            overwrites = {
                ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                ctx.guild.me: discord.PermissionOverwrite(read_messages=True),
                host_role: discord.PermissionOverwrite(read_messages=True, manage_messages=True),
            }
            for player_role in player_roles:
                overwrites[player_role] = discord.PermissionOverwrite(manage_messages=True)
            if type(player) is discord.Member:
                if len(player_roles) == 1:
                    if player_roles[0] not in player.roles:
                        await player.edit(roles=player.roles + [player_roles[0]])
                # manage needed for pins
                overwrites[player] = discord.PermissionOverwrite(read_messages=True, manage_messages=True)
            topic = f"{player}'s Role PM"
            await category.create_text_channel(HostBot._player_channel_name(player), overwrites=overwrites, topic=topic)

        server = session.query(hbs.Server).filter_by(id=ctx.guild.id).one_or_none()
        server.rolepms_id = category.id
        session.commit()

        if len(error_names) > 0:
            await ctx.send(error)

    @init.command(name='reset')
    @commands.is_owner()
    async def init_reset(self, ctx: commands.Context):
        """
        Delete previously created channels and roles.

        If Role PMs and Roles have been created using 'init rolepms', deletes those too.
        """
        session = session_maker()
        server = session.query(hbs.Server).filter_by(id=ctx.guild.id).one_or_none()
        if server is None:
            await ctx.send('This server has not been set up; nothing to reset.')
            return

        reason = f'Server reset by {ctx.author}'

        try:
            for channel in server.channels:
                discord_ch = ctx.guild.get_channel(channel.id)
                if discord_ch is not None:
                    await discord_ch.delete(reason=reason)
                else:
                    await ctx.send(f'Could not find {channel.type} channel.')
        except discord.Forbidden:
            await ctx.send('Insufficient permissions to delete channels.')

        try:
            for role in server.roles:
                discord_role = ctx.guild.get_role(role.id)
                if discord_role is not None:
                    await discord_role.delete(reason=reason)
                else:
                    await ctx.send(f'Could not find `{role.type}` role.')
        except discord.Forbidden:
            await ctx.send('Insufficient permissions to delete roles.')

        if server.rolepms_id is not None:
            try:
                category = ctx.guild.get_channel(server.rolepms_id)  # type: discord.CategoryChannel
                if category is not None:
                    for channel in category.channels:
                        await channel.delete(reason=reason)
                    await category.delete(reason=reason)
                else:
                    await ctx.send('Could not find Role PMs category.')
            except discord.Forbidden:
                await ctx.send('Insufficient permissions to delete Role PMs.')

        session.delete(server)
        session.commit()

        await ctx.send('Deleted, like, everything.')

    @init.command(name='setchan')
    @commands.has_permissions(administrator=True)
    async def init_setchan(self, ctx: commands.Context, channel_type: str,
                           channel: Union[discord.CategoryChannel, discord.TextChannel]):
        """
        Set the channels hostbot associates with each type.

        Valid channel types are:
        - announcements
        - flips
        - gamechat
        - graveyard
        - rolepms

        As rolepms is a category channel, it must be specified either through exact text name (case-sensitive) or channel ID snowflake.
       """
        valid_types = {'announcements', 'flips', 'gamechat', 'graveyard', 'rolepms'}

        session = session_maker()

        channel_type = channel_type.lower()
        if channel_type not in valid_types:
            await ctx.send(f'{channel_type} is not a valid channel type.')
            return

        if channel_type == 'rolepms':
            if channel.type is not discord.ChannelType.category:
                await ctx.send(f'{channel} is not a valid category channel.')
                return
            server = session.query(hbs.Server).filter_by(id=ctx.guild.id).one_or_none()
            server.rolepms_id = channel.id
        else:
            if channel.type is not discord.ChannelType.text:
                await ctx.send(f'{channel} is not a valid text channel.')
                return
            channel_row = session.query(hbs.Channel).filter_by(server_id=ctx.guild.id, type=channel_type).one_or_none()
            channel_row.id = channel.id

        session.commit()
        await ctx.message.add_reaction(ctx.bot.greentick)

    # @init.command(name='setrole')
    # async def init_setchan(self, ctx: commands.Context, role_type: str, role: discord.Role):
    #     ...

    @init.command(name='status')
    async def init_status(self, ctx: commands.Context):
        """
        List game server info and number of people in each game-related role.
        """
        session = session_maker()
        server = session.query(hbs.Server).filter_by(id=ctx.guild.id).one_or_none()

        spec_role_id = session.query(hbs.Role).filter_by(server_id=ctx.guild.id, type='spec').one_or_none()
        host_role_id = session.query(hbs.Role).filter_by(server_id=ctx.guild.id, type='host').one_or_none()
        player_role_ids = session.query(hbs.Role).filter_by(server_id=ctx.guild.id, type='player').all()
        dead_role_id = session.query(hbs.Role).filter_by(server_id=ctx.guild.id, type='dead').one_or_none()

        spec_role = ctx.guild.get_role(spec_role_id.id)
        host_role = ctx.guild.get_role(host_role_id.id)
        player_roles = [ctx.guild.get_role(role_id.id) for role_id in player_role_ids]
        dead_role = ctx.guild.get_role(dead_role_id.id)

        em = discord.Embed(title=server.name, color=host_role.color)
        em.set_thumbnail(url=ctx.guild.icon_url)
        em.add_field(name=f'{host_role} (Hosts)', value=f'{len(host_role.members)}', inline=False)
        for player_role in player_roles:
            em.add_field(name=f'{player_role} (Players)', value=f'{len(player_role.members)}')
        em.add_field(name=f'{spec_role} (Specs)', value=f'{len(spec_role.members)}', inline=False)
        em.add_field(name=f'{dead_role} (Dead)', value=f'{len(dead_role.members)}', inline=False)

        announcements_chan = session.query(hbs.Channel).filter_by(server_id=ctx.guild.id,
                                                                  type='announcements').one_or_none()
        flips_chan = session.query(hbs.Channel).filter_by(server_id=ctx.guild.id, type='flips').one_or_none()
        gamechat_chan = session.query(hbs.Channel).filter_by(server_id=ctx.guild.id, type='gamechat').one_or_none()
        graveyard_chan = session.query(hbs.Channel).filter_by(server_id=ctx.guild.id, type='gamechat').one_or_none()

        em.add_field(name='Announcements', value=f'{ctx.guild.get_channel(announcements_chan.id)}')
        em.add_field(name='Flips', value=f'{ctx.guild.get_channel(flips_chan.id)}')
        em.add_field(name='Gamechat', value=f'{ctx.guild.get_channel(gamechat_chan.id)}')
        em.add_field(name='Graveyard', value=f'{ctx.guild.get_channel(graveyard_chan.id)}')
        em.add_field(name='Role PMs category', value=f'{ctx.guild.get_channel(server.rolepms_id)}')

        await ctx.send(embed=em)

    def _inc_cooldown(self, user: discord.Member):
        if user.id not in self.confessional_cooldowns:
            self.confessional_cooldowns[user.id] = [datetime.utcnow()]
            return True

        if len(self.confessional_cooldowns[user.id]) < cooldown_max:
            self.confessional_cooldowns[user.id].append(datetime.utcnow())
            return True

        if self.confessional_cooldowns[user.id][0] + cooldown_delta > datetime.utcnow():
            return False
        self.confessional_cooldowns[user.id].pop(0)
        self.confessional_cooldowns[user.id].append(datetime.utcnow())
        return True

    @commands.command()
    @commands.guild_only()
    async def confessional(self, ctx: commands.Context, *, msg):
        """
        Send a confessional from your Role PM to the graveyard.

        Only usable by living players, and only in their Role PMs. Has a cooldown timer, so don't spam it.
        """
        session = session_maker()
        # This should never have multiple roles in it, unless I'm manually overriding something for a game,
        # in which case, that is important to be able to support!
        player_roles = session.query(hbs.Role).filter_by(type='player', server_id=ctx.guild.id).all()
        if len(player_roles) == 0:
            await ctx.send("This server isn't set up for EiMM.")
            await ctx.message.add_reaction(ctx.bot.redtick)
            return
        player_roles = [ctx.guild.get_role(player_role.id) for player_role in player_roles]
        found = False
        for player_role in player_roles:
            if player_role in ctx.author.roles:
                found = True
                break
        if not found:
            logging.debug(player_roles)
            logging.debug(ctx.author.roles)
            await ctx.send('This command is only usable by living players.')
            await ctx.message.add_reaction(ctx.bot.redtick)
            return

        gamechat_channel = session.query(hbs.Channel).filter_by(type='gamechat', server_id=ctx.guild.id).one_or_none()
        if ctx.channel.id == gamechat_channel.id:
            await ctx.send('Confessionals belong in your role PM.')
            await ctx.message.add_reaction(ctx.bot.redtick)
            return

        if self._inc_cooldown(ctx.author) is False:
            time_til_next = cooldown_delta - (datetime.utcnow() - self.confessional_cooldowns[ctx.author.id][0])
            hours, rem = divmod(time_til_next.seconds, 3600)
            mins, secs = divmod(time_til_next.seconds, 60)
            await ctx.send(f'Stop sending confessionals so fast!\n'
                           f'*(Max {cooldown_max} per {cooldown_delta}; {hours}:{mins:02}:{secs:02} to go.)*')
            await ctx.message.add_reaction(ctx.bot.redtick)
            return

        if len(msg) > 1900:
            await ctx.send('Your confessional is too long! Please keep it below 1900 characters.')
            await ctx.message.add_reaction(ctx.bot.redtick)
            return
        gy_channel = session.query(hbs.Channel).filter_by(type='graveyard', server_id=ctx.guild.id).one_or_none()
        gy_channel = ctx.guild.get_channel(gy_channel.id)  # type: discord.TextChannel
        msg = msg.replace('@everyone', '@\u200beveryone').replace('@here',
                                                                  '@\u200bhere')  # \u200b aka zero-width space
        conf = f'**Confessional from {ctx.author}:**\n>>> {msg}'
        await gy_channel.send(conf)
        await ctx.message.add_reaction(ctx.bot.greentick)

    @commands.command()
    @commands.guild_only()
    async def gameavatars(self, ctx: commands.Context):
        """
        List all avatar URLs for all players and hosts.
        """
        session = session_maker()
        player_role_rows = session.query(hbs.Role).filter_by(type='player', server_id=ctx.guild.id).all()
        host_role = session.query(hbs.Role).filter_by(type='host', server_id=ctx.guild.id).one_or_none()
        gamechat_channel = session.query(hbs.Channel).filter_by(type='gamechat', server_id=ctx.guild.id).one_or_none()
        if host_role is None or gamechat_channel is None or player_role_rows is None or len(player_role_rows) == 0:
            await ctx.send("This server isn't set up for EiMM.")
            await ctx.message.add_reaction(ctx.bot.redtick)
            return

        if ctx.channel.id == gamechat_channel.id:
            await ctx.send("Don't spam up gamechat with this, thanks.")
            await ctx.message.add_reaction(ctx.bot.redtick)
            return

        player_roles = []  # type: List[discord.Role]
        for row in player_role_rows:
            player_roles.append(ctx.guild.get_role(row.id))
        host_role = ctx.guild.get_role(host_role.id)  # type: discord.Role
        replies = []
        reply = '**Host avatars:**```\n'
        for host in sorted(host_role.members, key=lambda x: x.name.lower()):  # type: discord.Member
            if len(reply) > 1800:
                replies.append(reply + '```')
                reply = '```\n'
            reply += f'{host}: {host.avatar_url_as(static_format="png")}\n'
        if len(host_role.members) == 0:
            reply += ' '
        reply += '```**Player avatars:**```\n'
        for player_role in player_roles:
            for player in sorted(player_role.members, key=lambda x: x.name.lower()):  # type: discord.Member
                if len(reply) > 1800:
                    replies.append(reply + '```')
                    reply = '```\n'
                reply += f'{player}: {player.avatar_url_as(static_format="png")}\n'
        reply += '```'
        replies.append(reply)

        for r in replies:
            await ctx.send(r)

    @commands.command()
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def enrole(self, ctx: commands.Context, role: discord.Role, mentions: commands.Greedy[discord.Member]):
        """
        Add members to a role en masse.
        """
        for member in mentions:
            await member.edit(roles=member.roles + [role])
        await ctx.message.add_reaction(ctx.bot.greentick)

    @commands.group(invoke_without_command=True)
    async def addspec(self, ctx: commands.Context, specs: commands.Greedy[discord.Member]):
        """
        Add a spectator to your Role PM.

        Usable by players and hosts, and only from your Role PM channel.
        """
        session = session_maker()

        server = session.query(hbs.Server).filter_by(id=ctx.guild.id).one_or_none()
        if not server:
            await ctx.send("This server isn't a game server.")
            await ctx.message.add_reaction(ctx.bot.redtick)
            return
        elif server.addspec_on is False:
            await ctx.send("Adding specs to channels isn't enabled on this server.")
            await ctx.message.add_reaction(ctx.bot.redtick)
            return
        elif ctx.channel.category.id != server.rolepms_id:
            await ctx.send("This isn't a Role PM channel.")
            await ctx.message.add_reaction(ctx.bot.redtick)
            return

        allowed_role_ids = session.query(hbs.Role).filter(hbs.Role.server_id == ctx.guild.id,
                                                          or_(hbs.Role.type == 'player', hbs.Role.type == 'host')).all()
        allowed_roles = [ctx.guild.get_role(role_id.id) for role_id in allowed_role_ids]

        # check if author has any of the player/host roles
        if set(allowed_roles).isdisjoint(set(ctx.author.roles)):
            await ctx.send('Only players and hosts can add spectators to a role PM.')
            await ctx.message.add_reaction(ctx.bot.redtick)
            return

        spec_role_id = session.query(hbs.Role).filter_by(server_id=ctx.guild.id, type='spec').one_or_none()
        spec_role = ctx.guild.get_role(spec_role_id.id)

        badspecs = []
        for spec in specs:
            if spec_role not in spec.roles:
                badspecs.append(spec)
                await ctx.message.add_reaction(ctx.bot.redtick)
                continue

            # now we can do the actual function:
            await ctx.channel.set_permissions(spec, read_messages=True)
            await ctx.message.add_reaction(ctx.bot.greentick)

        if badspecs:
            badspec_msg = ', '.join([str(spec) for spec in badspecs])
            await ctx.send(f'Failed to add {badspec_msg}: only spectators can be added to a role PM!')

    @addspec.command(name='all')
    async def addspec_all(self, ctx: commands.Context):
        """
        Add all spectators to your Role PM.

        Usable by players and hosts, and only from your Role PM channel. @mention a user, or provide their full Discord username or server nick exactly (case-sensitive). If it's multiple words, "use quotes".
        """
        session = session_maker()

        server = session.query(hbs.Server).filter_by(id=ctx.guild.id).one_or_none()
        if not server:
            await ctx.send("This server isn't a game server.")
            await ctx.message.add_reaction(ctx.bot.redtick)
            return
        elif server.addspec_on is False:
            await ctx.send("Adding specs to channels isn't enabled on this server.")
            await ctx.message.add_reaction(ctx.bot.redtick)
            return
        elif ctx.channel.category.id != server.rolepms_id:
            await ctx.send("This isn't a Role PM channel.")
            await ctx.message.add_reaction(ctx.bot.redtick)
            return

        # player_role_ids = session.query(hbs.Role).filter_by(server_id=ctx.guild.id, type='player').all()
        # player_roles = [ctx.guild.get_role(role_id.id) for role_id in player_role_ids]
        #
        # # check if author has any of the player roles
        # if set(player_roles).isdisjoint(set(ctx.author.roles)):
        #     await ctx.send()  # TODO: error message
        #     return

        allowed_role_ids = session.query(hbs.Role).filter(hbs.Role.server_id == ctx.guild.id and
                                                          (hbs.Role.type == 'player' or hbs.Role.type == 'host')).all()
        allowed_roles = [ctx.guild.get_role(role_id.id) for role_id in allowed_role_ids]

        # check if author has any of the player/host roles
        if set(allowed_roles).isdisjoint(set(ctx.author.roles)):
            await ctx.send('Only players and hosts can add spectators to a role PM.')
            await ctx.message.add_reaction(ctx.bot.redtick)
            return

        spec_role_id = session.query(hbs.Role).filter_by(server_id=ctx.guild.id, type='spec').one_or_none()
        spec_role = ctx.guild.get_role(spec_role_id.id)

        # now we can do the actual function:
        # await ctx.channel.edit(overwrites={spec_role: discord.PermissionOverwrite(read_messages=True)})
        await ctx.channel.set_permissions(spec_role, read_messages=True)
        await ctx.message.add_reaction(ctx.bot.greentick)

    @addspec.command(name='rm')
    async def addspec_rm(self, ctx: commands.Context, spec: discord.Member):
        """
        Remove a spectator from your role PM.

        Usable by players and hosts, and only from your Role PM channel.
        """
        session = session_maker()

        server = session.query(hbs.Server).filter_by(id=ctx.guild.id).one_or_none()
        if not server:
            await ctx.send("This server isn't a game server.")
            await ctx.message.add_reaction(ctx.bot.redtick)
            return
        elif server.addspec_on is False:
            await ctx.send("Adding specs to channels isn't enabled on this server.")
            await ctx.message.add_reaction(ctx.bot.redtick)
            return
        elif ctx.channel.category.id != server.rolepms_id:
            await ctx.send("This isn't a Role PM channel.")
            await ctx.message.add_reaction(ctx.bot.redtick)
            return

        allowed_role_ids = session.query(hbs.Role).filter(hbs.Role.server_id == ctx.guild.id,
                                                          or_(hbs.Role.type == 'player', hbs.Role.type == 'host')).all()
        allowed_roles = [ctx.guild.get_role(role_id.id) for role_id in allowed_role_ids]

        # check if author has any of the player/host roles
        if set(allowed_roles).isdisjoint(set(ctx.author.roles)):
            await ctx.send('Only players and hosts can remove spectators from a role PM.')
            await ctx.message.add_reaction(ctx.bot.redtick)
            return

        spec_role_id = session.query(hbs.Role).filter_by(server_id=ctx.guild.id, type='spec').one_or_none()
        spec_role = ctx.guild.get_role(spec_role_id.id)

        if spec_role not in spec.roles:
            await ctx.send('Only spectators can be removed from a role PM!')
            await ctx.message.add_reaction(ctx.bot.redtick)
            return

        # now we can do the actual function:
        await ctx.channel.set_permissions(spec, read_messages=False)
        await ctx.message.add_reaction(ctx.bot.greentick)

    @addspec.command(name='off')
    async def addspec_off(self, ctx: commands.Context):
        """
        Disables players from being able to add spectators to their Role PMs.

        Usable by hosts only.
        """
        session = session_maker()

        server = session.query(hbs.Server).filter_by(id=ctx.guild.id).one_or_none()
        if not server:
            await ctx.send("This server isn't a game server.")
            await ctx.message.add_reaction(ctx.bot.redtick)
            return

        host_role_id = session.query(hbs.Role).filter_by(server_id=ctx.guild.id, type='host').one_or_none()
        host_role = ctx.guild.get_role(host_role_id.id)
        if host_role not in ctx.author.roles:
            await ctx.send('Only hosts can toggle this setting.')
            await ctx.message.add_reaction(ctx.bot.redtick)
            return

        server.addspec_on = False
        session.commit()

        await ctx.message.add_reaction(ctx.bot.greentick)

    @addspec.command(name='on')
    async def addspec_on(self, ctx: commands.Context):
        """
        Enables players to add spectators to their Role PMs.

        Usable by hosts only.
        """
        session = session_maker()

        server = session.query(hbs.Server).filter_by(id=ctx.guild.id).one_or_none()
        if not server:
            await ctx.send("This server isn't a game server.")
            await ctx.message.add_reaction(ctx.bot.redtick)
            return

        host_role_id = session.query(hbs.Role).filter_by(server_id=ctx.guild.id, type='host').one_or_none()
        host_role = ctx.guild.get_role(host_role_id.id)
        if host_role not in ctx.author.roles:
            await ctx.send('Only hosts can toggle this setting.')
            await ctx.message.add_reaction(ctx.bot.redtick)
            return

        server.addspec_on = True
        session.commit()

        await ctx.message.add_reaction(ctx.bot.greentick)

    @commands.command()
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def resolve(self, ctx: commands.Context, *, night: int):
        big_sheet_name = 'Formido Oppugnatura Exsequens'

        role_pm_category = discord.utils.get(ctx.guild.categories, name="Role PMs")
        current_night_name = "N1"
        # Columns are as follows
        # A:# B:Temp C:Ninja D:Player E:Alias F,G,H: Max,Hp,MT I:Action Name J:Priority K:B/H/N L:Description M:Notes N:Input O:Output
        if night == 1:
            # First night, nothing fancy, just check for valid alias
            current_night_sheet = self.connection.get_page(big_sheet_name, current_night_name)
        else:
            prev_night = night - 1
            previous_night_name = "N" + str(prev_night)
            current_night_name = "N" + str(night)
            prev_night_sheet = self.connection.get_page(big_sheet_name, previous_night_name)
            current_night_sheet = self.connection.get_page(big_sheet_name, current_night_name)

        self.current_night_actions_dict = current_night_sheet.get_all_records()
        self.last_night_action_dict = None
        if night != 1:
            #read last night's actions
            self.last_night_action_dict = prev_night_sheet.get_all_records()

        values_list = current_night_sheet.col_values(4)
        values_list = [item.lower() for item in values_list]

        for channel in ctx.guild.channels:
            if channel in role_pm_category.channels:
                #Role PM channel - use channel name to find discord player
                channel_name = channel.name
                user_name_list = channel_name.split("-")
                username = ""
                for x in user_name_list[:-1]:
                    username+=x
                username = username + "#" + user_name_list[-1]

                actions = ""
                actions_found = False
                # Find their username in the sheet
                if username in values_list:
                    # Check if the alias for their actions are valid
                    # Find their action submission
                    pins = await channel.pins()
                    for message in pins:
                        str_match = "Night " + str(night)
                        if str_match in message.content:
                            actions_found = True
                            actions = message.content
                            break
                    if actions_found:
                        # Read last night actions from player
                        self.last_night_actions = None
                        await self.read_last_nights_actions(ctx, username)
                        # Action message found
                        await self.write_action(ctx, actions, username)

                        if night != 1:
                            for row in self.list_of_dicts:
                                if row['Player'] == username:
                                    # player found, load prev night actions
                                    action_name = row['Action Name']
                                    target = row['Output']
                                    self.last_night_actions[action_name] = target
                            print(self.last_night_actions)
                        #Otherwise, no consect issues, actions are OK
                        else:
                            pass
                            #await ctx.send("{} Actions valid placeholder".format(username))

                    else:
                        await ctx.send("No actions found by {}".format(username))

        keys = self.current_night_actions_dict[0].keys()
        with open('foee_output.csv', 'w', newline='') as output_file:
            dict_writer = csv.DictWriter(output_file, keys)
            dict_writer.writeheader()
            dict_writer.writerows(self.current_night_actions_dict)
        await ctx.channel.send('***Output File***', file=File('foee_output.csv'))

    async def read_last_nights_actions(self, ctx, username):
        if self.last_night_action_dict is not None:
            for row in self.last_night_action_dict:
                if row['Player'] == username:
                    # player found, load prev night actions
                    action_name = row['Action Name']
                    target = row['Output']
                    self.last_night_actions[action_name] = target
            print(self.last_night_actions)

    async def write_action(self, ctx, actions, username):
        # self.list_of_dicts
        self.submitted_actions = {}
        # Split action string up with new line
        actions_list = actions.split("\n")
        for action in actions_list:
            a = action.split(":")
            # Action has no :, invalid action
            if len(a) == 1:
                pass
            elif len(a) > 1:
                action_name = a[0]
                targets = a[1:]
                #Strip BS spaces from the start
                targets = [s.strip() for s in targets]
                self.submitted_actions[action_name] = targets

        for row in self.current_night_actions_dict:
            if row['Player'].lower() == username:
                # player found, write actions in
                # Check if actions are valid
                for action_name, target_alias in self.submitted_actions.items():
                    if action_name.casefold() in row['Action Name'].casefold():
                        actual_full_action_name = row['Action Name']
                        # TODO: Check input alias is actually an alias
                        check = False
                        for alias in target_alias:
                            if alias in self.alias_list:
                                check = True
                            else:
                                check = False
                                break
                        if not check:
                            await ctx.send("Action {} invalid because {} not in alias list".format(action_name, target_alias))
                        else:
                            # Is there last night info?
                            if self.last_night_actions is not None:
                                # Check if single target
                                if isinstance(target_alias, list) and len(target_alias) == 1:
                                    # Check if alias is a consecutive target or not.
                                    target_alias = target_alias[0]
                                    if target_alias != self.last_night_actions[actual_full_action_name] or actual_full_action_name=="Standard Shot":
                                        row['Input'] = target_alias
                                        # Clear it
                                        self.submitted_actions[action_name] = ""
                                    else:
                                        await ctx.send("Action {} invalid because of consect target on alias {}".format(action_name, target_alias))
                                elif isinstance(target_alias, list) and len(target_alias) > 1:
                                    #multi target, ensure last night actions was multitarget too, otherwise prob failed
                                    if len(self.last_night_actions[actual_full_action_name])>1:
                                        set1 = set(target_alias)
                                        list2 = ast.literal_eval(self.last_night_actions[actual_full_action_name])
                                        set2 = set(list2)
                                        consect = set1 & set2
                                        if len(consect) > 0:
                                            await ctx.send("Action {} invalid because of consect target on alias {}".format(action_name,
                                                                                                                   consect))
                            # Actions are ok, write in actions
                            else:
                                row['Input'] = target_alias
                                # Clear it
                                self.submitted_actions[action_name] = ""

    @commands.command()
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def update_alias_list(self, ctx: commands.Context, *, msg):
        '''Pass it new line seperated list of aliases for that night'''
        self.alias_list = msg.split("\n")
        await ctx.send(self.alias_list)

    # TODO: all of these
    # @commands.group(invoke_without_command=True)
    # @commands.has_permissions(administrator=True)
    # async def phase(self, ctx: commands.Context):
    #     """
    #     Pause/unpause phase.
    #     """
    #     pass
    #
    # @phase.command(name='pause')
    # @commands.has_permissions(administrator=True)
    # async def phase_pause(self, ctx: commands.Context):
    #     """
    #     Lock the gamechat channel.
    #
    #     Only works in a single gamechat channel.
    #     """
    #     ...
    #
    # @phase.command(name='unpause')
    # @commands.has_permissions(administrator=True)
    # async def phase_unpause(self, ctx: commands.Context):
    #     """
    #     Unlock the gamechat channel.
    #     """
    #     session = session_maker()
    #     gamechat_channel = session.query(hbs.Channel).filter_by(type='gamechat', server_id=ctx.guild.id).one_or_none()
    #     gamechat = ctx.guild.get_channel(gamechat_channel.id)
    #
    #     ...


# @init.command(name='updaterole')
# async def init_db_update(ctx, roletype, role):
#     # TODO
#
# @init.command(name='updatechannel')
# async def init_db_update(ctx, roletype, role):
#     # TODO


def setup(bot: Bot):
    # global connection
    # connection = spreadsheet.SheetConnection(bot.google_creds, bot.google_scope)
    #
    # global session_maker
    # bot.add_command(init)
    # bot.add_command(confessional)
    # bot.add_command(gameavatars)
    # bot.add_command(enrole)
    bot.add_cog(HostBot(bot))

    # db_dir = 'databases/'
    # db_file = f'{db_dir}/hostbot.db'
    # if not Path(db_file).exists():
    #     # TODO: Don't technically need this condition?
    #     # Adds a bit of clarity though, so keeping it in for now.
    #     Path(db_dir).mkdir(exist_ok=True)
    #
    # engine = create_engine(f'sqlite:///{db_file}')
    # session_maker = sessionmaker(bind=engine)
    #
    # hbs.Base.metadata.create_all(engine)
