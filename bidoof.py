import discord
from discord.ext import commands

import conf.settings as settings

bot = commands.Bot(
    command_prefix=settings.prefix,
    description='https://board8.fandom.com/wiki/Mafia_Bidoof'
)

for plugin in settings.plugins:
    bot.load_extension(f'plugins.{plugin}')

@bot.command()
async def reload(ctx, plugin):
    bot.reload_extension(f'plugins.{plugin}')
    await ctx.send(f'Reloaded plugin `{plugin}`.')

@bot.command()
async def shutdown(ctx):
    await ctx.send('As you wish.')
    await bot.logout()


bot.run(settings.client_token)
