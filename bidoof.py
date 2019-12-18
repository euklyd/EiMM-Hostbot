import discord
from discord.ext import commands

import conf.settings as settings

from core.bot import Bot

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


@bot.command()
@commands.is_owner()
async def reload(ctx, plugin):
    bot.reload_extension(f'plugins.{plugin}')
    await ctx.send(f'Reloaded plugin `{plugin}`.')
    print(f'reloaded {plugin}')  # TODO: change to actual logging sometime


@bot.command()
@commands.is_owner()
async def shutdown(ctx):
    await ctx.send("I'll be back.")
    await bot.logout()


bot.run(settings.client_token)
