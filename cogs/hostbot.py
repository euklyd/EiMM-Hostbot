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

session_maker = None  # type: Union[None, Callable[[], Session]]
# connection = None  # type: Optional[spreadsheet.SheetConnection]

cooldown_delta = timedelta(hours=1)
cooldown_max = 2


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
                print(f'gamechat: creating {channel_name} for {key}')
            if key == 'graveyard':
                overwrites[ctx.guild.default_role] = discord.PermissionOverwrite(read_messages=False,
                                                                                 send_messages=None)
                overwrites[roles['dead']['role']] = discord.PermissionOverwrite(read_messages=True)
                overwrites[roles['host']['role']] = discord.PermissionOverwrite(read_messages=True)
                overwrites[roles['spec']['role']] = discord.PermissionOverwrite(read_messages=True)
                print(f'graveyard: creating {channel_name} for {key}')

            if key == 'music':
                overwrites[ctx.guild.default_role] = discord.PermissionOverwrite(read_messages=False)

            new_channel = await ctx.guild.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
            )
            channels.append(hbs.Channel(id=new_channel.id, type=key))
            print(f'created {channel_name} `[{key}]` with overwrites:\n{pprint.pformat(overwrites)}\n')
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

    @init.command(name='rolepms')
    @commands.has_permissions(administrator=True)
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

        print(f'spec_role_id: {spec_role_id}')
        print(f'host_role_id: {spec_role_id}')

        sheet_name = server.sheet
        print(f'getting page {page} from sheet {sheet_name}')
        ws = self.connection.get_page(sheet_name, page)
        print(ws)
        ls_usernames = spreadsheet.get_column_values(ws, column)
        print(ls_usernames)

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
            # TODO: remove test prints probably, but these are so smol that it doesn't really matter.
            print(player_roles)
            print(ctx.author.roles)
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
        msg = msg.replace('@everyone', '@\u200beveryone`').replace('@here',
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
    async def addspec(self, ctx: commands.Context, spec: discord.Member):
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

        if spec_role not in spec.roles:
            await ctx.send('Only spectators can be added to a role PM!')
            await ctx.message.add_reaction(ctx.bot.redtick)
            return

        # now we can do the actual function:
        await ctx.channel.set_permissions(spec, read_messages=True)
        await ctx.message.add_reaction(ctx.bot.greentick)

    @addspec.command(name='all')
    async def addspec_all(self, ctx: commands.Context):
        """
        Add all spectators to your Role PM.

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
