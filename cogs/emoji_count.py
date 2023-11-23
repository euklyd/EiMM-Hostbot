import csv
import json
import re
from collections import namedtuple
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Union, Callable, Optional, List, Dict, Any

import aiohttp
import discord
from discord.ext import commands
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker, Session

import cogs.emoji_schema as es
import utils
from utils.menu import menu_list, CANCEL

_EMOJI_RE = re.compile(r"<:(?P<name>\w\w+):(?P<id>\d+)>")
MAX_ATTACHMENT_SIZE = 1e6

session_maker = None  # type: Union[None, Callable[[], Session]]
enabled_servers = []  # type: List[int]  # discord server IDs
needed_dirs = [
    "databases/conf/",
]
enabled_servers_path = "databases/conf/emoji_enabled_servers.json"


class NoneEmoji:
    name = "Deleted Emoji"
    url = ""
    user = ""
    created_at = ""

    def __repr__(self):
        return f"{self.name}"


def increment_count(
    session: Session, server: discord.guild, emoji_id: int, user: discord.user, today: datetime.date
) -> int:
    entry = (
        session.query(es.EmojiCount)
        .filter_by(server_id=server.id, emoji_id=emoji_id, user_id=user.id, date=today)
        .one_or_none()
    )  # type: Optional[es.EmojiCount]
    if entry is not None:
        entry.count += 1
    else:
        # make a new entry
        entry = es.EmojiCount(server_id=server.id, emoji_id=emoji_id, user_id=user.id, date=today, count=1)
        session.add(entry)
    session.commit()
    return entry.count


# TODO: add to cog? idk
async def count_emoji(message: discord.Message):
    if message.guild is None:
        return
    if message.author.bot:
        # nope
        return
    session = session_maker()

    emoji_ids = {e.id: e for e in message.guild.emojis}  # type: Dict[int, discord.Emoji]

    today = datetime.utcnow().date()

    for match in _EMOJI_RE.finditer(message.content):
        emoji_id = int(match.group("id"))  # type: int
        if emoji_id in emoji_ids:
            # only increment the count if it's an actual emoji that belongs to the server
            count = increment_count(session, message.guild, emoji_id, message.author, today)
            # await message.channel.send(f'Count for {emoji_ids[emoji_id]} is now {count}.')  # NOTE: Only for debug


def get_count(ctx: commands.Context, emoji_id: int, oldest: date) -> int:
    session = session_maker()
    entries = (
        session.query(es.EmojiCount)
            .filter_by(server_id=ctx.guild.id, emoji_id=emoji_id)
            .filter(func.DATE(es.EmojiCount.date) > oldest)
    )  # type: List[es.EmojiCount]
    count = 0
    for entry in entries:
        count += entry.count
    return count


class Emoji(commands.Cog):
    """Emoji management."""

    @commands.group(invoke_without_command=True)
    @commands.has_permissions(manage_emojis=True)
    async def emoji(self, ctx: commands.Context):
        await ctx.send("nah")
        # await emoji_head(ctx)  # if you wanted to do this by default? idk

    @emoji.command(name="enable")
    @commands.has_permissions(administrator=True)
    async def emoji_enable(self, ctx: commands.Context):
        """
        Enable emoji counting on the current server.
        """
        global enabled_servers
        if ctx.guild.id not in enabled_servers:
            enabled_servers.append(ctx.guild.id)
            with open(enabled_servers_path, "w") as enabled:
                json.dump(enabled_servers, enabled, indent=4)
            await ctx.send(f"Emoji counting enabled on **{ctx.guild}**.")
        else:
            await ctx.send(f"Emoji counting already enabled; use `disable` to turn it off.")

    @emoji.command(name="disable")
    @commands.has_permissions(administrator=True)
    async def emoji_disable(self, ctx: commands.Context):
        """
        Disable emoji counting on the current server.
        """
        global enabled_servers
        if ctx.guild.id in enabled_servers:
            enabled_servers.remove(ctx.guild.id)
            with open(enabled_servers_path, "w") as enabled:
                json.dump(enabled_servers, enabled, indent=4)
            await ctx.send(f"Emoji counting disabled on **{ctx.guild}**.")
        else:
            await ctx.send(f"Emoji counting not enabled; use `enable` to turn it on.")

    @emoji.command(name="count")
    @commands.has_permissions(manage_emojis=True)
    async def emoji_count(self, ctx: commands.Context, em: Union[discord.Emoji, int], days: Optional[int] = 30):
        """
        Count the times an emoji has been used in the last <days> days.

        Only returns uses for emojis belonging to this server, and only uses on this server.
        """
        if type(em) is discord.Emoji:
            assert type(em) is discord.Emoji
            emoji_id = em.id
        else:
            emoji_id = em

        oldest = datetime.utcnow().date() - timedelta(days=days)

        count = get_count(ctx, emoji_id, oldest)
        # TODO: This logic sucks, rewrite it sometime. You can do this in the query.

        # -- output conversion --
        if count == 1:
            n_times = f"{count} time"
        else:
            n_times = f"{count} times"
        if days == 1:
            n_days = f"{days} day"
        else:
            n_days = f"{days} days"
        await ctx.send(f"{ctx.bot.get_emoji(emoji_id)} has been used `{n_times}` in the last `{n_days}`.")

    @emoji.command(name="stats")
    @commands.has_permissions(manage_emojis=True)
    async def emoji_stats(
        self,
        ctx: commands.Context,
        em: Optional[Union[discord.Emoji, int]] = None,
        days: Optional[int] = 30,
        force: str = "",
    ):
        """
        More detailed stats for a given emoji over the last <days> days.

        Use -f as a third option to check for previous, now-deleted emoji using their ID snowflakes.
        """
        if em is None:
            await ctx.send(f"That's not an emoji on **{ctx.guild}**.")
            return

        if type(em) is discord.Emoji:
            assert type(em) is discord.Emoji
            emoji_id = em.id
        else:
            emoji_id = int(em)

        if force != "-f" and emoji_id not in [e.id for e in ctx.guild.emojis]:
            await ctx.send(f"That's not the ID of an emoji in **{ctx.guild}**.")
            return

        oldest = datetime.utcnow().date() - timedelta(days=days)

        session = session_maker()

        # list of tuples of users and how many time each has used this emoji, ordered by uses
        user_counts = (
            session.query(es.EmojiCount.user_id, func.sum(es.EmojiCount.count))
            .filter_by(server_id=ctx.guild.id, emoji_id=emoji_id)
            .filter(func.DATE(es.EmojiCount.date) > oldest)
            .group_by(es.EmojiCount.user_id)
            .order_by(func.sum(es.EmojiCount.count).desc())
            .all()
        )  # type: List[int, int]
        # really it's a List[sqlalchemy.util._collections.result] but functionally it's a list of int tuples

        count = 0
        for user, user_count in user_counts:
            count += user_count

        if len(user_counts) == 0:
            max_user = None
        else:
            max_user = ctx.guild.get_member(user_counts[0][0])

        # -- output conversion --
        if count == 1:
            n_times = f"{count} time"
        else:
            n_times = f"{count} times"
        if days == 1:
            n_days = f"{days} day"
        else:
            n_days = f"{days} days"

        if max_user is None:
            freq = f"Most frequent user: `N/A`"
        else:
            freq = f"Most frequent user: `{max_user}` (`{user_counts[0][1]}` uses)"
        await ctx.send(f"{ctx.bot.get_emoji(emoji_id)} has been used `{n_times}` in the last `{n_days}`.\n{freq}.")

    @emoji.command(name="head")
    @commands.has_permissions(manage_emojis=True)
    async def emoji_head(self, ctx: commands.Context, days: int = 30, num: int = 5, anim: bool = False):
        """
        Display the most frequently emojis for the current server.
        """
        oldest = datetime.utcnow().date() - timedelta(days=days)

        emoji_ids = {e.id: e for e in ctx.guild.emojis}  # type: Dict[int, discord.Emoji]
        animated_emojis = {e.id for e in ctx.guild.emojis if e.animated}

        session = session_maker()

        total_counts = (
            session.query(es.EmojiCount.emoji_id, func.sum(es.EmojiCount.count))
            .filter_by(server_id=ctx.guild.id)
            .filter(func.DATE(es.EmojiCount.date) > oldest)
            .group_by(es.EmojiCount.emoji_id)
            .order_by(func.sum(es.EmojiCount.count).desc())
            .all()
        )  # type: List[int, int]

        # total_counts = total_counts[:num]

        emoji_counts = {em: ct for em, ct in total_counts}  # type: Dict[int, int]
        for em_id in emoji_ids:
            if em_id not in emoji_counts:
                emoji_counts[em_id] = 0

        total_counts = list(emoji_counts.items())
        if not anim:
            total_counts = [e for e in total_counts if e[0] not in animated_emojis]
        total_counts = sorted(total_counts, key=lambda x: -x[1])[:num]

        reply = f"__**Top `{num}` emojis in the past `{days}` days for {ctx.guild}:**__\n"
        for i, entry in enumerate(total_counts):
            em = emoji_ids.get(entry[0])
            if em is None:
                em = NoneEmoji()
            reply += f"[{i + 1}] {em} `[:{em.name}:]`: {entry[1]} uses\n"

        await ctx.send(reply)

    @emoji.command(name="tail")
    @commands.has_permissions(manage_emojis=True)
    async def emoji_tail(self, ctx: commands.Context, days: int = 30, num: int = 5, anim: bool = False):
        """
        Display the least frequently emojis for the current server.
        """
        # TODO: Fill tail with never-used emojis?
        #  Add as a flag, probably.
        oldest = datetime.utcnow().date() - timedelta(days=days)

        emoji_ids = {e.id: e for e in ctx.guild.emojis}  # type: Dict[int, discord.Emoji]
        animated_emojis = {e.id for e in ctx.guild.emojis if e.animated}

        session = session_maker()

        total_counts = (
            session.query(es.EmojiCount.emoji_id, func.sum(es.EmojiCount.count))
            .filter_by(server_id=ctx.guild.id)
            .filter(func.DATE(es.EmojiCount.date) > oldest)
            .group_by(es.EmojiCount.emoji_id)
            .order_by(func.sum(es.EmojiCount.count).asc())
            .all()
        )  # type: List[int, int]

        # total_counts = total_counts[:num]

        emoji_counts = {em: ct for em, ct in total_counts}  # type: Dict[int, int]
        for em_id in emoji_ids:
            if em_id not in emoji_counts:
                emoji_counts[em_id] = 0

        total_counts = list(emoji_counts.items())
        if not anim:
            total_counts = [e for e in total_counts if e[0] not in animated_emojis]
        total_counts = sorted(total_counts, key=lambda x: x[1])[:num]

        reply = f"__**Bottom `{num}` emojis in the past `{days}` days for {ctx.guild}:**__\n"
        for i, entry in enumerate(total_counts):
            em = emoji_ids.get(entry[0])
            if em is None:
                em = NoneEmoji()
            reply += f"[{i + 1}] {em} `[:{em.name}:]`: {entry[1]} uses\n"

        await ctx.send(reply)

    @emoji.command(name="all")
    @commands.has_permissions(manage_emojis=True)
    async def emoji_all(self, ctx: commands.Context, days: int = 30, anim: bool = False):
        """
        Display counts for all emojis for the current server.
        """
        oldest = datetime.utcnow().date() - timedelta(days=days)

        emoji_ids = {e.id: e for e in ctx.guild.emojis}  # type: Dict[int, discord.Emoji]
        animated_emojis = {e.id for e in ctx.guild.emojis if e.animated}

        session = session_maker()

        total_counts = (
            session.query(es.EmojiCount.emoji_id, func.sum(es.EmojiCount.count))
            .filter_by(server_id=ctx.guild.id)
            .filter(func.DATE(es.EmojiCount.date) > oldest)
            .group_by(es.EmojiCount.emoji_id)
            .order_by(func.sum(es.EmojiCount.count).desc())
            .all()
        )  # type: List[int, int]

        # total_counts = total_counts[:num]

        emoji_counts = {em: ct for em, ct in total_counts}  # type: Dict[int, int]
        for em_id in emoji_ids:
            if em_id not in emoji_counts:
                emoji_counts[em_id] = 0

        total_counts = list(emoji_counts.items())
        if not anim:
            total_counts = [e for e in total_counts if e[0] not in animated_emojis]

        reply = f"__**All used emojis in the past `{days}` days for {ctx.guild}:**__\n"
        emoji_ls = []
        for i, entry in enumerate(total_counts):
            em = emoji_ids.get(entry[0])
            if em is None:
                em = NoneEmoji()
            emoji_ls.append(f"{em} : {entry[1]} uses")
        await ctx.send(reply)
        await utils.menu.menu_list(ctx, emoji_ls)  # we don't actually care to select anything

    @emoji.command(name="export")
    @commands.has_permissions(manage_emojis=True)
    async def emoji_export(self, ctx: commands.Context):
        """
        Export the emoji usage data for the current server to a CSV.
        """
        emojis = {}  # type: Dict[int, discord.Emoji]
        for em in ctx.guild.emojis:  # type: discord.Emoji
            # api call unfortunately required for getting detailed emoji info
            emojis[em.id] = await ctx.guild.fetch_emoji(em.id)

        filename = f"/tmp/{ctx.guild.name}_emojis.csv"
        with open(filename, "w") as f:
            out = csv.writer(f)
            labels = [
                "server id",
                "server",
                "user id",
                "user",
                "date of use",
                "emoji id",
                "emoji name",
                "emoji url",
                "creator",
                "creation time",
                "count",
            ]
            out.writerow(labels)

            session = session_maker()

            for entry in session.query(es.EmojiCount).filter_by(server_id=ctx.guild.id).all():  # type: es.EmojiCount
                em = emojis.get(entry.emoji_id)  # type: Union[discord.Emoji, NoneEmoji]
                if em is None:
                    em = NoneEmoji()
                out.writerow(
                    [
                        entry.server_id,
                        ctx.guild.name,
                        entry.user_id,
                        ctx.guild.get_member(entry.user_id),
                        entry.date,
                        entry.emoji_id,
                        em.name,
                        em.url,
                        em.user,
                        em.created_at,
                        entry.count,
                    ]
                )

        await ctx.send("Alright, _nerd_.", file=discord.File(filename))

    @commands.group(invoke_without_command=True)
    @commands.has_permissions(manage_emojis=True)
    async def evemoji(self, ctx: commands.Context):
        """Event Emoji command group."""
        pass

    async def ditto_add(self, ctx: commands.Context, session: Session) -> Optional[str]:
        """Interactive menu to get or confirm the name of the most recent game."""
        prev_emojis: List[es.EventEmoji] = []
        prev_emojis = session.query(es.EventEmoji).filter_by(server_id=ctx.guild.id, active=True).order_by(
            es.EventEmoji.date.desc()).all()
        if not prev_emojis:
            await ctx.send("No active previous event.")
            return None
        prev_event = prev_emojis[0].event
        await ctx.send(f"The previous event was {prev_event}. Confirm? [y/n]")
        msg = await ctx.bot.wait_for(event='message', check=lambda m: m.author == ctx.author, timeout=60)
        if msg.content.lower() == "y":
            return prev_event
        print(msg.content.lower())
        ls_events: List[str] = []
        for em in prev_emojis:
            if em.event not in ls_events:
                ls_events.append(em.event)
            if ls_events == 3:
                break
        events = ", ".join(ls_events)
        await ctx.send(f"Please rerun the command with the event you want. The previous three events were {events}.")

    @evemoji.command(name="add")
    @commands.has_permissions(manage_emojis=True)
    async def evemoji_add(
        self,
        ctx: commands.Context,
        event: str,
        owner: discord.Member,
        emojiname: str,
        # emoji: Union[discord.Emoji, discord.Attachment],  # TODO(dpy2.0)
        emoji: Union[discord.Emoji, discord.PartialEmoji, None],
    ):
        """Add a new Event Emoji."""
        emoji_url: Optional[str] = None
        if emoji:
            emoji_url = str(emoji.url)
        elif len(ctx.message.attachments) == 1:
            attachment: discord.Attachment = ctx.message.attachments[0]
            if attachment.size > MAX_ATTACHMENT_SIZE:
                await ctx.send(f"Attachment too large ({attachment.size} bytes; max {MAX_ATTACHMENT_SIZE}).")
                await ctx.message.add_reaction(ctx.bot.redtick)
                return
            emoji_url = str(attachment.url)
        else:
            await ctx.send("Must either specify an emoji or upload an image.")
            await ctx.message.add_reaction(ctx.bot.redtick)

        async with aiohttp.ClientSession() as aiosession:
            async with aiosession.get(emoji_url) as resp:
                if resp.status != 200:
                    await ctx.send("Error retrieving emoji data.")
                    await ctx.message.add_reaction(ctx.bot.redtick)
                    return
                emoji_bytes: bytes = await resp.content.read()

        try:
            created_emoji: discord.Emoji = await ctx.guild.create_custom_emoji(
                name=emojiname,
                image=emoji_bytes,
                reason=f"Added for {owner} ({event}).",
            )
        except Exception as e:
            await ctx.send(f"Upload error: {e}")
            await ctx.message.add_reaction(ctx.bot.redtick)
            return

        session = session_maker()

        if event.lower() == "ditto" or not event:
            prev_game = await self.ditto_add(ctx, session)
            if not prev_game:
                return
            event = prev_game

        event_emoji = es.EventEmoji(
            emoji_id=created_emoji.id,
            server_id=ctx.guild.id,
            date=datetime.utcnow(),
            owner_id=owner.id,
            event=event,
            active=True,
        )
        session.add(event_emoji)
        session.commit()
        await ctx.message.add_reaction(ctx.bot.greentick)

    @evemoji.command(name="rm")
    @commands.has_permissions(manage_emojis=True)
    async def evemoji_rm(
        self,
        ctx: commands.Context,
        emoji: discord.Emoji,
    ):
        """Remove an event emoji."""
        session = session_maker()
        event_emoji: es.EventEmoji = session.query(es.EventEmoji).filter_by(emoji_id=emoji.id, server_id=ctx.guild.id).one_or_none()
        if not event_emoji:
            await ctx.send(f"{emoji} is not registered as an Event Emoji.")
            await ctx.message.add_reaction(ctx.bot.redtick)
            return
        emoji: discord.Emoji = await ctx.guild.fetch_emoji(event_emoji.emoji_id)
        if emoji:
            await emoji.delete(reason="Deleted Event Emoji")
        else:
            await ctx.send("Emoji not found so cannot delete, but will be set inactive.")
        event_emoji.active = False
        session.commit()
        await ctx.message.add_reaction(ctx.bot.greentick)

    @evemoji.command(name="ls")
    @commands.has_permissions(manage_emojis=True)
    async def evemoji_ls(
        self,
        ctx: commands.Context,
        sort: Optional[str] = "alphabetical",
        # active: Optional[bool] = True,
        days: Optional[int] = 30,
    ):
        """
        List all (active) Event Emojis.
        Sort options: alphabetical, usage, date, owner, event
        Use days to limit the time window if you're counting by usage (default 30).
        """
        session = session_maker()
        query_emojis: List[es.EventEmoji] = []
        # I don't think it makes sense to show inactive emojis atm, it clutters up the command invocation.
        active = True
        if active:
            query_emojis = session.query(es.EventEmoji).filter_by(server_id=ctx.guild.id, active=True).all()
        else:
            query_emojis = session.query(es.EventEmoji).filter_by(server_id=ctx.guild.id).all()

        EmojiTuple = namedtuple("EmojiTuple", "discord db_entry count owner")
        emojis: List[EmojiTuple] = []
        for emoji in query_emojis:
            owner = ctx.guild.get_member(emoji.owner_id)
            oldest = datetime.utcnow().date() - timedelta(days=days)
            count = get_count(ctx, emoji.emoji_id, oldest)
            et = EmojiTuple(ctx.bot.get_emoji(emoji.emoji_id), emoji, count, owner)
            emojis.append(et)

        if sort.lower() not in {"alphabetical", "usage", "date", "owner", "event"}:
            await ctx.send(f"_Unrecognized sort '{sort}', using alphabetical._")
        if sort.lower() == "usage":
            emojis.sort(key=lambda e: e.count, reverse=True)
        elif sort.lower() == "date":
            emojis.sort(key=lambda e: e.db_entry.date)
        elif sort.lower() == "owner":
            emojis.sort(key=lambda e: e.db_entry.owner_id, reverse=True)
        elif sort.lower() == "event":
            emojis.sort(key=lambda e: e.db_entry.event, reverse=True)
        else:
            emojis.sort(key=lambda e: e.discord.name)

        # s = "\n".join(f"{em.discord} {em.discord.name}, {em.owner}, {em.db_entry.event}, {em.count}" for em in emojis)
        # print(s)
        # await ctx.send(sort + ":\n" + s)
        menu_entries = [
            f"{em.discord} from `{em.owner}` ({em.db_entry.event}, {em.db_entry.date}), {em.count} uses"
            for em in emojis
        ]
        try:
            await menu_list(
                ctx,
                menu_entries,
                heading=f"Event Emoji with usage over the past {days} days:",
                timeout=60,
                use_code_block=False,
            )
        except RuntimeError:
            await ctx.send(f"Exit your currently running menu first with `{CANCEL}`.")



def setup(bot: commands.Bot):
    global enabled_servers
    global session_maker

    db_dir = "databases/"
    db_file = f"{db_dir}/emojicount.db"
    if not Path(db_file).exists():
        Path(db_dir).mkdir(exist_ok=True)

    engine = create_engine(f"sqlite:///{db_file}")
    session_maker = sessionmaker(bind=engine)

    es.Base.metadata.create_all(engine)

    for needed_dir in needed_dirs:
        Path(needed_dir).mkdir(exist_ok=True)

    if Path(enabled_servers_path).exists():
        with open(enabled_servers_path, "r") as enabled:
            enabled_servers = json.load(enabled)
    else:
        enabled_servers = []

    bot.add_listener(count_emoji, "on_message")
    bot.add_cog(Emoji(bot))
