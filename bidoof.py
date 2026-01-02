import argparse
import asyncio
import faulthandler
import logging
import signal

import discord
from discord.ext import commands

import conf.settings as settings
from core.bot import Bot


@commands.command()
@commands.is_owner()
async def reload(ctx: commands.Context, extension: str) -> None:
    """
    Reload the specified extension.

    If it is not loaded yet, load it.
    """
    if f"cogs.{extension}" in ctx.bot.extensions:
        await ctx.bot.reload_extension(f"cogs.{extension}")
        await ctx.send(f"Reloaded extension `{extension}`.")
        logging.warning(f"reloaded cogs.{extension}")
    else:
        try:
            await ctx.bot.load_extension(f"cogs.{extension}")
            await ctx.send(f"Loaded extension `{extension}`.")
        except commands.errors.ExtensionNotFound:
            await ctx.send(f"Could not find extension `{extension}`.")


@commands.command()
@commands.is_owner()
async def unload(ctx: commands.Context, extension: str) -> None:
    """
    Unload the specified extension.
    """
    if f"cogs.{extension}" in ctx.bot.extensions:
        await ctx.bot.unload_extension(f"cogs.{extension}")
        await ctx.send(f"Unloaded extension `{extension}`.")
        logging.warning(f"unloaded cogs.{extension}")
    else:
        await ctx.send(f"Extension `{extension}` not loaded.")


@commands.command()
@commands.is_owner()
async def shutdown(ctx: commands.Context) -> None:
    """
    Zzz.
    """
    await ctx.send("I'll be back.")
    await ctx.bot.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loglevel", "-l", help="log level", default="INFO")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    logging.basicConfig(level=args.loglevel, format="[%(asctime)s] %(message)s", datefmt="%Y/%m/%d %T:%M:%S")
    faulthandler.enable()

    # Intents: members=True, emojis=True, invites=True, messages=True, reactions=True, message_content=True
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True  # Required for reading message content in v2

    bot = Bot(
        command_prefix=settings.prefix,
        description="https://board8.fandom.com/wiki/Mafia_Bidoof",
        conf=settings.conf,
        activity=settings.activity,
        owner_id=settings.owner_id,
        status=settings.status,
        intents=intents,
    )

    # Set up graceful shutdown on SIGINT/SIGTERM
    loop = asyncio.get_running_loop()

    def handle_shutdown() -> None:
        logging.warning("Shutting down...")
        loop.create_task(bot.close())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_shutdown)

    async with bot:
        for ext in settings.extensions:
            await bot.load_extension(f"cogs.{ext}")
            logging.warning(f"loaded cogs.{ext}")

        bot.add_command(shutdown)
        bot.add_command(reload)
        bot.add_command(unload)

        logging.warning("starting bot")
        await bot.start(settings.client_token)


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
