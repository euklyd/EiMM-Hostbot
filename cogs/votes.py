from pathlib import Path
from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from sqlalchemy import Column, Integer, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from core.bot import Bot

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

Base = declarative_base()

session_maker: "Callable[[], Session] | None" = None


def get_session() -> Session:
    """Get a database session, asserting that the database has been initialized."""
    assert session_maker is not None, "Database not initialized - Votes cog not loaded"
    return session_maker()


# TODO: Fix multi-channel voting. Right now there is a bug, so don't open multiple channels at once.

# NOTE: Deprecated until I've renamed this so it doesn't conflict with interviews, a far more important module.


class Vote(Base):
    __tablename__ = "Vote"
    channel_id = Column(Integer, primary_key=True)
    voter_id = Column(Integer, primary_key=True)
    voted_id = Column(Integer)

    def __repr__(self):
        return f"<Vote channel_id={self.channel_id}, voter_id={self.voter_id}, voted_id={self.voted_id}>"


# class Vote(Base):
#     __tablename__ = 'Vote'
#     channel_id = Column(Integer, primary_key=True)
#     voter_id = Column(Integer, primary_key=True)
#     # voted_id = Column(Integer)
#     voted_id = Column(String)
#
#     def __repr__(self):
#         return f'<Vote channel_id={self.channel_id}, voter_id={self.voter_id}, voted_id={self.voted_id}>'


class Channel(Base):
    __tablename__ = "Channel"
    channel_id = Column(Integer, primary_key=True)
    server_id = Column(Integer)


@commands.group(invoke_without_command=True)
async def vote(ctx: commands.Context) -> None:
    """
    Run votes for mafia-style games.
    """
    await ctx.send("this isn't a command")


@vote.command(name="setup")
@commands.is_owner()
async def vote_setup(ctx: commands.Context) -> None:
    """
    Set up a channel for voting.
    """
    session = get_session()
    old_channel = session.query(Channel).filter_by(channel_id=ctx.channel.id).one_or_none()
    if old_channel is not None:
        await ctx.send("This channel is already setup.")
        return
    channel = Channel(server_id=ctx.guild.id, channel_id=ctx.channel.id)
    session.add(channel)
    session.commit()
    await ctx.send(f"{ctx.channel} set up for voting!")


@vote.command(name="unsetup")
@commands.is_owner()
async def vote_unsetup(ctx: commands.Context) -> None:
    """
    Un-set up a channel for voting.
    """
    session = get_session()
    old_channel = session.query(Channel).filter_by(channel_id=ctx.channel.id).one_or_none()
    if old_channel is None:
        await ctx.send("This channel was never setup for votes.")
        return
    session.delete(old_channel)
    session.commit()
    await vote_clear(ctx)
    await ctx.send(f"{ctx.channel} no longer open for voting.")


@vote.command(name="clear")
@commands.is_owner()
async def vote_clear(ctx: commands.Context) -> None:
    """
    Clear all votes for a channel.
    """
    session = get_session()
    old_channel = session.query(Channel).filter_by(channel_id=ctx.channel.id).one_or_none()
    if old_channel is None:
        await ctx.send("This channel was never setup for votes.")
        return
    old_votes = session.query(Vote).filter_by(channel_id=ctx.channel.id).all()
    for old_vote in old_votes:
        session.delete(old_vote)
    session.commit()
    await ctx.send(f"Votes for {ctx.channel} cleared!")


@vote.command(name="for")
async def vote_for(ctx: commands.Context, votee: discord.Member) -> None:
    """
    Vote.
    """
    session = get_session()
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


# @commands.command()
# async def vote(ctx: commands.Context, *, votee: str):
#     """
#     Vote.
#     """
#     session = get_session()
#     old_channel = session.query(Channel).filter_by(channel_id=ctx.channel.id).one_or_none()
#     if old_channel is None:
#         await ctx.send("This channel hasn't been set up for voting.")
#         return
#     old_vote = session.query(Vote).filter_by(voter_id=ctx.author.id).one_or_none()
#     if votee not in legal_votes:
#         await ctx.send("That is not a legal vote; please check the alias list again.")
#         return
#     if old_vote is not None:
#         old_vote.voted_id = votee
#     else:
#         new_vote = Vote(channel_id=ctx.channel.id, voter_id=ctx.author.id, voted_id=votee)
#         session.add(new_vote)
#     session.commit()
#     await ctx.message.add_reaction(ctx.bot.greentick)


@vote.command(name="totals")
async def vote_totals(ctx: commands.Context) -> None:
    """
    Current votecounts.
    """
    session = get_session()
    old_channel = session.query(Channel).filter_by(channel_id=ctx.channel.id).one_or_none()
    if old_channel is None:
        await ctx.send("This channel hasn't been set up for voting.")
        return
    votes = session.query(Vote).filter_by(channel_id=ctx.channel.id).all()
    tally = {}
    for ballot in votes:
        if ballot.voted_id in tally:
            tally[ballot.voted_id] += 1
        else:
            tally[ballot.voted_id] = 1
    sorted_tally = sorted(tally.items(), key=lambda x: x[1], reverse=True)
    reply = "**Votals:**```\n"
    for ballot in sorted_tally:
        reply += f"{ballot[0]}: {ballot[1]}\n"
    reply += "```"
    await ctx.send(reply)


@vote.command(name="voters")
@commands.has_permissions(administrator=True)
async def vote_voters(ctx: commands.Context) -> None:
    session = get_session()
    old_channel = session.query(Channel).filter_by(channel_id=ctx.channel.id).one_or_none()
    if old_channel is None:
        await ctx.send("This channel hasn't been set up for voting.")
        return
    votes = session.query(Vote).filter_by(channel_id=ctx.channel.id).all()
    tally = {}
    for ballot in votes:
        if ballot.voted_id in tally:
            tally[ballot.voted_id] += [ballot.voter_id]
        else:
            tally[ballot.voted_id] = [ballot.voter_id]

    sorted_tally = sorted(tally.items(), key=lambda x: len(x[1]), reverse=True)
    reply = "**Votals:**```\n"
    for votee in sorted_tally:
        voters = [str(ctx.guild.get_member(voter_id)) for voter_id in votee[1]]
        reply += f"{votee[0]}: {voters}\n"
    reply += "```"
    await ctx.send(reply)


async def setup(bot: Bot) -> None:
    global session_maker

    # bot.add_command(vote_setup)
    # bot.add_command(vote_clear)
    # bot.add_command(vote_unsetup)
    # bot.add_command(vote)
    # bot.add_command(votals)
    # bot.add_command(voters)
    bot.add_command(vote)

    db_dir = "databases/"
    db_file = f"{db_dir}/votes.db"
    if not Path(db_file).exists():
        # TODO: Don't technically need this condition?
        # Adds a bit of clarity though, so keeping it in for now.
        Path(db_dir).mkdir(exist_ok=True)

    engine = create_engine(f"sqlite:///{db_file}")
    session_maker = sessionmaker(bind=engine)

    Base.metadata.create_all(engine)
