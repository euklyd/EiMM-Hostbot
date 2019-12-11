import io

from PIL import Image

import discord
from discord.ext import commands


@commands.command()
async def color(ctx: commands.Context, hexcode):
    if hexcode[0] == '#':
        color = hexcode
    else:
        color = f'#{hex(int(hexcode, 16))[2:]}'
    # color = ((hexcode >> 16) & 0xff, (hexcode >> 8) & 0xff, hexcode & 0xff)
    im = Image.new('RGB', size=(128, 128), color=color)
    img_bytes = io.BytesIO()
    filename = f'{color}.png'
    im.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    f = discord.File(img_bytes, filename=filename)
    await ctx.send(file=f)


def setup(bot: commands.Bot):
    bot.add_command(color)
