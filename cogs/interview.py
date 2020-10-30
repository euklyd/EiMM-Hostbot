from datetime import datetime
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

import discord
from discord.ext import commands
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from cogs import interview_schema as schema
from cogs.interview_schema import Server, Meta, Vote, OptOut, TotalQuestions
from core.bot import Bot
from utils import menu, spreadsheet

SCOPE = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]
SECRET = 'conf/google_creds.json'
SHEET_NAME = 'eimm role templates & keywords'


class Interview(commands.Cog):
    """
    Runs member interviews, interfaced with Google Sheets as a GUI.
    """

    def __init__(self, bot: Bot):
        self.bot = bot
        self.connection = None  # type: Optional[spreadsheet.SheetConnection]
        self.session_maker = None  # type:
        self.load()

    def load(self):
        self.connection = spreadsheet.SheetConnection(SECRET, SCOPE)
        db_dir = 'databases/'
        db_file = f'{db_dir}/interviews.db'
        if not Path(db_file).exists():
            # TODO: Don't technically need this condition?
            # Adds a bit of clarity though, so keeping it in for now.
            Path(db_dir).mkdir(exist_ok=True)
        engine = create_engine(f'sqlite:///{db_file}')
        self.session_maker = sessionmaker(bind=engine)

        schema.Base.metadata.create_all(engine)

    def new_interview(self):
        # TODO: yes.
        pass

    # == Setup ==

    @commands.group('ivsetup')
    @commands.has_permissions(administrator=True)
    async def ivsetup(self, ctx: commands.Context):
        # TODO: yes.
        #  document command group
        pass

    @ivsetup.command(name='server')
    @commands.has_permissions(administrator=True)
    async def ivsetup_server(self, ctx: commands.Context, answers: discord.TextChannel,
                             backstage: discord.TextChannel, sheet_url: str):
        # TODO: yes.
        #  setup server + channels for interview
        #  update all databases
        pass

    @ivsetup.command(name='interview')
    @commands.has_permissions(administrator=True)
    async def ivsetup_interview(self, ctx: commands.Context, interviewee: discord.Member, *, email: str):
        # TODO: yes.
        #  setup a new interview
        #  do we want the email to be private? not sure yet
        #  update metadata (maybe other databases?)
        pass

    # == Questions ==

    @commands.command()
    async def ask(self, ctx: commands.Context, *, question: str):
        # TODO:
        #  upload question to sheet
        #  update metadata
        pass

    @commands.command()
    async def mask(self, ctx: commands.Context, *, questions_str: str):
        # TODO:
        #  split up questions
        #  upload all questions to sheet
        #  update metadata
        pass

    # == Answers ==

    @commands.command()
    async def answer(self, ctx: commands.Context):
        # TODO:
        #  check if invoker is interviewee
        #  dump a bunch of answers
        #  update sheet
        pass

    @commands.command()
    async def preview(self, ctx: commands.Context):
        # TODO:
        #  check if invoker is interviewee
        #  dump a bunch of answers
        pass

    # == Votes ==

    @commands.command()
    async def vote(self, ctx: commands.Context, mentions: commands.Greedy[discord.Member]):
        # TODO: check votes for legality oh no

        session = self.session_maker()
        old_votes = session.query(Vote).filter_by(server_id=ctx.guild.id, voter_id=ctx.author.id).all()
        session.delete(old_votes)
        votes = []
        for mention in mentions:
            votes.append(Vote(server_id=ctx.guild.id, voter_id=ctx.author.id,
                              candidate_id=mention.id, timestamp=datetime.utcnow()))
        session.commit()
        await ctx.message.add_reaction(self.bot.greentick)

    @commands.command()
    async def votes(self, ctx: commands.Context):
        # TODO: list ppl the invoker is voting for
        session = self.session_maker()
        votes = session.query(Vote).filter_by(server_id=ctx.guild.id, voter_id=ctx.author.id).all()
        pass

    @commands.command()
    async def votals(self, ctx: commands.Context, flag: Optional[str]):
        session = self.session_maker()
        votes = session.query(Vote).filter_by(server_id=ctx.guild.id).all()
        # TODO: preprocessing
        if '-f' in flag:
            # TODO: do full votals
            pass
        else:
            # TODO: do normal votals
            pass


def setup(bot: commands.Bot):
    bot.add_cog(Interview(bot))
