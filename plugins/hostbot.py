import discord
from discord.ext import commands

import pprint
import yaml

from pathlib import Path

from sqlalchemy import create_engine
import hostbot_schema


@commands.command()
async def hello(ctx):
    await ctx.send('Hello {0.display_name}.'.format(ctx.author))

@commands.group(invoke_without_command=True)
async def init(ctx):
    await ctx.send("there's nothing to init!")

@init.command(name='server')
async def init_server(ctx, *, yml):
    # TODO: wip

    yml = yml.strip('```yml\n')
    ctx.guild

    for key, role in yml['roles']:
        perms = discord.Permissions()
        if key == 'host':
            perms.update({
                'manage_channels': True,
                'manage_roles': True,
                'change_nickname': True
                'manage_nicknames': True,
                'manage_messages': True,
                'mention_everyone': True,
                'mute_members': True
            })
        new_role = await ctx.guild.create_role(
            name=role['name'],
            color=role['color'],
            permissions=perms,
            hoist=True,
            reason=f'The {key} role.'
        )
        role['role'] = new_role

    for key, channel_name in yml['channels']:
        roles = yml['roles']
        overwrites = {}
        if key == 'gamechat':
            overwrites[roles['player']['role']]: discord.PermissionOverwrite(send_messages=True)
        else:
            overwrites[roles['player']['role']]: discord.PermissionOverwrite(send_messages=False)
        if key = 'graveyard':
            overwrites[roles['player']['role']]: discord.PermissionOverwrite(read_messages=False)
            overwrites[roles['dead']['role']]: discord.PermissionOverwrite(send_messages=True)
        else:
            overwrites[roles['dead']['role']]: discord.PermissionOverwrite(send_messages=False)

        new_channel = await ctx.guild.create_text_channel(
            name = channel_name
        )
    # await ctx.send(f'```json\n{pprint.pformat(yml)}```')

@init.command(name='reset')
async def init_reset(ctx):
    await ctx.send('oh shit lol')

# @init.command(name='updaterole')
# async def init_db_update(ctx, roletype, role):
#     # TODO
#
# @init.command(name='updatechannel')
# async def init_db_update(ctx, roletype, role):
#     # TODO


def setup(bot):
    bot.add_command(hello)
    bot.add_command(init)

    db_file = 'databases/hostbot.db'
    fresh = False
    if not Path(db_file).exists():
        # need to create initial tables
        fresh = True
    engine = create_engine(f'sqlite:///{db_file}')

    if fresh:
        # create the tables
