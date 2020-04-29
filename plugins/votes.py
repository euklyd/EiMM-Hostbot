from pathlib import Path
from typing import Callable, Union, Optional

import discord
from discord.ext import commands
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from core.bot import Bot

Base = declarative_base()

session_maker = None  # type: Union[None, Callable[[], Session]]


# TODO: Fix multi-channel voting. Right now there is a bug, so don't open multiple channels at once.


# class Vote(Base):
#     __tablename__ = 'Vote'
#     channel_id = Column(Integer, primary_key=True)
#     voter_id = Column(Integer, primary_key=True)
#     voted_id = Column(Integer)
#
#     def __repr__(self):
#         return f'<Vote channel_id={self.channel_id}, voter_id={self.voter_id}, voted_id={self.voted_id}>'


class Vote(Base):
    __tablename__ = 'Vote'
    channel_id = Column(Integer, primary_key=True)
    voter_id = Column(Integer, primary_key=True)
    # voted_id = Column(Integer)
    voted_id = Column(String)

    def __repr__(self):
        return f'<Vote channel_id={self.channel_id}, voter_id={self.voter_id}, voted_id={self.voted_id}>'


legal_votes = [
    "ain't no party like a rakdos party",
    "aliasn't",
    "AncestralRecall",
    "ban flash in commander ffs",
    "beyond repair",
    "Black man, don't shoot",
    "Boggart Arsonist",
    "Boggart Brute",
    "Boggart Foragers",
    "Boggart Loggers",
    "Boggart Mob",
    "Boggart Ram-Gang",
    "Collector Oof",
    "Conq's Harem",
    "From the Helvault",
    "Fullmetal",
    "Goblin Token",
    "HYDRA BITCH",
    "i am once again asking did you pay the 2",
    "i demand fully randomized alias lists",
    "Ignite Memories",
    "L",
    "Lodestone",
    "Lord Gaius",
    "Lotus",
    "Maestria com Metais - Contestação Estoica custará 1 a menos para ser conjurado se você controlar três ou mais artefatos.",
    "most broken role itg",
    "Ninja of the Deep Hours",
    "Ninja Rodent",
    "noise alias, \"\"\"rand\"\"\" n1",
    "Not all rodents are rats, you know. Plus, why is being a rat used as an insult nowadays? By the way, if you're questioning whether I am a rat, I",
    "please make sure i read my role correctly @daycop",
    "Ratboy Slim",
    "Ratsune Miku",
    "Remy",
    "Saproling",
    "Sofiaaaaaaaaaaaaaaa~",
    "Stuart",
    "thank you for expansion of game size",
    "The Bastardliest Bastard",
    "translucent powder",
    "White lie",
    "WHY CAN'T I WAKE UP IN TIME FOR TURNIPS",
    "Worthless.",
    "You have activated my trap card",
]


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


# @commands.command()
# async def vote(ctx: commands.Context, votee: discord.Member):
#     """
#     Vote.
#     """
#     session = session_maker()
#     old_channel = session.query(Channel).filter_by(channel_id=ctx.channel.id).one_or_none()
#     if old_channel is None:
#         await ctx.send("This channel hasn't been set up for voting.")
#         return
#     old_vote = session.query(Vote).filter_by(voter_id=ctx.author.id).one_or_none()
#     if old_vote is not None:
#         old_vote.voted_id = votee.id
#     else:
#         new_vote = Vote(channel_id=ctx.channel.id, voter_id=ctx.author.id, voted_id=votee.id)
#         session.add(new_vote)
#     session.commit()
#     await ctx.message.add_reaction(ctx.bot.greentick)


@commands.command()
async def vote(ctx: commands.Context, *, votee: str):
    """
    Vote.
    """
    session = session_maker()
    old_channel = session.query(Channel).filter_by(channel_id=ctx.channel.id).one_or_none()
    if old_channel is None:
        await ctx.send("This channel hasn't been set up for voting.")
        return
    old_vote = session.query(Vote).filter_by(voter_id=ctx.author.id).one_or_none()
    if votee not in legal_votes:
        await ctx.send("That is not a legal vote; please check the alias list again.")
        return
    if old_vote is not None:
        old_vote.voted_id = votee
    else:
        new_vote = Vote(channel_id=ctx.channel.id, voter_id=ctx.author.id, voted_id=votee)
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
        reply += f'{ballot[0]}: {ballot[1]}\n'
    reply += '```'
    await ctx.send(reply)


@commands.has_permissions(administrator=True)
@commands.command()
async def voters(ctx: commands.Context):
    session = session_maker()
    old_channel = session.query(Channel).filter_by(channel_id=ctx.channel.id).one_or_none()
    if old_channel is None:
        await ctx.send("This channel hasn't been set up for voting.")
        return
    votes = session.query(Vote).filter_by(channel_id=ctx.channel.id).all()
    tally = {}
    for ballot in votes:  # type: Vote
        if ballot.voted_id in tally:
            tally[ballot.voted_id] += [ballot.voter_id]
        else:
            tally[ballot.voted_id] = [ballot.voter_id]

    sorted_tally = sorted(tally.items(), key=lambda x: len(x[1]), reverse=True)
    reply = '**Votals:**```\n'
    for votee in sorted_tally:  # type: tuple[int, int]
        voters = [str(ctx.guild.get_member(voter_id)) for voter_id in votee[1]]
        reply += f'{votee[0]}: {voters}\n'
    reply += '```'
    await ctx.send(reply)


def setup(bot: Bot):
    global session_maker

    bot.add_command(vote_setup)
    bot.add_command(vote_clear)
    bot.add_command(vote_unsetup)
    bot.add_command(vote)
    bot.add_command(votals)
    bot.add_command(voters)

    db_dir = 'databases/'
    db_file = f'{db_dir}/votes.db'
    if not Path(db_file).exists():
        # TODO: Don't technically need this condition?
        # Adds a bit of clarity though, so keeping it in for now.
        Path(db_dir).mkdir(exist_ok=True)

    engine = create_engine(f'sqlite:///{db_file}')
    session_maker = sessionmaker(bind=engine)

    Base.metadata.create_all(engine)
