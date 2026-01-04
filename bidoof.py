import argparse
import asyncio
import faulthandler
import logging
import os
import signal

import discord
from discord.ext import commands

import conf.settings as settings
from core.bot import Bot
from db import init_db


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
async def sync(ctx: commands.Context, guild_id: int | None = None) -> None:
    """
    Sync slash commands to Discord.

    If guild_id is provided, copy global commands to that guild and sync (instant).
    Otherwise, sync globally (can take up to an hour to propagate).
    """
    if guild_id:
        guild = discord.Object(id=guild_id)
        # Copy global commands to this guild for instant availability
        ctx.bot.tree.copy_global_to(guild=guild)
        synced = await ctx.bot.tree.sync(guild=guild)
        await ctx.send(f"Synced {len(synced)} commands to guild {guild_id}.")
    else:
        synced = await ctx.bot.tree.sync()
        await ctx.send(f"Synced {len(synced)} commands globally.")


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
    web_server = None  # Will be uvicorn.Server if web is enabled

    def handle_shutdown() -> None:
        logging.warning("Shutting down...")
        if web_server is not None:
            web_server.should_exit = True
        loop.create_task(bot.close())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_shutdown)

    async with bot:
        # Initialize database if DATABASE_URL is set
        database_url = os.environ.get("DATABASE_URL")
        if database_url:
            init_db(database_url)
            logging.info("Database initialized")

            # Create tables for interview schema
            # Import models to register them with Base.metadata
            from cogs.interview import models as _  # noqa: F401
            from db import create_tables
            from db.base import Base

            await create_tables(Base)
            logging.info("Database tables created")
        else:
            logging.warning("DATABASE_URL not set - database features disabled")

        # Initialize web server if enabled
        web_enabled = os.environ.get("WEB_ENABLED", "").lower() == "true"
        if web_enabled:
            import uvicorn

            from web.app import create_app

            web_app = create_app(bot)
            web_port = int(os.environ.get("WEB_PORT", "8080"))
            config = uvicorn.Config(
                web_app,
                host="0.0.0.0",
                port=web_port,
                log_level=args.loglevel.lower(),
            )
            web_server = uvicorn.Server(config)
            logging.info(f"Web server will start on port {web_port}")

        for ext in settings.extensions:
            await bot.load_extension(f"cogs.{ext}")
            logging.warning(f"loaded cogs.{ext}")

        bot.add_command(shutdown)
        bot.add_command(reload)
        bot.add_command(unload)
        bot.add_command(sync)

        logging.warning("starting bot")

        # Run bot and web server concurrently if web is enabled
        if web_server is not None:
            await asyncio.gather(
                bot.start(settings.client_token),
                web_server.serve(),
            )
        else:
            await bot.start(settings.client_token)


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
