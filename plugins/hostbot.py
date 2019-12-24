import pprint
import re
from pathlib import Path
from typing import Callable, Union

import discord
import yaml
from discord.ext import commands
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

import plugins.hostbot_schema as hbs

session_maker = None  # type: Union[None, Callable[[], Session]]


@commands.group(invoke_without_command=True)
@commands.has_permissions(administrator=True)
async def init(ctx: commands.Context):
    await ctx.send("there's nothing to init!")


@init.command(name='server')
@commands.has_permissions(administrator=True)
async def init_server(ctx: commands.Context, *, yml):
    session = session_maker()

    yml = yaml.load(yml.strip('```yml\n'))
    # await ctx.send(f'parsed:```json\n{pprint.pformat(yml)}```')

    server = hbs.Server(
        id=ctx.guild.id,
        name=yml['name'],
        sheet=yml['sheet']
    )
    roles = []
    channels = []

    for key, role in yml['roles'].items():
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

    for key, channel_name in yml['channels'].items():
        roles = yml['roles']
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
            # overwrites[roles['player']['role']] = discord.PermissionOverwrite(read_messages=False)
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
        # pprint.pprint(f'created {channel_name} `[{key}]` with overwrites:\n{overwrites}\n')
        print(f'created {channel_name} `[{key}]` with overwrites:\n{pprint.pformat(overwrites)}\n')
    server.channels = channels

    session.add(server)
    session.commit()

    await ctx.send('created a bunch of things')


def player_channel_name(player: discord.Member):
    name = player.name
    name = re.sub(r'[\W_ -]+', '', name)
    name = re.sub(r' ', '-', name)
    return f'{name}_{player.discriminator}'


@init.command(name='rolepms')
@commands.has_permissions(administrator=True)
async def init_rolepms(ctx: commands.Context):
    # ls_usernames = get_from_sheet()  # TODO

    session = session_maker()
    spec_role_id = session.query(hbs.Role).filter_by(server_id=ctx.guild.id, type='spec').one_or_none()
    spec_role = ctx.guild.get_role(spec_role_id.id)

    host_role_id = session.query(hbs.Role).filter_by(server_id=ctx.guild.id, type='host').one_or_none()
    host_role = ctx.guild.get_role(host_role_id.id)

    player_role_id = session.query(hbs.Role).filter_by(server_id=ctx.guild.id, type='player').one_or_none()
    player_role = ctx.guild.get_role(player_role_id.id)

    print(f'spec_role_id: {spec_role_id}')
    print(f'host_role_id: {spec_role_id}')

    ls_usernames = [
        'BT#4881',
        'Kim#9000',
        'Monde#6197',
    ]

    players = []
    error_names = []
    error = 'Error finding players: ```\n'
    for name in ls_usernames:
        player = ctx.guild.get_member_named(name)
        if player is None:
            error_names.append(name)
            error += f'{name}\n'
        else:
            players.append(player)
    error += '```'

    players = sorted(players, key=lambda p: p.name.lower())
    category = await ctx.guild.create_category('Role PMs', overwrites={
        ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        ctx.guild.me: discord.PermissionOverwrite(read_messages=True),
        host_role: discord.PermissionOverwrite(read_messages=True, manage_messages=True),
        spec_role: discord.PermissionOverwrite(read_messages=True),
    })  # type: discord.CategoryChannel
    for player in players:
        await player.edit(roles=player.roles + [player_role])
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            ctx.guild.me: discord.PermissionOverwrite(read_messages=True),
            player: discord.PermissionOverwrite(read_messages=True, manage_messages=True),  # manage needed for pins
            host_role: discord.PermissionOverwrite(read_messages=True, manage_messages=True),
            spec_role: discord.PermissionOverwrite(read_messages=True),
        }
        topic = f"{player}'s Role PM"
        await category.create_text_channel(player_channel_name(player), overwrites=overwrites, topic=topic)

    server = session.query(hbs.Server).filter_by(id=ctx.guild.id).one_or_none()
    # server.rolepms = hbs.RolePMs(id=category.id, server_id=ctx.guild.id)
    server.rolepms_id = category.id
    session.commit()
    # TODO: save category

    if len(error_names) > 0:
        await ctx.send(error)


@init.command(name='reset')
@commands.is_owner()
async def init_reset(ctx: commands.Context):
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

    await ctx.send('i deleted ur stuffz')


# @init.command(name='updaterole')
# async def init_db_update(ctx, roletype, role):
#     # TODO
#
# @init.command(name='updatechannel')
# async def init_db_update(ctx, roletype, role):
#     # TODO


def setup(bot: commands.Bot):
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
