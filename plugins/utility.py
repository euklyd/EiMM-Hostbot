from typing import Optional

import random
# import requests
import discord
from discord.ext import commands


# from selenium import webdriver
# from selenium.webdriver.common.keys import Keys
# from selenium.webdriver.chrome.options import Options


# @commands.command()
# async def outline(ctx: commands.Context, url: str):
#     # If we wanted to do something super cool, we'd spoof an actual browser with selenium, and use outline.com
#     # to generate a full link that way.
#     # Unfortunately, it turns out selenium doesn't work very well with outline so we'll ignore that for now.
#     tinyurl = requests.get(f'https://tinyurl.com/api-create.php?url={url}').content.decode('utf8')
#     outline_url = f'https://outline.com/{tinyurl}'
#     await ctx.send(outline_url)


@commands.command()
async def bidoof(ctx: commands.Context, key: Optional[str]):
    """
    I can't make a Mafia Bidoof bot *without* this command.

    God bless Mafia Bidoof.
    """
    BIDOOF_ALBUM = 'kn6ieEv'
    bidoofs = []
    if type(BIDOOF_ALBUM) is list:
        for album in BIDOOF_ALBUM:
            bidoofs += ctx.bot.imgur.get_album_images(album)
    else:
        bidoofs = ctx.bot.imgur.get_album_images(BIDOOF_ALBUM)
    bidoof = random.choice(bidoofs)
    if key is not None:
        for img in bidoofs:
            if img.description is not None and img.description.lower() == key.lower():
                bidoof = img
                break
    em = discord.Embed().set_image(url=bidoof.link)
    await ctx.send(embed=em)


@commands.command()
@commands.is_owner()
async def msg(ctx: commands.Context, channel_id: int, *, message: str):
    """
    Send a message to the specified channel ID.
    """
    channel = ctx.bot.get_channel(channel_id)  # type: discord.TextChannel
    if channel is None:
        channel = ctx.bot.get_user(channel_id)  # type: discord.User
    if channel is None:
        # Not a text channel or a user.
        await ctx.send('No matching channel found.')
    await channel.send(message)


def setup(bot: commands.Bot):
    bot.add_command(bidoof)
    bot.add_command(msg)
