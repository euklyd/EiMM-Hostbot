import csv
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Union, Callable, Optional, List, Dict

import discord
from discord.ext import commands
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker, Session

import plugins.emoji_schema as es

_EMOJI_RE = re.compile(r'<:(?P<name>\w\w+):(?P<id>\d+)>')

session_maker = None  # type: Union[None, Callable[[], Session]]
enabled_servers = []  # type: List[int]  # discord server IDs
enabled_servers_path = 'databases/conf/emoji_enabled_servers.json'


def increment_count(session: Session, server: discord.guild, emoji_id: int, user: discord.user,
                    today: datetime.date) -> int:
    entry = session.query(es.EmojiCount).filter_by(server_id=server.id, emoji_id=emoji_id, user_id=user.id,
                                                   date=today).one_or_none()  # type: Optional[es.EmojiCount]
    if entry is not None:
        entry.count += 1
    else:
        # make a new entry
        entry = es.EmojiCount(server_id=server.id, emoji_id=emoji_id, user_id=user.id, date=today, count=1)
        session.add(entry)
    session.commit()
    return entry.count


async def count_emoji(message: discord.Message):
    if message.author.bot:
        # nope
        return
    session = session_maker()

    emoji_ids = {e.id: e for e in message.guild.emojis}

    today = datetime.utcnow().date()

    for match in _EMOJI_RE.finditer(message.content):
        emoji_id = int(match.group('id'))  # type: int
        if emoji_id in emoji_ids:
            # only increment the count if it's an actual emoji that belongs to the server
            count = increment_count(session, message.guild, emoji_id, message.author, today)
            # await message.channel.send(f'Count for {emoji_ids[emoji_id]} is now {count}.')  # NOTE: Only for debug


@commands.group(invoke_without_command=True)
async def emoji(ctx: commands.Context):
    await ctx.send('nah')


@emoji.command(name='enable')
@commands.is_owner()
async def emoji_enable(ctx: commands.Context):
    """
    Enable emoji counting on the current server.
    """
    global enabled_servers
    if ctx.guild.id not in enabled_servers:
        enabled_servers.append(ctx.guild.id)
        with open(enabled_servers_path, 'w') as enabled:
            json.dump(enabled_servers, enabled, indent=4)
        await ctx.send(f'Emoji counting enabled on **{ctx.guild}**.')
    else:
        await ctx.send(f'Emoji counting already enabled; use `disable` to turn it off.')


@emoji.command(name='disable')
@commands.is_owner()
async def emoji_disable(ctx: commands.Context):
    """
    Disable emoji counting on the current server.
    """
    global enabled_servers
    if ctx.guild.id in enabled_servers:
        enabled_servers.remove(ctx.guild.id)
        with open(enabled_servers_path, 'w') as enabled:
            json.dump(enabled_servers, enabled, indent=4)
        await ctx.send(f'Emoji counting disabled on **{ctx.guild}**.')
    else:
        await ctx.send(f'Emoji counting not enabled; use `enable` to turn it on.')


@emoji.command(name='count')
async def emoji_count(ctx: commands.Context, em: Union[discord.Emoji, int], days: Optional[int] = 30):
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

    session = session_maker()
    entries = session.query(es.EmojiCount).filter_by(
        server_id=ctx.guild.id, emoji_id=emoji_id).filter(
        func.DATE(es.EmojiCount.date) > oldest)  # type: List[es.EmojiCount]
    # count = session.query(func.sum(es.EmojiCount)).filter_by(
    #     server_id=ctx.guild.id, emoji_id=emoji_id).filter(
    #     func.DATE(es.EmojiCount.date) > oldest)  # # type: List[es.EmojiCount]
    # if count is None:
    #     count = 0

    count = 0
    for entry in entries:
        count += entry.count

    # -- output conversion --
    if count == 1:
        n_times = f'{count} time'
    else:
        n_times = f'{count} times'
    if days == 1:
        n_days = f'{days} day'
    else:
        n_days = f'{days} days'
    await ctx.send(f'{ctx.bot.get_emoji(emoji_id)} has been used `{n_times}` in the last `{n_days}`.')


@emoji.command(name='stats')
async def emoji_stats(ctx: commands.Context, em: Union[discord.Emoji, int], days: Optional[int] = 30):
    """
    More detailed stats for a given emoji over the last <days> days.
    """
    if type(em) is discord.Emoji:
        assert type(em) is discord.Emoji
        emoji_id = em.id
    else:
        emoji_id = int(em)

    oldest = datetime.utcnow().date() - timedelta(days=days)

    session = session_maker()
    entries = session.query(es.EmojiCount).filter_by(
        server_id=ctx.guild.id, emoji_id=emoji_id).filter(
        func.DATE(es.EmojiCount.date) > oldest).order_by(es.EmojiCount.count).all()  # type: List[es.EmojiCount]

    print(type(entries))
    print(len(entries))

    count = 0
    for entry in entries:
        count += entry.count

    if len(entries) == 0:
        user = None
    else:
        user = ctx.guild.get_member(entries[0].user_id)

    # -- output conversion --
    if count == 1:
        n_times = f'{count} time'
    else:
        n_times = f'{count} times'
    if days == 1:
        n_days = f'{days} day'
    else:
        n_days = f'{days} days'

    if user is None:
        freq = f'Most frequent user: `N/A`'
    else:
        freq = f'Most frequent user: `{user}` (`{entries[0].count}` uses)'
    await ctx.send(f'{ctx.bot.get_emoji(emoji_id)} has been used `{n_times}` in the last `{n_days}`.\n{freq}.')


@emoji.command(name='export')
async def emoji_export(ctx: commands.Context):
    """
    Export the emoji usage data for the current server to a CSV.
    """
    emojis = {}  # type: Dict[int, discord.Emoji]
    for em in ctx.guild.emojis:  # type: discord.Emoji
        # api call unfortunately required for getting detailed emoji info
        emojis[em.id] = await ctx.guild.fetch_emoji(em.id)

    filename = f'/tmp/{ctx.guild.name}_emojis.csv'
    with open(filename, 'w') as f:
        out = csv.writer(f)
        labels = [
            'server id', 'server',
            'user id', 'user',
            'date of use',
            'emoji id', 'emoji name', 'emoji url', 'creator', 'creation time',
            'count'
        ]
        out.writerow(labels)

        session = session_maker()

        class NoneEmoji:
            name = 'Deleted Emoji'
            url = ''
            user = ''
            created_at = ''

        for entry in session.query(es.EmojiCount).filter_by(server_id=ctx.guild.id).all():  # type: es.EmojiCount
            em = emojis.get(entry.emoji_id)  # type: Union[discord.Emoji, NoneEmoji]
            if em is None:
                em = NoneEmoji()
            out.writerow([
                entry.server_id, ctx.guild.name,
                entry.user_id, ctx.guild.get_member(entry.user_id),
                entry.date,
                entry.emoji_id, em.name, em.url, em.user, em.created_at,
                entry.count
            ])

    await ctx.send('Alright, _nerd_.', file=discord.File(filename))


def setup(bot: commands.Bot):
    global enabled_servers
    global session_maker

    db_dir = 'databases/'
    db_file = f'{db_dir}/emojicount.db'
    if not Path(db_file).exists():
        Path(db_dir).mkdir(exist_ok=True)

    engine = create_engine(f'sqlite:///{db_file}')
    session_maker = sessionmaker(bind=engine)

    es.Base.metadata.create_all(engine)

    if Path(enabled_servers_path).exists():
        with open(enabled_servers_path, 'r') as enabled:
            enabled_servers = json.load(enabled)
    else:
        enabled_servers = []

    bot.add_listener(count_emoji, 'on_message')
    bot.add_command(emoji)
