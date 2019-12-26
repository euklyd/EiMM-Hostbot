import pprint
import re
from pathlib import Path
from typing import Callable, Union, Optional

import discord
import yaml
from discord.ext import commands
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

import plugins.hostbot_schema as hbs
from core.bot import Bot
from utils import spreadsheet

session_maker = None  # type: Union[None, Callable[[], Session]]
connection = None  # type: Optional[spreadsheet.SheetConnection]


class NotFoundMember:
    def __init__(self, name_and_discriminator: str):
        regex = r'(?P<name>.+)#(?P<disc>\d+)'
        matches = re.match(regex, name_and_discriminator)
        self.name = matches.group('name')
        self.discriminator = int(matches.group('disc'))

    def __str__(self):
        return f'{self.name}#{self.discriminator}'


@commands.group(invoke_without_command=True)
@commands.has_permissions(administrator=True)
async def init(ctx: commands.Context):
    await ctx.send(f"This isn't a command! Use `{ctx.bot.default_command_prefix}help init`.")


@init.command(name='server')
@commands.has_permissions(administrator=True)
async def init_server(ctx: commands.Context, *, yml_config):
    """
    Initialize a game server with channels and roles.

    For an example configuration, see: https://hastebin.com/cukamuveru.yml
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
        sheet=yml_config['sheet']
    )
    roles = []
    channels = []

    for key, role in yml_config['roles'].items():
        perms = discord.Permissions()
        if key == 'host':
            perms.update(**{
                'manage_channels': True,
                'manage_roles': True,
                'change_nickname': True,
                'manage_nicknames': True,
                'manage_messages': True,
                'mention_everyone': True,
                'mute_members': True
            })
        new_role = await ctx.guild.create_role(
            name=role['name'],
            color=discord.Color(role['color']),
            permissions=perms,
            hoist=True,
            reason=f'The {key} role.'
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
            overwrites[ctx.guild.default_role] = discord.PermissionOverwrite(read_messages=False, send_messages=None)
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

    session.add(server)
    session.commit()

    await ctx.send('Created channels and roles.')


def player_channel_name(player: discord.Member):
    name = player.name
    name = re.sub(r'[\W_ -]+', '', name)
    name = re.sub(r' ', '-', name)
    return f'{name}_{player.discriminator}_rolepm'


@init.command(name='rolepms')
@commands.has_permissions(administrator=True)
async def init_rolepms(ctx: commands.Context, page: str = 'Rolesheet', column: str = 'Account'):
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

    player_role_id = session.query(hbs.Role).filter_by(server_id=ctx.guild.id, type='player').one_or_none()
    player_role = ctx.guild.get_role(player_role_id.id)

    print(f'spec_role_id: {spec_role_id}')
    print(f'host_role_id: {spec_role_id}')

    sheet_name = server.sheet
    print(f'getting page {page} from sheet {sheet_name}')
    ws = connection.get_page(sheet_name, page)
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
    category = await ctx.guild.create_category('Role PMs', overwrites={
        ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        ctx.guild.me: discord.PermissionOverwrite(read_messages=True),
        host_role: discord.PermissionOverwrite(read_messages=True, manage_messages=True),
        spec_role: discord.PermissionOverwrite(read_messages=True),
    })  # type: discord.CategoryChannel

    for player in players:
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            ctx.guild.me: discord.PermissionOverwrite(read_messages=True),
            host_role: discord.PermissionOverwrite(read_messages=True, manage_messages=True),
            spec_role: discord.PermissionOverwrite(read_messages=True),
        }
        if type(player) is discord.Member:
            await player.edit(roles=player.roles + [player_role])
            # manage needed for pins
            overwrites[player] = discord.PermissionOverwrite(read_messages=True, manage_messages=True)
        topic = f"{player}'s Role PM"
        await category.create_text_channel(player_channel_name(player), overwrites=overwrites, topic=topic)

    server = session.query(hbs.Server).filter_by(id=ctx.guild.id).one_or_none()
    server.rolepms_id = category.id
    session.commit()

    if len(error_names) > 0:
        await ctx.send(error)


@init.command(name='reset')
@commands.is_owner()
async def init_reset(ctx: commands.Context):
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
            await discord_ch.delete(reason=reason)
    except discord.Forbidden:
        await ctx.send('Insufficient permissions to delete channels.')

    try:
        for role in server.roles:
            discord_role = ctx.guild.get_role(role.id)
            await discord_role.delete(reason=reason)
    except discord.Forbidden:
        await ctx.send('Insufficient permissions to delete roles.')

    if server.rolepms_id is not None:
        try:
            category = ctx.guild.get_channel(server.rolepms_id)  # type: discord.CategoryChannel
            for channel in category.channels:
                await channel.delete(reason=reason)
            await category.delete(reason=reason)
        except discord.Forbidden:
            await ctx.send('Insufficient permissions to delete Role PMs.')

    session.delete(server)
    session.commit()

    await ctx.send('Deleted, like, everything.')


# @init.command(name='updaterole')
# async def init_db_update(ctx, roletype, role):
#     # TODO
#
# @init.command(name='updatechannel')
# async def init_db_update(ctx, roletype, role):
#     # TODO


def setup(bot: Bot):
    global connection
    connection = spreadsheet.SheetConnection(bot.google_creds, bot.google_scope)

    global session_maker
    bot.add_command(init)

    db_dir = 'databases/'
    db_file = f'{db_dir}/hostbot.db'
    if not Path(db_file).exists():
        # TODO: Don't technically need this condition?
        # Adds a bit of clarity though, so keeping it in for now.
        Path(db_dir).mkdir(exist_ok=True)

    engine = create_engine(f'sqlite:///{db_file}')
    session_maker = sessionmaker(bind=engine)

    hbs.Base.metadata.create_all(engine)
