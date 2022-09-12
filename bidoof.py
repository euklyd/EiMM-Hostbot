import argparse
import faulthandler
import logging
from datetime import datetime

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
    if f"plugins.{plugin}" in ctx.bot.extensions:
        ctx.bot.reload_extension(f"plugins.{plugin}")
        await ctx.send(f"Reloaded plugin `{plugin}`.")
        logging.warning(f"reloaded plugins.{plugin}")
    elif f"cogs.{plugin}" in ctx.bot.extensions:
        ctx.bot.reload_extension(f"cogs.{plugin}")
        await ctx.send(f"Reloaded cog `{plugin}`.")
        logging.warning(f"reloaded cogs.{plugin}")
    else:
        try:
            ctx.bot.load_extension(f"plugins.{plugin}")
            await ctx.send(f"Loaded plugin `{plugin}`.")
        except commands.errors.ExtensionNotFound:
            await ctx.send(f"Could not find plugin `{plugin}`.")


@commands.command()
@commands.is_owner()
async def unload(ctx: commands.Context, plugin: str):
    """
    Unload the specified plugin.
    """
    if f"plugins.{plugin}" in ctx.bot.extensions:
        ctx.bot.unload_extension(f"plugins.{plugin}")
        await ctx.send(f"Unloaded plugin `{plugin}`.")
        logging.warning(f"reloaded plugins.{plugin}")
    elif f"cogs.{plugin}" in ctx.bot.extensions:
        ctx.bot.unload_extension(f"cogs.{plugin}")
        await ctx.send(f"Unloaded cog `{plugin}`.")
        logging.warning(f"reloaded cogs.{plugin}")
    else:
        await ctx.send(f"Plugin `{plugin}` not loaded.")


@commands.command()
@commands.is_owner()
async def shutdown(ctx: commands.Context):
    """
    Zzz.
    """
    await ctx.send("I'll be back.")
    await ctx.bot.logout()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loglevel", "-l", help="log level", default="INFO")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    logging.basicConfig(level=args.loglevel, format="[%(asctime)s] %(message)s", datefmt="%Y/%m/%d %T:%M:%S")
    faulthandler.enable()

    # At least, needs: members=True, emojis=True, invites=True, messages=True, reactions=True
    # All of these but members are defaults.
    intents = discord.Intents.default()
    intents.members = True
    bot = Bot(
        command_prefix=settings.prefix,
        description="https://board8.fandom.com/wiki/Mafia_Bidoof",
        conf=settings.conf,
        activity=settings.activity,
        owner_id=settings.owner_id,
        status=settings.status,
        intents=intents,
        case_insensitive=True,  # unfortunately this doesn't help with "help <cogname>"
    )

    for cog in settings.cogs:
        bot.load_extension(f"cogs.{cog}")
        logging.warning(f"loaded cogs.{cog}")

    for plugin in settings.plugins:
        bot.load_extension(f"plugins.{plugin}")
        logging.warning(f"loaded plugins.{plugin}")

    bot.add_command(shutdown)
    bot.add_command(reload)
    bot.add_command(unload)

    print("doot")
    logging.warning("starting bot")
    bot.run(settings.client_token)
