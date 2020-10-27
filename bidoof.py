import discord
from discord.ext import commands

import conf.settings as settings
from core.bot import Bot


@commands.command()
@commands.is_owner()
async def reload(ctx: commands.Context, plugin: str):
    """
    Reload the specified plugin.

    If it is not loaded yet, load it. Only works for plugins (extensions), NOT cogs.
    """
    if f'plugins.{plugin}' in ctx.bot.extensions:
        ctx.bot.reload_extension(f'plugins.{plugin}')
        await ctx.send(f'Reloaded plugin `{plugin}`.')
        print(f'reloaded plugins.{plugin}')  # TODO: change to actual logging sometime
    elif f'cogs.{plugin}' in ctx.bot.extensions:
        ctx.bot.reload_extension(f'cogs.{plugin}')
        await ctx.send(f'Reloaded cog `{plugin}`.')
        print(f'reloaded cogs.{plugin}')  # TODO: change to actual logging sometime
    else:
        ctx.bot.load_extension(f'plugins.{plugin}')
        await ctx.send(f'Loaded plugin `{plugin}`.')


@commands.command()
@commands.is_owner()
async def shutdown(ctx: commands.Context):
    """
    Zzz.
    """
    await ctx.send("I'll be back.")
    await ctx.bot.logout()


if __name__ == '__main__':
    # At least, needs: members=True, emojis=True, invites=True, messages=True, reactions=True
    # All of these but members are defaults.
    intents = discord.Intents.default()
    intents.members = True
    bot = Bot(
        command_prefix=settings.prefix,
        description='https://board8.fandom.com/wiki/Mafia_Bidoof',
        conf=settings.conf,
        owner_id=settings.owner_id,
        status=settings.status,
        intents=intents,
    )

    for cog in settings.cogs:
        bot.load_extension(f'cogs.{cog}')

    for plugin in settings.plugins:
        bot.load_extension(f'plugins.{plugin}')

    bot.add_command(shutdown)
    bot.add_command(reload)

    print("starting bot")
    bot.run(settings.client_token)
