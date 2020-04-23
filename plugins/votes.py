from pathlib import Path
from typing import Callable, Union, Optional

import discord
from discord.ext import commands
from sqlalchemy import create_engine, Column, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from core.bot import Bot

Base = declarative_base()

session_maker = None  # type: Union[None, Callable[[], Session]]


# TODO: Fix multi-channel voting. Right now there is a bug, so don't open multiple channels at once.


class Vote(Base):
    __tablename__ = 'Vote'
    channel_id = Column(Integer, primary_key=True)
    voter_id = Column(Integer, primary_key=True)
    voted_id = Column(Integer)

    def __repr__(self):
        return f'<Vote channel_id={self.channel_id}, voter_id={self.voter_id}, voted_id={self.voted_id}>'


class Channel(Base):
    __tablename__ = 'Channel'
    channel_id = Column(Integer, primary_key=True)
    server_id = Column(Integer)


@commands.is_owner()
@commands.command()
async def vote_setup(ctx: commands.Context):
    """
    Set up a channel for voting.
    """
    session = session_maker()
    old_channel = session.query(Channel).filter_by(channel_id=ctx.channel.id).one_or_none()
    if old_channel is not None:
        await ctx.send('This channel is already setup.')
        return
    channel = Channel(server_id=ctx.guild.id, channel_id=ctx.channel.id)
    session.add(channel)
    session.commit()
    await ctx.send(f'{ctx.channel} set up for voting!')


@commands.is_owner()
@commands.command()
async def vote_unsetup(ctx: commands.Context):
    """
    Un-set up a channel for voting.
    """
    session = session_maker()
    old_channel = session.query(Channel).filter_by(channel_id=ctx.channel.id).one_or_none()
    if old_channel is None:
        await ctx.send('This channel was never setup for votes.')
        return
    session.delete(old_channel)
    session.commit()
    await vote_clear(ctx)
    await ctx.send(f'{ctx.channel} no longer open for voting.')


@commands.is_owner()
@commands.command()
async def vote_clear(ctx: commands.Context):
    """
    Clear all votes for a channel.
    """
    session = session_maker()
    old_channel = session.query(Channel).filter_by(channel_id=ctx.channel.id).one_or_none()
    if old_channel is None:
        await ctx.send('This channel was never setup for votes.')
        return
    old_votes = session.query(Vote).filter_by(channel_id=ctx.channel.id).all()
    for old_vote in old_votes:
        session.delete(old_vote)
    session.commit()
    await ctx.send(f'Votes for {ctx.channel} cleared!')


@commands.command()
async def vote(ctx: commands.Context, votee: discord.Member):
    """
    Vote.
    """
    session = session_maker()
    old_channel = session.query(Channel).filter_by(channel_id=ctx.channel.id).one_or_none()
    if old_channel is None:
        await ctx.send("This channel hasn't been set up for voting.")
        return
    old_vote = session.query(Vote).filter_by(voter_id=ctx.author.id).one_or_none()
    if old_vote is not None:
        old_vote.voted_id = votee.id
    else:
        new_vote = Vote(channel_id=ctx.channel.id, voter_id=ctx.author.id, voted_id=votee.id)
        session.add(new_vote)
    session.commit()
    await ctx.message.add_reaction(ctx.bot.greentick)


@commands.command()
async def votals(ctx: commands.Context):
    """
    Current votecounts.
    """
    session = session_maker()
    old_channel = session.query(Channel).filter_by(channel_id=ctx.channel.id).one_or_none()
    if old_channel is None:
        await ctx.send("This channel hasn't been set up for voting.")
        return
    votes = session.query(Vote).filter_by(channel_id=ctx.channel.id).all()
    tally = {}
    for ballot in votes:  # type: Vote
        if ballot.voted_id in tally:
            tally[ballot.voted_id] += 1
        else:
            tally[ballot.voted_id] = 1
    sorted_tally = sorted(tally.items(), key=lambda x: x[1], reverse=True)
    reply = '**Votals:**```\n'
    for ballot in sorted_tally:  # type: tuple[int, int]
        member = ctx.guild.get_member(ballot[0])
        reply += f'{member}: {ballot[1]}\n'
    reply += '```'
    await ctx.send(reply)


def setup(bot: Bot):
    global session_maker

    bot.add_command(vote_setup)
    bot.add_command(vote_clear)
    bot.add_command(vote_unsetup)
    bot.add_command(vote)
    bot.add_command(votals)

    db_dir = 'databases/'
    db_file = f'{db_dir}/votes.db'
    if not Path(db_file).exists():
        # TODO: Don't technically need this condition?
        # Adds a bit of clarity though, so keeping it in for now.
        Path(db_dir).mkdir(exist_ok=True)

    engine = create_engine(f'sqlite:///{db_file}')
    session_maker = sessionmaker(bind=engine)

    Base.metadata.create_all(engine)
