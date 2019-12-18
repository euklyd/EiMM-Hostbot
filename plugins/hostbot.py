from typing import Callable, Union

import discord
from discord.ext import commands

import pprint
import yaml

from pathlib import Path

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
        overwrites = {}
        if key == 'gamechat':
            overwrites[roles['player']['role']]: discord.PermissionOverwrite(send_messages=True)
        else:
            overwrites[roles['player']['role']]: discord.PermissionOverwrite(send_messages=False)
        if key == 'graveyard':
            overwrites[roles['player']['role']]: discord.PermissionOverwrite(read_messages=False)
            overwrites[roles['dead']['role']]: discord.PermissionOverwrite(send_messages=True)
        else:
            overwrites[roles['dead']['role']]: discord.PermissionOverwrite(send_messages=False)

        new_channel = await ctx.guild.create_text_channel(
            name=channel_name,
            overwrites=overwrites
        )
        channels.append(hbs.Channel(id=new_channel.id, type=key))
    server.channels = channels

    session.add(server)
    session.commit()

    await ctx.send('created a bunch of things')


@init.command(name='reset')
@commands.has_permissions(administrator=True)
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
    bot.add_command(hello)
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
