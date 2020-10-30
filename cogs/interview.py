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

    @commands.group('iv')
    @commands.has_permissions(administrator=True)
    async def iv(self, ctx: commands.Context):
        """
        # TODO: Write actual instructions and info for this module here.
        """
        # TODO: yes.
        #  document command group
        #  TODO: write instructions on setting up on a new server
        pass

    @iv.command(name='setup')
    @commands.has_permissions(administrator=True)
    async def iv_setup(self, ctx: commands.Context, answers: discord.TextChannel,
                             backstage: discord.TextChannel, sheet_url: str):
        """
        Set up the current server for interviews.

        Answer channel is where where answers to questions will be posted, backstage is a private space for
        the bot to be controlled.
        """
        # TODO: yes.
        #  setup server + channels for interview
        #  update all databases
        pass

    @iv.command(name='next')
    @commands.has_permissions(administrator=True)
    async def iv_next(self, ctx: commands.Context, interviewee: discord.Member, *, email: Optional[str] = None):
        """
        Set up the next interview for <interviewee>.

        Creates a new interview sheet for the next interviewee. If the optional <email> parameter is provided,
        shares the document with them. Old emails must still be cleared out manually.
        # TODO: deprecate former behavior of using current channel as new backstage
        """

        # TODO: yes.
        #  setup a new interview
        #  do we want the email to be private? not sure yet
        #  update metadata (maybe other databases?)
        pass

    # TODO (maybe): Add methods to change the answer/backstage channels.

    @iv.command(name='disable')
    async def iv_disable(self, ctx: commands.Context):
        """
        Disable voting and question asking for the current interview.
        """
        pass

    @iv.command(name='enable')
    async def iv_enable(self, ctx: commands.Context):
        """
        Re-enable voting and question asking for the current interview.
        """
        pass

    # == Questions ==

    @commands.command()
    async def ask(self, ctx: commands.Context, *, question: str):
        """
        Submit a question for the current interview.
        """
        # TODO:
        #  upload question to sheet
        #  update metadata
        pass

    @commands.command()
    async def mask(self, ctx: commands.Context, *, questions_str: str):
        """
        Submit multiple questions for the current interview.

        Each question must be a single line, separated by linebreaks.
        """
        # TODO:
        #  split up questions
        #  upload all questions to sheet
        #  update metadata
        pass

    # == Answers ==

    @commands.command()
    async def answer(self, ctx: commands.Context):
        """
        Post all answers to questions that have not yet been posted.

        Questions will be grouped by asker, rather than strictly in chronological order.
        # TODO: Add a flag to post strictly chronologically?
        """
        # TODO:
        #  check if invoker is interviewee
        #  dump a bunch of answers
        #  update sheet
        pass

    @commands.command()
    async def preview(self, ctx: commands.Context):
        """
        Preview answers, visible in the backstage channel.
        """
        # TODO:
        #  check if invoker is interviewee
        #  dump a bunch of answers
        pass

    # == Votes ==

    @commands.command()
    async def vote(self, ctx: commands.Context, mentions: commands.Greedy[discord.Member]):
        """
        Vote for up to three nominees for the next interview.

        Voting rules:
        1. Cannot vote for yourself.
        2. Cannot vote for anyone who's been interviewed too recently.
        3. Cannot vote if you've joined the server since the start of the last interview.
        4. Cannot vote for bots, excepting HaruBot.
        5. Cannot vote while interviews are disabled.
        6. Cannot vote for people who are opted out.
        """
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
        """
        Check who you're voting for.
        """
        # TODO: list ppl the invoker is voting for
        session = self.session_maker()
        votes = session.query(Vote).filter_by(server_id=ctx.guild.id, voter_id=ctx.author.id).all()
        pass

    @commands.command()
    async def votals(self, ctx: commands.Context, flag: Optional[str]):
        """
        View current vote standings.

        Use the --full flag to view who's voting for each candidate.
        """
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
