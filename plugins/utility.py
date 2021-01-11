from collections import Counter
from typing import Optional, List, Union

import random
import discord
import requests
import dice
from imgurpython.imgur.models.image import Image
from discord.ext import commands

from core.bot import Bot


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


class Utility(commands.Cog):
    """
    Utility commands, usable by everyone.
    """

    def __init__(self, bot: Bot):
        self.bot = bot

    @commands.command()
    async def avatar(self, ctx: commands.Context, user: Optional[discord.User]):
        """
        Fetch the avatar URL for a user.

        If no user mentioned, fetches your own avatar URL.
        """
        if user is None:
            user = ctx.author
        await ctx.send(str(user.avatar_url_as(static_format="png")))

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def bigmoji(self, ctx: commands.Context, emoji: Union[discord.PartialEmoji, discord.Emoji]):
        """
        Send an emoji, but big.
        """
        await ctx.send(emoji.url)
        await ctx.message.delete()

    @commands.command()
    async def ping(self, ctx: commands.Context):
        """
        Call-and-response to check if the bot is alive.
        """
        await ctx.send("pong")

    @commands.command()
    async def roll(self, ctx: commands.Context, expr: str):
        """
        Roll dice.

        e.g., "roll 1d4+2d8". Evaluates expressions using the syntax found at https://pypi.org/project/dice/.
        """
        result = dice.roll(expr)
        await ctx.send(result)

    @commands.command()
    async def trunc(self, ctx: commands.Context, size: int, *, message: str):
        """
        Truncate a message to <size> characters.
        """
        await ctx.send(f'`{message[:size]}`')


class Moderation(commands.Cog):
    """
    Server management and moderation, usable by admins.
    """

    def __init__(self, bot: Bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def clear(self, ctx: commands.Context, num: int):
        """
        Clear messages en masse.
        """
        assert type(ctx.channel) is discord.TextChannel
        deleted = await ctx.channel.purge(limit=num + 1)  # num+1 because the trigger message is counted too
        deletion_message = await ctx.send(f'*Cleared {len(deleted)} messages.*')
        await deletion_message.delete(delay=5)


class Management(commands.Cog):
    """
    Bot management, usable only by the bot owner.
    """

    def __init__(self, bot: Bot):
        self.bot = bot

    @commands.command()
    @commands.is_owner()
    async def msg(self, ctx: commands.Context, channel_id: int, *, message: str):
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
        await ctx.message.add_reaction(ctx.bot.greentick)

    @commands.command()
    @commands.is_owner()
    async def chavi(self, ctx: commands.Context, *, url: str):
        """
        Change the bot's avatar.
        """
        try:
            response = requests.get(url)
            await ctx.bot.user.edit(avatar=response.content)
            await ctx.message.add_reaction(ctx.bot.greentick)
        except Exception as e:
            await ctx.send(f'`Error: {e}`')
            await ctx.message.add_reaction(ctx.bot.redtick)

    @commands.command()
    @commands.is_owner()
    async def pin(self, ctx: commands.Context, msg_id: int, channel: Optional[discord.TextChannel]):
        """
        Pin a message.

        msg_id must be for a message in the current channel, unless a channel is specified.
        """
        if channel is not None:
            message = await channel.fetch_message(msg_id)
        else:
            message = await ctx.channel.fetch_message(msg_id)
        if message is None:
            await ctx.send(f'Message `{msg_id}` not found.')
            await ctx.message.add_reaction(ctx.bot.redtick)
            return
        await message.pin()
        await ctx.message.add_reaction(ctx.bot.greentick)

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        print(f"that's a guild update! oldsubs: {before.premium_subscription_count}, newsubs: {after.premium_subscription_count}")
        if before.id != 0:
            # TODO this should be removed and replaced w/ an actual opt-in db
            return

        # TODO: replace with a db channel entry
        chan = after.get_channel(0)  # type: discord.TextChannel

        if before.premium_subscription_count != after.premium_subscription_count:
            print(f'change in nitro boosters! {before.premium_subscription_count} -> {after.premium_subscription_count}')
            # nitro boost change
            before_subs = set(before.premium_subscribers)
            after_subs = set(after.premium_subscribers)
            ls_boosters = ''
            for booster in sorted(list(after_subs), key=lambda x: str(x).lower()):
                ls_boosters += f'{booster}\n'

            # NOTE: You can't determine the number of times a single member has boosted so
            #  this is useless until that functionality is added to the API.
            #
            # before_subs = Counter(before.premium_subscribers)
            # after_subs = Counter(after.premium_subscribers)
            # maxlen = 0
            # for booster in after_subs:
            #     if len(str(booster)) > maxlen:
            #         maxlen = len(str(booster))
            # for booster, count in after_subs.items():
            #     ls_boosters += f'{str(booster) + ":" : <{maxlen + 1}}: {count}\n'

            if before.premium_subscription_count < after.premium_subscription_count:
                # someone boosted
                newsub = list(after_subs - before_subs)
                ls_change = ', '.join(newsub)

                if ls_change is None:
                    msg = f"{self.bot.boostemoji} Someone who was already boosting added another boost! We can't tell who! _(This is a Discord API problem)_\n"
                else:
                    msg = f'{self.bot.boostemoji} `{ls_change}` just boosted the server!\n'

            else:
                # someone unboosted
                formersub = list(set(after.premium_subscribers) - set(before.premium_subscribers))
                ls_change = ', '.join(formersub)
                if ls_change is None:
                    msg = f"{self.bot.boostemoji} Someone removed one but not both of their boosts! We can't tell who! _(This is a Discord API problem)_\n"
                else:
                    msg = f'{self.bot.boostemoji} `{ls_change}` just unboosted the server :(\n'

            msg += f'New boosters ({after.premium_subscription_count}): ```ini\n{ls_boosters}```'

            await chan.send(msg)

            return


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
    bidoof_img = random.choice(bidoofs)  # type: Image
    if key is not None:
        # if a key is specified, attempt to override the randomly selected image
        for img in bidoofs:
            if img.description is not None and img.description.lower() == key.lower():
                bidoof_img = img
                break
    em = discord.Embed().set_image(url=bidoof_img.link)
    await ctx.send(embed=em)


def setup(bot: commands.Bot):
    bot.add_command(bidoof)

    bot.add_cog(Utility(bot))
    bot.add_cog(Moderation(bot))
    bot.add_cog(Management(bot))
