from typing import Optional, List

import random
# import requests
import discord
import requests
from imgurpython.imgur.models.image import Image
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
    bidoofs = []  # type: List[Image]
    if type(BIDOOF_ALBUM) is list:
        for album in BIDOOF_ALBUM:
            bidoofs += ctx.bot.imgur.get_album_images(album)
    else:
        bidoofs = ctx.bot.imgur.get_album_images(BIDOOF_ALBUM)
    bidoof_img = random.choice(bidoofs)  # Image
    if key is not None:
        # if a key is specified, attempt to override the randomly selected image
        for img in bidoofs:
            if img.description is not None and img.description.lower() == key.lower():
                bidoof_img = img
                break
    em = discord.Embed().set_image(url=bidoof_img.link)
    await ctx.send(embed=em)


@commands.command()
@commands.is_owner()
async def msg(ctx: commands.Context, channel_id: int, *, message: str):
    """
    Send a message to the specified channel.

    Also works for whispering to users. Please don't abuse this!
    """
    channel = ctx.bot.get_channel(channel_id)  # type: discord.TextChannel
    if channel is None:
        channel = ctx.bot.get_user(channel_id)  # type: discord.User
    if channel is None:
        # Not a text channel or a user.
        await ctx.send('No matching channel found.')
    await channel.send(message)


@commands.command()
@commands.is_owner()
async def chavi(ctx: commands.Context, *, url: str):
    try:
        response = requests.get(url)
        await ctx.bot.user.edit(avatar=response.content)
        await ctx.message.add_reaction(ctx.bot.greentick)
    except Exception as e:
        await ctx.send(f'`Error: {e}`')
        await ctx.message.add_reaction(ctx.bot.redtick)


@commands.command()
async def trunc(ctx: commands.Context, size: int, *, msg: str):
    await ctx.send(f'`{msg[:size]}`')


@commands.command()
@commands.has_permissions(administrator=True)
async def clear(ctx: commands.Context, num: int):
    """
    Clear messages en masse.
    """
    assert type(ctx.channel) is discord.TextChannel
    deleted = await ctx.channel.purge(limit=num+1)  # num+1 because the trigger message is counted too
    deletion_message = await ctx.send(f'*Cleared {len(deleted)} messages.*')
    await deletion_message.delete(delay=5)


def setup(bot: commands.Bot):
    bot.add_command(bidoof)
    bot.add_command(msg)
    bot.add_command(chavi)
    bot.add_command(trunc)
    bot.add_command(clear)
