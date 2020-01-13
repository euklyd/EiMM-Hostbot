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
        print(f'reloaded {plugin}')  # TODO: change to actual logging sometime
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
    bot = Bot(
        command_prefix=settings.prefix,
        description='https://board8.fandom.com/wiki/Mafia_Bidoof',
        conf=settings.conf,
        owner_id=settings.owner_id,
        status=settings.status,
    )

    for cog in settings.cogs:
        bot.add_cog(cog(bot))

    for plugin in settings.plugins:
        bot.load_extension(f'plugins.{plugin}')

    bot.add_command(shutdown)
    bot.add_command(reload)

    bot.run(settings.client_token)
