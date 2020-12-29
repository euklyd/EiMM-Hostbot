import asyncio
import pprint
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Generator, Tuple

import discord
import gspread
from discord.ext import commands
from sqlalchemy import create_engine, event, desc
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from gspread.exceptions import SpreadsheetNotFound

from cogs import interview_schema as schema
from core.bot import Bot
from utils import spreadsheet, utils

_DEBUG_FLAG = False  # Note: toggle to off when not testing

DB_DIR = 'databases'
DB_FILE = f'{DB_DIR}/interviews.db'


# For some awful reason, SQLite doesn't turn on foreign key constraints by default.
# This is the fix.
# TODO: Move this to a SQL utility file so it gets run globally every time :)
@event.listens_for(Engine, 'connect')
def set_sqlite_pragma(dbapi_connection, connection_record):
    # Some examples online would have you only run this if the SQLite version is high enough to
    # support foreign keys. That isn't a concern here. If your SQLite doesn't support foreign keys,
    # it can crash and burn.
    cursor = dbapi_connection.cursor()
    cursor.execute('PRAGMA foreign_keys=ON')
    cursor.close()


session_maker = None  # type: Optional[sessionmaker]

# Google sheets API constants
SCOPE = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]
SECRET = 'conf/google_creds.json'
SHEET_NAME = ''

SERVER_LEFT_MSG = '[Member Left]'
ERROR_MSG = '[Bad User]'


class Candidate:
    """
    Utility class, used only for votals.
    """

    def __init__(self, ctx: commands.Context, candidate_id: int):
        self._ctx = ctx
        self.candidate = ctx.guild.get_member(candidate_id)
        self.voters = []

    def str(self, length: int) -> str:
        return f'{_name_or_default(self.candidate) + ":" : <{length + 1}}'

    def voters_str(self) -> str:
        # Hopefully it should never fall through to default! Preprocessing strips those out.
        voters = [_name_or_default(self._ctx.guild.get_member(voter)) for voter in self.voters]
        voters = sorted(voters, key=lambda x: str(x).lower())
        return ', '.join(voters)

    def basic_str(self, length: int) -> str:
        return f'{self.str(length)} {len(self.voters)}'

    def full_str(self, length: int) -> str:
        return f'{self.str(length)} {len(self.voters)} ({self.voters_str()})'

    def sortkey(self) -> Tuple[int, str]:
        """
        Sort first by number of votes, then alphabetically.
        Votes are negative so that sorting by votes (greatest to least) can be consistent with sorting
        alphabetically (A to Z).
        """
        return -len(self.voters), _name_or_default(self.candidate).lower()


class Question:
    def __init__(self, interviewee: discord.Member, asker: Union[discord.Member, discord.User],
                 question: str, question_num: int, server_id: int, channel_id: int, message_id: int,
                 answer: str = None, timestamp: datetime = None):
        self.interviewee = interviewee
        self.asker = asker
        self.question = question
        self.question_num = question_num
        self.server_id = server_id
        self.channel_id = channel_id
        self.message_id = message_id

        self.answer = answer
        if timestamp is None:
            self.timestamp = datetime.utcnow()
        else:
            self.timestamp = timestamp

    @property
    def jump_url(self) -> str:
        return f'https://discordapp.com/channels/{self.server_id}/{self.channel_id}/{self.message_id}'

    @staticmethod
    async def from_row(ctx: commands.Context, row: Dict[str, Any]) -> 'Question':
        """
        Translates a row from the Google sheet to an object.
        """
        channel = ctx.bot.get_channel(row['Channel ID'])  # type: discord.TextChannel

        asker = ctx.guild.get_member(row['ID'])
        if asker is None:
            asker = await ctx.bot.fetch_user(row['ID'])
            if _DEBUG_FLAG:
                print(f"couldn't find member with ID {row['ID']}, instead fetched user {asker}")

        return Question(
            # This is a bit dangerous, but should be fine! only the interviewee will be calling the answer method:
            interviewee=ctx.author,
            asker=asker,
            question=row['Question'],
            question_num=row['#'],
            server_id=row['Server ID'],
            channel_id=row['Channel ID'],
            message_id=row['Message ID'],
            answer=str(row['Answer']),
            timestamp=datetime.utcfromtimestamp(row['POSIX Timestamp']),
        )

    def to_row(self, ctx: commands.Context) -> list:
        """
        Convert this Question to a row for uploading to Sheets.
        """
        session = session_maker()
        server = session.query(schema.Server).filter_by(id=ctx.guild.id).one_or_none()
        if server is None:
            raise ValueError('No server found on this guild.')
        return [
            self.timestamp.strftime('%m/%d/%Y %H:%M:%S'),
            self.timestamp.timestamp(),
            str(self.asker),
            str(self.asker.id),
            self.question_num,
            self.question,
            '',  # no answer when uploading
            False,
            str(self.server_id),
            str(self.channel_id),
            str(self.message_id),
            # str(self.message.guild.id),
            # str(self.message.channel.id),
            # str(self.message.id),
        ]

    @staticmethod
    def upload_many(ctx: commands.Context, connection: spreadsheet.SheetConnection, questions: List['Question']):
        """
        Upload a list of Questions to a spreadsheet.

        This would normally be a normal method, but there's a separate command (append_rows vs append_row) for
        bulk upload, and we need to use that to dodge Sheets API rate limits.
        """
        session = session_maker()
        server = session.query(schema.Server).filter_by(id=ctx.guild.id).one_or_none()

        rows = [q.to_row(ctx) for q in questions]
        sheet = connection.get_sheet(server.sheet_name).sheet1
        sheet.append_rows(rows)

    @staticmethod
    def _generate_words(text: str) -> Generator[str, None, None]:
        words = text.replace('[', '\\[').replace(']', '\\]').split(' ')
        for word in words:
            while len(word) > 900:
                yield word[:900]
                word = word[900:]
            yield word

    def question_words(self) -> Generator[str, None, None]:
        """
        Add angle braces as quote styling *after* this method.
        """
        # words = self.question.replace('[', '\\[').replace(']', '\\]').split(' ')
        # for word in words:
        #     while len(word) > 900:
        #         yield word[:900]
        #         word = word[900:]
        #     yield word
        return self._generate_words(self.question)

    def answer_words(self) -> Generator[str, None, None]:
        """
        Add angle braces as quote styling *after* this method.
        """
        # words = self.answer.replace('[', '\\[').replace(']', '\\]').split(' ')
        # for word in words:
        #     while len(word) > 900:
        #         yield word[:900]
        #         word = word[900:]
        #     yield word
        return self._generate_words(self.answer)


class InterviewEmbed(discord.Embed):
    @staticmethod
    def blank(interviewee: discord.Member, asker: Union[discord.Member, discord.User],
              avatar_url: str = None) -> 'InterviewEmbed':
        if avatar_url is None:
            avatar_url = interviewee.avatar_url
        em = InterviewEmbed(
            title=f"**{interviewee}**'s interview",
            description=' ',
            color=interviewee.color,
        )
        em.set_thumbnail(url=avatar_url)
        em.set_author(
            name=f'Asked by {asker}',
            icon_url=asker.avatar_url,
        )
        # +100 length as a buffer for the metadata fields
        em.length = len(f"**{interviewee}**'s interview" + ' ' + f'Asked by {asker}') + len(asker.avatar_url) + 100
        return em


def _name_or_default(user: discord.User) -> str:
    if user is not None:
        return str(user)
    return SERVER_LEFT_MSG


# def translate_name(member: Union[discord.Member, discord.User]):
#     if member is None:
#         return SERVER_LEFT_MSG
#     if type(member) is discord.User:
#         return member.name
#     if type(member) is discord.Member:
#         return member.nick
#     return ERROR_MSG


# def message_link(server_id: int, channel_id: int, message_id: int) -> str:
#     return f'https://discordapp.com/channels/{server_id}/{channel_id}/{message_id}'


def add_question(em: discord.Embed, question: Question, current_length: int) -> int:
    """
    Questions and answers are added to embed fields, each of which has a maximum of 1000 chars.
    Need to check (and possibly split up) each question and answer to make sure they don't overflow and break
    the embed. This is... somewhat frustrating.

    Return length of question/answer strings added, or error codes:
    -1 if the total is too long
    -2 if this one question is too long
    """
    text_length = 0

    question_text = question.question.replace('[', '\\[').replace(']', '\\]')
    question_lines = [line.strip() for line in question_text.split('\n')]

    # Sum of all text in all lines PLUS accounting for adding '> ' and '\n' to each line PLUS the question's answer:
    # When splitting up questions, assume 85 (round to 100) characters for the message link markdown, so you get 900
    # chars rather than 1000.
    if sum([len(line) for line in question_lines]) + len(question_lines) * 3 + len(question.answer) <= 900:
        # formatted_question_text = f'[> {"> ".join(question_lines)}]({question.message.jump_url})'
        formatted_question_text = f'[> {"> ".join(question_lines)}]({question.jump_url})'
        text_length = len(f'Question #{question.question_num}') + len(f'{formatted_question_text}\n{question.answer}')
        if text_length > 4800:
            return -2
        if current_length + text_length > 4800:
            return -1
        em.add_field(
            name=f'Question #{question.question_num}',
            value=f'{formatted_question_text}\n{question.answer}',
            inline=False,
        )
        return text_length

    # Need to split and add to separate fields:

    if len(question.question) + len(question.answer) > 4700:
        # I'm far too lazy to calculate exactly, but this should be safe enough
        return -2
    if current_length + len(question.question) + len(question.answer) > 4700:
        return -1

    question_chunk = '[> '
    question_chunks = []
    for word in question.question_words():
        if len(question_chunk + word) > 900:
            # question_chunk += f']({question.message.jump_url})'
            question_chunk += f']({question.jump_url})'
            question_chunks.append(question_chunk)
            question_chunk = '[> '
        word = word.replace("\n", "\n> ")
        question_chunk += f'{word}' + ' '
    # question_chunk += f']({question.message.jump_url})'
    question_chunk += f']({question.jump_url})'
    question_chunks.append(question_chunk)

    for i, chunk in enumerate(question_chunks):
        if len(question_chunks) > 1:
            name = f'Question #{question.question_num} [{i + 1}/{len(question_chunks)}]'
        else:
            name = f'Question #{question.question_num}'
        em.add_field(name=name, value=chunk, inline=False)
        text_length += len(name) + len(chunk)

    answer_chunk = ''
    answer_chunks = []
    for word in question.answer_words():
        if len(answer_chunk + word) > 950:
            answer_chunks.append(answer_chunk)
            answer_chunk = ''
        answer_chunk += word + ' '
    answer_chunks.append(answer_chunk)

    for i, chunk in enumerate(answer_chunks):
        if len(answer_chunks) > 1:
            name = f'Answer #{question.question_num} [{i + 1}/{len(answer_chunks)}]'
        else:
            name = f'Answer #{question.question_num}'
        em.add_field(name=name, value=chunk, inline=False)
        text_length += len(name) + len(chunk)

    return text_length


def _server_active(ctx: commands.Context):
    """
    Exposed so that it can be checked in help commands.
    """
    session = session_maker()
    server = session.query(schema.Server).filter_by(id=ctx.guild.id).one_or_none()
    return server is not None


def _ck_server_active():
    """
    Command check to make sure the server is set up for interviews.
    """

    async def predicate(ctx: commands.Context):
        if ctx.guild is None:
            return False
        if _DEBUG_FLAG:
            return True
        active = _server_active(ctx)
        if not active and not ctx.message.content.startswith(ctx.prefix + 'help'):
            await ctx.send('Server is not set up for interviews.')
            await ctx.message.add_reaction(ctx.bot.redtick)
        return active

    return commands.check(predicate)


def _ck_interview_enabled():
    """
    Command check to make sure the interview is not disabled.

    Checked when voting, opting in or out, and asking questions.
    """

    async def predicate(ctx: commands.Context):
        if ctx.guild is None:
            return False
        session = session_maker()
        result = session.query(schema.Server).filter_by(id=ctx.guild.id, active=True).one_or_none()
        if result is None and not ctx.message.content.startswith(ctx.prefix + 'help'):
            await ctx.send('Interviews are currently disabled.')
            await ctx.message.add_reaction(ctx.bot.redtick)
        return result is not None

    return commands.check(predicate)


def _ck_is_interviewee():
    """
    Command check to make sure the invoker is the interviewee.

    Checked when answering questions.
    """

    async def predicate(ctx: commands.Context):
        if ctx.guild is None:
            return False
        session = session_maker()
        result = session.query(schema.Interview).filter_by(server_id=ctx.guild.id, interviewee_id=ctx.author.id,
                                                           current=True).one_or_none()
        if result is None and not ctx.message.content.startswith(ctx.prefix + 'help'):
            await ctx.send(f'**{ctx.author}**, you are not the interviewee.')
            await ctx.message.add_reaction(ctx.bot.redtick)
        return result is not None

    return commands.check(predicate)


class Interview(commands.Cog):
    """
    Runs member interviews, interfaced with Google Sheets as a GUI.

    Instructions:

    1. Clone this sheet and rename it for your server:
    https://docs.google.com/spreadsheets/d/1cC3YtXrXlykd6vfI5Q6y1sw8EGH9walpidZB4BJKTbw/edit?usp=sharing

    2. Share it with this bot's credentialed email (ask the bot owner for it, I'm not uploading it to github).
    (You can query this with the command `iv` if it's been set up in the configuration file.)

    3. Run the command `iv setup #answer_channel #question_channel sheet_name`.

    4. Run the command `iv enable` to open voting.

    5. Once you decide voting is ended, run the command `iv next @vote_winner`.

    6. Share the sheet with the winner, hide old sheet pages, and let them get to answering.

    Note: Most commands are not displayed unless your server is set up for interviews.
    """

    def __init__(self, bot: Bot):
        self.bot = bot
        self.connection = None  # type: Optional[spreadsheet.SheetConnection]
        self.load()

    def load(self):
        self.connection = spreadsheet.SheetConnection(SECRET, SCOPE)

        if not Path(DB_FILE).exists():
            # Note: Don't technically need this condition, but it adds a bit of clarity, so keeping it in for now.
            Path(DB_DIR).mkdir(exist_ok=True)
        engine = create_engine(f'sqlite:///{DB_FILE}')
        global session_maker
        session_maker = sessionmaker(bind=engine)

        schema.Base.metadata.create_all(engine)

    # == Helper methods ==

    @staticmethod
    def _generate_embeds(interviewee: discord.Member, interview: schema.Interview, questions: List[Question],
                         avatar_url: str = None) -> List[Union[discord.Embed, Question]]:
        """
        Generate a list of discord.Embeds to be posted from a list of Questions.
        """
        if avatar_url is None:
            avatar_url = interviewee.avatar_url

        n_answered = 0
        n_asked = interview.questions_asked

        def finalize(final_em: discord.Embed):
            final_em.set_footer(text=f'{n_answered + interview.questions_answered} questions answered (of {n_asked})')
            return final_em

        length = 0

        def new_em(asker: discord.Member):
            if _DEBUG_FLAG:
                print('new blank em')
            nonlocal length
            length = 0
            return InterviewEmbed.blank(interviewee, asker, avatar_url=avatar_url)  # TODO: update avatar url?

        last_asker = None  # type: Optional[discord.Member]

        ls_embeds = []

        em = None  # type: Optional[discord.Embed]
        for question in questions:
            if _DEBUG_FLAG:
                print(f'generating {question.asker}-{question.question_num}')
            if last_asker != question.asker:
                # new asker, append old embed and make a new one
                if em is not None and len(em.fields) > 0:
                    ls_embeds.append(finalize(em))
                # make a new embed
                em = new_em(question.asker)

            # Add question/answer fields and count additional length.
            added_length = add_question(em, question, length)

            # Update answered questions per asker
            n_answered += 1
            if added_length == -1:
                # question wasn't added, append to list and retry
                if len(em.fields) > 0:
                    ls_embeds.append(finalize(em))
                em = new_em(question.asker)
                added_length = add_question(em, question, length)

            if added_length == -2:
                # question cannot be added, add an error
                ls_embeds.append(question)
            length += added_length
            last_asker = question.asker
        if em is not None:
            # yield the final embed
            if len(em.fields) > 0:
                ls_embeds.append(finalize(em))

        return ls_embeds

    # == Setup ==

    @commands.group(invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def iv(self, ctx: commands.Context):
        """
        Interview management commandgroup.
        """
        if _server_active(ctx):
            reply = f'Interviews are currently set up for {ctx.guild}; use `{ctx.bot.default_command_prefix}' \
                    f'help Interview` for more info.'
        else:
            reply = f'Interviews are not currently set up for {ctx.guild}; use `{ctx.bot.default_command_prefix}' \
                    f'help iv setup` for more info.\n' \
                    f'The Google service account email is `{ctx.bot.conf.google_email}`.\n' \
                    f'Use `{ctx.bot.default_command_prefix}help Interview` for setup instructions.'
        await ctx.send(reply)

    async def _check_sheet(self, ctx: commands.Context, sheet_name: str):
        """
        Check if the specified sheet name is legal.
        """
        session = session_maker()
        existing_server = session.query(schema.Server).filter_by(sheet_name=sheet_name).one_or_none()
        if existing_server is not None:
            await ctx.send(f'A sheet with the name `{sheet_name}` has already been registered, '
                           'please use a different one.')
            await ctx.message.add_reaction(ctx.bot.redtick)
            return False

        client = gspread.authorize(self.connection.creds)
        sheet_names = [sheet['name'] for sheet in client.list_spreadsheet_files()]
        # try:
        #     sheet = self.connection.get_sheet(sheet_name)
        # except SpreadsheetNotFound:
        #     await ctx.send(f"Spreadsheet `{sheet_name}` cannot be found, make sure it's been shared with the bot "
        #                    f"account (`{ctx.bot.conf.google_email}`) and try again.")
        #     await ctx.message.add_reaction(ctx.bot.redtick)
        #     return False

        if sheet_name not in sheet_names:
            await ctx.send(f"Spreadsheet `{sheet_name}` cannot be found, make sure it's been shared with the bot "
                           f"account (`{ctx.bot.conf.google_email}`) and try again.")
            await ctx.message.add_reaction(ctx.bot.redtick)
            return False

        return True

    @iv.command(name='setup')
    @commands.has_permissions(administrator=True)
    async def iv_setup(self, ctx: commands.Context, answers: discord.TextChannel,
                       backstage: discord.TextChannel, sheet_name: str,
                       default_question: str = 'Make sure to write an intro on stage before you start '
                                               'answering questions!'):
        """
        Set up the current server for interviews.

        Answer channel is where where answers to questions will be posted, backstage is a private space for
        the bot to be controlled, sheet_name is the URL of your interview sheet.
        If your sheet name is multiple words, enclose it in double quotes, e.g., "sheet name".
        Sheet names must be unique, first-come-first-served.

        Copy the sheet template from:
        https://docs.google.com/spreadsheets/d/1cC3YtXrXlykd6vfI5Q6y1sw8EGH9walpidZB4BJKTbw/edit?usp=sharing

        This command doesn't set up permissions, etc. for your channels, figure out how you want those to look
        on your own.
        """

        session = session_maker()

        existing_server = session.query(schema.Server).filter_by(id=ctx.guild.id).one_or_none()
        if existing_server is not None:
            await ctx.send('This server is already set up for interviews.')
            await ctx.message.add_reaction(ctx.bot.redtick)
            return

        if await self._check_sheet(ctx, sheet_name) is False:
            return

        server = schema.Server(
            id=ctx.guild.id,
            sheet_name=sheet_name,
            default_question=default_question,
            answer_channel=answers.id,
            back_channel=backstage.id,
            limit=datetime.utcfromtimestamp(0),
            reinterviews_allowed=False,
            active=False,
        )
        session.add(server)
        session.commit()
        await ctx.send(f'Set up {ctx.guild} for interviews.\n'
                       f'Answers will be posted in {answers}, hidden channel is {backstage}.')
        await ctx.message.add_reaction(ctx.bot.greentick)

    @iv.command(name='next')
    @commands.has_permissions(administrator=True)
    @_ck_server_active()
    async def iv_next(self, ctx: commands.Context, interviewee: discord.Member, *, email: Optional[str] = None):
        """
        Set up the next interview for <interviewee>.

        Creates a new interview sheet for the next interviewee. If the optional <email> parameter is provided,
        shares the document with them. Old emails must still be cleared out manually.
        """

        # set the old interview row to be not-current
        session = session_maker()
        old_interview = session.query(schema.Interview).filter_by(server_id=ctx.guild.id,
                                                                  current=True).one_or_none()  # type: schema.Interview
        if old_interview is not None:
            # if old_interview doesn't exist that just means it's the first interview!
            old_interview.current = False
            server = old_interview.server
        else:
            server = session.query(schema.Server).filter_by(id=ctx.guild.id).one_or_none()

        timestamp = datetime.utcnow()
        sheet_name = f'{interviewee.name} [{interviewee.id}]-{timestamp.timestamp()}'

        # Create new schema.Interview & add it do database

        new_interview = schema.Interview(
            server_id=ctx.guild.id,
            interviewee_id=interviewee.id,
            start_time=timestamp,
            sheet_name=sheet_name,
            questions_asked=1,  # Starts at 1 for the default question
            questions_answered=0,
            current=True,
        )
        session.add(new_interview)

        # Make & clear a new sheet page

        interview_sheet = self.connection.get_sheet(server.sheet_name)
        old_sheet = interview_sheet.sheet1
        new_sheet = old_sheet.duplicate(
            insert_sheet_index=0,
            new_sheet_name=sheet_name
        )
        new_sheet.insert_row(
            [
                timestamp.strftime('%m/%d/%Y %H:%M:%S'),
                timestamp.timestamp(),
                str(ctx.bot.user),
                str(ctx.bot.user.id),
                1,
                server.default_question,
                '',
                False,
                str(ctx.guild.id),
                str(ctx.channel.id),
                str(ctx.message.id),
            ],
            index=2,
        )
        new_sheet.resize(rows=2)

        if email is not None:
            interview_sheet.share(email, perm_type='user', role='writer')

        channel = ctx.guild.get_channel(server.answer_channel)
        op_msg = await self._votals_in_channel(ctx, flag=None, channel=channel)
        new_interview.op_channel_id = op_msg.channel.id
        new_interview.op_message_id = op_msg.id

        session.query(schema.Vote).filter_by(server_id=ctx.guild.id).delete()

        # Open the interview up for votes, questions, etc.
        server.active = True

        # Only commit after the new page is up and old votes are deleted.
        session.commit()

        await ctx.message.add_reaction(ctx.bot.greentick)
        await asyncio.sleep(2)
        await ctx.send(f'{ctx.author.mention}, make sure to update the table of contents!')

    @iv.command(name='settings')
    @commands.has_permissions(administrator=True)
    @_ck_server_active()
    async def iv_settings(self, ctx: commands.Context):
        """
        Check current settings for this server's interviews.
        """
        session = session_maker()
        server = session.query(schema.Server).filter_by(id=ctx.guild.id).one_or_none()  # type: schema.Server
        answer = ctx.guild.get_channel(server.answer_channel)
        backstage = ctx.guild.get_channel(server.back_channel)
        em = discord.Embed(title=f'{ctx.guild} interview settings', color=ctx.bot.user.color)

        em.add_field(name='Answer channel', value=f'{answer.mention}')
        em.add_field(name='Backstage channel', value=f'{backstage.mention}')
        em.add_field(name='Sheet name', value=f'{server.sheet_name}')
        em.add_field(name='Default question', value=f'{server.default_question}')
        em.add_field(name='Reinterview limit', value=f'{server.limit}')
        await ctx.send(embed=em)

    @iv.command(name='overwrite')
    @commands.is_owner()
    @_ck_server_active()
    async def iv_overwrite(self, ctx: commands.Context):
        """
        TODO: Manually overwrite certain parts of the database.
        """
        pass

    @iv.command(name='recount')
    @commands.is_owner()
    @_ck_server_active()
    async def iv_recount(self, ctx: commands.Context):
        """
        TODO: Update metadata for the current interview as possible from the sheet.
        """
        session = session_maker()
        interview = session.query(schema.Interview).filter_by(server_id=ctx.guild.id, current=True).one_or_none()
        old_count = interview.questions_answered
        old_total = interview.questions_asked

        sheet = self.connection.get_sheet(interview.server.sheet_name).sheet1
        count = 0
        records = sheet.get_all_records()
        for record in records:
            if record['Posted?'] == 'TRUE':
                count += 1
        interview.questions_answered = count
        interview.questions_asked = len(records)
        session.commit()

        await ctx.message.add_reaction(ctx.bot.greentick)
        await ctx.send(f'Old count: {old_count}\nNew count: {count}')
        await ctx.send(f'Old total: {old_total}\nNew total: {len(records)}')

    @iv.command(name='channel')
    @commands.has_permissions(administrator=True)
    @_ck_server_active()
    async def iv_channel(self, ctx: commands.Context, channel_type: str, channel: discord.TextChannel):
        """
        Change saved answer/question channels.

        channel_type must be 'answer' or 'backstage'.
        """
        session = session_maker()
        server = session.query(schema.Server).filter_by(id=ctx.guild.id).one_or_none()
        answer = ctx.guild.get_channel(server.answer_channel)
        backstage = ctx.guild.get_channel(server.back_channel)
        if channel_type.lower() == 'answer':
            server.answer_channel = channel.id
            session.commit()
            await ctx.message.add_reaction(ctx.bot.greentick)
        elif channel_type.lower() == 'backstage':
            server.back_channel = channel.id
            session.commit()
            await ctx.message.add_reaction(ctx.bot.greentick)
        else:
            await ctx.send(f'The only channels to set up are the `answer` ({answer.mention}) and '
                           f'`backstage` ({backstage.mention}) channels.')
            await ctx.message.add_reaction(ctx.bot.redtick)

    @iv.command(name='sheet')
    @commands.has_permissions(administrator=True)
    @_ck_server_active()
    async def iv_sheet(self, ctx: commands.Context, sheet_name: str = None):
        """
        Change saved sheet name.

        If no sheet name specified, prints the current name.
        """
        if sheet_name is not None and await self._check_sheet(ctx, sheet_name) is False:
            return

        session = session_maker()
        server = session.query(schema.Server).filter_by(id=ctx.guild.id).one_or_none()
        if sheet_name is None:
            await ctx.send(f'The current interview sheet name is `{server.sheet_name}`.')
            return
        server.sheet_name = sheet_name
        session.commit()
        await ctx.message.add_reaction(ctx.bot.greentick)

    @iv.command(name='disable')
    @commands.has_permissions(administrator=True)
    @_ck_server_active()
    async def iv_disable(self, ctx: commands.Context):
        """
        Disable voting and question asking for the current interview.
        """
        session = session_maker()
        server = session.query(schema.Server).filter_by(id=ctx.guild.id).one_or_none()
        if server is None:
            await ctx.send(f'Interviews are not set up for {ctx.guild}.')
            await ctx.message.add_reaction(ctx.bot.redtick)
            return
        if server.active is False:
            await ctx.send(f'Interviews are already disabled.')
            await ctx.message.add_reaction(ctx.bot.redtick)
            return
        server.active = False
        session.commit()
        await ctx.message.add_reaction(ctx.bot.greentick)

    @iv.command(name='enable')
    @commands.has_permissions(administrator=True)
    @_ck_server_active()
    async def iv_enable(self, ctx: commands.Context):
        """
        Re-enable voting and question asking for the current interview.
        """
        session = session_maker()
        server = session.query(schema.Server).filter_by(id=ctx.guild.id).one_or_none()
        if server is None:
            await ctx.send(f'Interviews are not set up for {ctx.guild}.')
            await ctx.message.add_reaction(ctx.bot.redtick)
            return
        if server.active is True:
            await ctx.send(f'Interviews are already enabled.')
            await ctx.message.add_reaction(ctx.bot.redtick)
            return
        server.active = True
        session.commit()
        await ctx.message.add_reaction(ctx.bot.greentick)

    @iv.command(name='limit')
    @commands.has_permissions(administrator=True)
    @_ck_server_active()
    async def iv_limit(self, ctx: commands.Context, date: str = None):
        """
        Set the new reinterview limit (YYYY/MM/DD).

        Only reinterviews whose most recent interview is before the specified date will be allowed.
        (I'm lazy, if you want to disable reinterviews, just set it to like, the year 2000.)

        If no date specified, prints the current limit.
        """
        session = session_maker()
        server = session.query(schema.Server).filter_by(id=ctx.guild.id).one_or_none()
        if date is None:
            await ctx.send(f'The current reinterview limit is `{server.limit.strftime("%Y/%m/%d")}`.')
            return
        server.limit = datetime.strptime(date, '%Y/%m/%d')
        session.commit()
        await ctx.message.add_reaction(ctx.bot.greentick)

    @iv.command(name='stats')
    @_ck_server_active()
    async def iv_stats(self, ctx: commands.Context, member: Optional[discord.Member]):
        """
        View interview-related stats.

        If no user specified, view stats for the current interview.
        """
        session = session_maker()
        interview = session.query(schema.Interview).filter_by(server_id=ctx.guild.id,
                                                              current=True).one_or_none()  # type: schema.Interview
        if member is None:
            if interview is None:
                await ctx.send('There is no currently ongoing interview.')
                return
            interviewee = ctx.guild.get_member(interview.interviewee_id)
            past_interviews = session.query(schema.Interview).filter_by(
                server_id=ctx.guild.id, interviewee_id=interview.interviewee_id).all()  # type: List[schema.Interview]

            # view general stats
            em = discord.Embed(
                title=f"{interviewee}'s interview",
                color=interviewee.color,
            )
            em.set_thumbnail(url=interviewee.avatar_url)
            if len(past_interviews) > 1:
                description = f"{interviewee}'s past interviews were:\n"
                for iv in past_interviews:
                    url = utils.jump_url(iv.server_id, iv.op_channel_id, iv.op_message_id)
                    description += f'• [{iv.start_time}]({url}): {iv.questions_answered} out of {iv.questions_asked}\n'
            else:
                description = f"This is {interviewee}'s first interview!"
            em.description = description
            em.add_field(name='Questions asked', value=str(interview.questions_asked))
            em.add_field(name='Questions answered', value=str(interview.questions_answered))
            em.set_footer(text=f'Interview started on {interview.start_time}')
            await ctx.send(embed=em)
            return

        past_interviews = session.query(schema.Interview).filter_by(
            server_id=ctx.guild.id, interviewee_id=member.id).all()  # type: List[schema.Interview]

        em = discord.Embed(
            title=f'Interview stats for {member}',
            color=member.color,
        )
        if len(past_interviews) > 0:
            description = f"{member}'s past interviews were:\n"
            for iv in past_interviews:
                url = utils.jump_url(iv.server_id, iv.op_channel_id, iv.op_message_id)
                description += f'• [{iv.start_time}]({url}): {iv.questions_asked} out of {iv.questions_asked}\n'
            em.description = description
        em.set_thumbnail(url=member.avatar_url)
        if interview is None:
            # No questions could have been asked if there's no current interview
            await ctx.send(embed=em)
            return
        current_qs = session.query(schema.Asker).filter_by(interview_id=interview.id, asker_id=member.id).one_or_none()
        if current_qs is None:
            # hasn't asked questions
            current_qs = 0
        else:
            current_qs = current_qs.num_questions
        ls_past_qs = session.query(schema.Asker).filter_by(asker_id=member.id).all()
        past_qs = 0
        for asker in ls_past_qs:
            past_qs += asker.num_questions

        em.add_field(name='Questions asked this interview', value=str(current_qs))
        em.add_field(name='Questions total', value=str(past_qs))
        await ctx.send(embed=em)

    # == Questions ==

    async def _ask_many(self, ctx: commands.Context, question_strs: List[str]):
        """
        Ask a bunch of questions at once. Or just one. Either way, use the batch upload command rather than
        doing it one at a time.
        """
        session = session_maker()
        interview = session.query(schema.Interview).filter_by(current=True,
                                                              server_id=ctx.guild.id).one_or_none()  # type: Optional[schema.Interview]
        interviewee = ctx.guild.get_member(interview.interviewee_id)
        if interviewee is None:
            await ctx.send(f"Couldn't find server member `{interview.interviewee_id}`.")
            return

        asker_meta = None
        for asker in interview.askers:
            if asker.asker_id == ctx.author.id:
                asker_meta = asker
        if asker_meta is None:
            asker_meta = schema.Asker(interview_id=interview.id, asker_id=ctx.author.id, num_questions=0)
            session.add(asker_meta)

        questions = []
        for question_str in question_strs:
            q = Question(
                interviewee=interviewee,
                asker=ctx.author,
                question=question_str,
                question_num=asker_meta.num_questions + 1,
                server_id=ctx.guild.id,
                channel_id=ctx.channel.id,
                message_id=ctx.message.id,
                # message=ctx.message,
                # answer=,  # unfilled, obviously
                timestamp=datetime.utcnow(),
            )

            questions.append(q)

            asker_meta.num_questions += 1
            interview.questions_asked += 1

        Question.upload_many(ctx, self.connection, questions)

        session.commit()

        desc = '\n'.join(question_strs)[:1900] + '...' if len('\n'.join(question_strs)) > 1900 else '\n'.join(
            question_strs)[0:1900]
        em = discord.Embed(
            title=f"**{interviewee}**'s interview",
            description=desc,
            color=ctx.bot.user.color,
        )
        em.set_author(
            name=f'New question from {ctx.author}',
            icon_url=ctx.author.avatar_url,
        )
        backstage = ctx.guild.get_channel(interview.server.back_channel)
        if backstage is None:
            await ctx.send(f'Backstage channel `{interview.server.back_channel}` not found for this server.')
        await backstage.send(embed=em)

        await ctx.message.add_reaction(ctx.bot.greentick)

    @commands.command()
    @_ck_server_active()
    @_ck_interview_enabled()
    async def ask(self, ctx: commands.Context, *, question_str: str):
        """
        Submit a question for the current interview.
        """
        await self._ask_many(ctx, [question_str])

    @commands.command()
    @_ck_server_active()
    @_ck_interview_enabled()
    async def mask(self, ctx: commands.Context, *, questions_str: str):
        """
        Submit multiple questions for the current interview.

        Each question must be a single line, separated by linebreaks. If you want multi-line single questions,
        use the 'ask' command.
        """
        await self._ask_many(ctx, questions_str.split('\n'))

    # == Answers ==

    async def _channel_answer(self, ctx: commands.Context, channel: discord.TextChannel):
        """
        Command wrapped by Interview.answer() and Interview.preview(). Greedily dumps as many answered questions
        into embeds as possible, and posts them to the specified channel.
        """
        preview_flag = False
        if channel == ctx.channel:
            preview_flag = True

        session = session_maker()
        server = session.query(schema.Server).filter_by(id=ctx.guild.id).one_or_none()  # type: schema.Server
        interview = session.query(schema.Interview).filter_by(server_id=ctx.guild.id,
                                                              current=True).one_or_none()  # type: schema.Interview
        interviewee = ctx.guild.get_member(interview.interviewee_id)
        sheet = self.connection.get_sheet(server.sheet_name).sheet1

        if _DEBUG_FLAG:
            print('fetching records')
        rows = sheet.get_all_records()
        if _DEBUG_FLAG:
            print('records fetched')

        filtered_rows = []
        filtered_cells = []
        for i, row in enumerate(rows):
            if row['Answer'] is not None and row['Answer'] != '' and row['Posted?'] == 'FALSE':
                filtered_rows.append(row)
                filtered_cells.append({
                    'range': f'H{i + 2}',
                    'values': [[True]]
                })

        if _DEBUG_FLAG:
            print('filtered cells')

        # Note: Useful debug output, not convinced this is perfect yet.
        # print('\n=== raw rows ===\n')
        # pprint.pprint(len(rows))
        # print(f'\n=== filtered ({len(filtered_rows)}) ===\n')
        # pprint.pprint(filtered_rows)

        questions = [await Question.from_row(ctx, row) for row in filtered_rows]
        if _DEBUG_FLAG:
            print('converted to questions')
            for q in questions:
                print(q.asker, q.question_num)

        if len(questions) == 0:
            await ctx.send('No new questions to be answered.')
            return

        n_sent = 0
        embeds = Interview._generate_embeds(interviewee=interviewee, interview=interview, questions=questions)
        if _DEBUG_FLAG:
            print(len(embeds))
            for e in embeds:
                print(type(e))
        for embed in embeds:
            if type(embed) is Question:
                # question was too long
                await channel.send(f"Question #{embed.question_num} or its answer from {embed.asker} was too long "
                                   f"to embed, please split it up and answer it manually.")
            else:
                await channel.send(embed=embed)
                n_sent += 1
                if _DEBUG_FLAG:
                    print(f'sent {n_sent} answer embeds')
        if _DEBUG_FLAG:
            print('done sending answers')

        if preview_flag is True:
            return

        # Update sheet and metadata if not previewing:
        sheet.batch_update(filtered_cells)
        interview.questions_answered += len(questions)
        session.commit()

    @commands.command()
    @_ck_server_active()
    @_ck_is_interviewee()
    async def answer(self, ctx: commands.Context):
        """
        Post all answers to questions that have not yet been posted.

        Questions posted in chronological order, grouped by asker. If an answer is too long to be posted,
        the interviewee may have to post it manually.
        """
        session = session_maker()
        server = session.query(schema.Server).filter_by(id=ctx.guild.id).one_or_none()  # type: schema.Server
        channel = ctx.guild.get_channel(server.answer_channel)

        try:
            await self._channel_answer(ctx, channel)
        except Exception as e:
            # this is bad practice but i don't know what the error is; it'll be removed later
            await ctx.message.add_reaction(ctx.bot.redtick)
            print(f"hey here's that error you're looking for at {datetime.utcnow()}")
            print(type(e))
            raise e
        await ctx.message.add_reaction(ctx.bot.greentick)

    @commands.command()
    @_ck_server_active()
    @_ck_is_interviewee()
    async def preview(self, ctx: commands.Context):
        """
        Preview answers, visible in the backstage channel.
        """
        await self._channel_answer(ctx, ctx.channel)
        await ctx.message.add_reaction(ctx.bot.greentick)

    async def _imganswer(self, ctx: commands.Context, row_num: int, url: str, channel: discord.TextChannel):
        preview_flag = False
        if channel == ctx.channel:
            preview_flag = True

        session = session_maker()
        server = session.query(schema.Server).filter_by(id=ctx.guild.id).one_or_none()  # type: schema.Server
        interview = session.query(schema.Interview).filter_by(server_id=ctx.guild.id,
                                                              current=True).one_or_none()  # type: schema.Interview
        interviewee = ctx.guild.get_member(interview.interviewee_id)
        sheet = self.connection.get_sheet(server.sheet_name).sheet1

        row = sheet.row_values(row_num)  # List[Any]

        asker = ctx.guild.get_member(row[3])
        if asker is None:
            asker = await ctx.bot.fetch_user(row[3])
        em = InterviewEmbed.blank(interviewee, asker)

        n_answered = 1
        n_asked = interview.questions_asked

        question = Question(interviewee=interviewee, asker=asker, question=row[5], question_num=row[4],
                            server_id=row[8], channel_id=row[9], message_id=row[10], answer=row[6], timestamp=row[1])
        add_question(em, question, 0)  # we're not checking length here
        em.set_footer(text=f'{n_answered + interview.questions_answered} questions answered (of {n_asked})')
        em.set_image(url=url)

        if not preview_flag:
            interview.questions_answered += 1
            sheet.update_acell(f'H{row_num}', True)
            session.commit()

        await channel.send(embed=em)

    @commands.command()
    @_ck_server_active()
    @_ck_is_interviewee()
    async def imganswer(self, ctx: commands.Context, row_num: int, url: str):
        """
        Answer a single question row with an added image.

        Use the row as indicated on the sheet sidebar.
        """
        session = session_maker()
        server = session.query(schema.Server).filter_by(id=ctx.guild.id).one_or_none()  # type: schema.Server
        channel = ctx.guild.get_channel(server.answer_channel)
        await self._imganswer(ctx, row_num, url, channel)

    # == Votes ==

    @staticmethod
    def _votes_footer(votes: List[discord.User], prefix: str = None):
        if len(votes) == 0:
            return f'_You are not currently voting; vote with `{prefix}vote`._'

        votes = sorted(votes, key=lambda x: _name_or_default(x).lower())
        return '_You are currently voting for: ' + ', '.join([f'`{_name_or_default(vote)}`' for vote in votes]) + '._'

    @staticmethod
    def _preprocess_votals(ctx: commands.Context, votes: List[schema.Vote]) -> List[Candidate]:
        """
        Returns a list of candidates and vote counts, sorted by (vote count, alphabetical name).
        """
        candidates = list(set(vote.candidate_id for vote in votes))
        votals = {}
        for candidate_id in candidates:
            votals[candidate_id] = Candidate(ctx, candidate_id)
            for vote in votes:
                if vote.candidate_id == candidate_id and ctx.guild.get_member(vote.voter_id) is not None:
                    votals[candidate_id].voters.append(vote.voter_id)

        return sorted(list(votals.values()), key=lambda x: x.sortkey())

    @staticmethod
    def _votals_text_basic(ctx: commands.Context, votes: List[schema.Vote]) -> str:
        votals = Interview._preprocess_votals(ctx, votes)
        text = ''
        max_name_length = len(SERVER_LEFT_MSG)
        for candidate in votals:
            if len(str(candidate)) > max_name_length:
                max_name_length = len(str(candidate.candidate))
        for candidate in votals:
            s = candidate.basic_str(max_name_length)
            if len(text) + len(s) > 1750:
                # Break if it's getting too long for a single message.
                text += '...\n'
                break
            text += s + '\n'

        return text

    @staticmethod
    def _votals_text_full(ctx: commands.Context, votes: List[schema.Vote]) -> str:
        votals = Interview._preprocess_votals(ctx, votes)
        text = ''
        max_name_length = len(SERVER_LEFT_MSG)
        for candidate in votals:
            if len(str(candidate)) > max_name_length:
                max_name_length = len(str(candidate.candidate))
        for candidate in votals:
            s = candidate.full_str(max_name_length)
            if len(text) + len(s) > 1750:
                # Break if it's getting too long for a single message.
                text += '...\n'
                break
            text += s + '\n'

        return text

    @commands.command()
    @_ck_server_active()
    @_ck_interview_enabled()
    async def vote(self, ctx: commands.Context, mentions: commands.Greedy[discord.Member]):
        """
        Vote for up to three nominees for the next interview.

        Voting rules:
        1. Cannot vote while interviews are disabled.
        2. Cannot vote for >3 people.
        3. Cannot vote for people who are opted out.
        4. Cannot vote for anyone who's been interviewed too recently.
        5. Cannot vote if you've joined the server since the start of the last interview.
        6. Cannot vote for bots, excepting HaruBot.
        7. Cannot vote for yourself.

        Rules are checked in order, so if you vote for five people, but the first three are illegal votes,
        none of your votes will count.
        """

        session = session_maker()
        iv_meta = session.query(schema.Interview).filter_by(server_id=ctx.guild.id, current=True).one_or_none()
        server = session.query(schema.Server).filter_by(id=ctx.guild.id).one_or_none()  # type: schema.Server

        # Note: Not completely confident in vote legality checking, so these checks are a living document.

        class VoteError:
            def __init__(self):
                self.opt_outs = []
                self.too_recent = []
                self.bots = []
                self.self = False
                self.too_many = []

            @property
            def is_error(self):
                return (len(self.opt_outs) > 0 or
                        len(self.too_recent) > 0 or
                        len(self.bots) > 0 or
                        len(self.too_many) > 0 or
                        self.self is True)

            async def send_errors(self):
                if not self.is_error:
                    return
                reply = 'The following votes were ignored:\n'
                if len(self.opt_outs) > 0:
                    reply += '• Opted out:' + ', '.join([f'`{v}`' for v in self.opt_outs]) + '.\n'
                if len(self.too_recent) > 0:
                    reply += '• Interviewed too recently: ' + ', '.join([f'`{v}`' for v in self.too_recent]) + '.\n'
                if len(self.bots) > 0:
                    reply += ('• As much as I would love to usher in the **Rᴏʙᴏᴛ Rᴇᴠᴏʟᴜᴛɪᴏɴ**, you cannot vote for '
                              'bots such as ' + ', '.join([f'`{v}`' for v in self.bots]) + '.\n')
                    bottag = discord.utils.get(ctx.bot.emojis, name='bottag')
                    if bottag:
                        await ctx.message.add_reaction(bottag)
                if self.self:
                    reply += '• Your **anti-town** self vote.\n'
                if len(self.too_many) > 0:
                    reply += ('• ' + ', '.join([f'`{v}`' for v in self.too_many]) + ' exceeded your limit of '
                                                                                    'three (3) votes.\n')
                await ctx.send(reply)

        vote_error = VoteError()

        # 1. Cannot vote while interviews are disabled.  (return immediately)
        # NOTE: Taken care of in command checks.
        # if not _interview_enabled(ctx):
        #     await ctx.send('Voting is currently **closed**; please wait for the next round to begin.')
        #     await ctx.message.add_reaction(ctx.bot.redtick)
        #     return

        # 2. Cannot vote for >3 people.
        if len(mentions) > 3:
            # await ctx.send('Vote for no more than three candidates. Additional votes are ignored.')
            # await ctx.message.add_reaction(ctx.bot.redtick)
            vote_error.too_many = mentions[3:]
            mentions = mentions[:3]
        elif len(mentions) < 1:
            await ctx.send('Vote at least one candidate.')
            await ctx.message.add_reaction(ctx.bot.redtick)
            return

        # 3. Cannot vote for people who are opted out.
        for mention in mentions:
            opted_out = session.query(schema.OptOut).filter_by(server_id=ctx.guild.id, opt_id=mention.id).one_or_none()
            if opted_out is not None:
                vote_error.opt_outs.append(mention)
        for mention in vote_error.opt_outs:
            mentions.remove(mention)

        # 4. Cannot vote for anyone who's been interviewed too recently.
        for mention in mentions:
            old = session.query(schema.Interview).filter_by(server_id=ctx.guild.id, interviewee_id=mention.id).order_by(
                desc('start_time')).first()  # type: schema.Interview
            if old and old.start_time > server.limit:
                vote_error.too_recent.append(mention)
        for mention in vote_error.too_recent:
            mentions.remove(mention)

        # 5. Cannot vote if you've joined the server since the start of the last interview.  (return immediately)
        if iv_meta is not None and ctx.author.joined_at > iv_meta.start_time:
            await ctx.send(f"Don't just rejoin servers only to vote, {ctx.author}, have some respect.")
            await ctx.message.add_reaction(ctx.bot.redtick)
            return

        # 6. Cannot vote for bots, excepting HaruBot.
        for mention in mentions:
            if mention.bot:
                vote_error.bots.append(mention)
        for mention in vote_error.bots:
            mentions.remove(mention)

        # 7. Cannot vote for yourself.
        if ctx.author in mentions:
            vote_error.self = True
            mentions.remove(ctx.author)

        old_votes = session.query(schema.Vote).filter_by(server_id=ctx.guild.id, voter_id=ctx.author.id).all()
        for vote in old_votes:
            session.delete(vote)
        votes = []
        for mention in mentions:
            votes.append(schema.Vote(server_id=ctx.guild.id, voter_id=ctx.author.id,
                                     candidate_id=mention.id, timestamp=datetime.utcnow()))
        session.add_all(votes)
        session.commit()

        if vote_error.is_error:
            await ctx.message.add_reaction(self.bot.redtick)
            await vote_error.send_errors()
        if len(mentions) > 0:
            # some votes went through
            await ctx.message.add_reaction(self.bot.greentick)

    @commands.command()
    @_ck_server_active()
    @_ck_interview_enabled()
    async def unvote(self, ctx: commands.Context):
        """
        Delete your current votes.
        """
        session = session_maker()
        session.query(schema.Vote).filter_by(server_id=ctx.guild.id, voter_id=ctx.author.id).delete()
        session.commit()
        await ctx.message.add_reaction(self.bot.greentick)

    @commands.command()
    @_ck_server_active()
    async def votes(self, ctx: commands.Context):
        """
        Check who you're voting for.
        """
        session = session_maker()
        votes = session.query(schema.Vote).filter_by(server_id=ctx.guild.id, voter_id=ctx.author.id).all()
        member_votes = [ctx.guild.get_member(vote.candidate_id) for vote in votes]

        response = self._votes_footer(member_votes, prefix=ctx.bot.default_command_prefix)
        await ctx.send(response)

    async def _votals_in_channel(self, ctx: commands.Context, flag: Optional[str] = None,
                                 channel: Optional[discord.TextChannel] = None) -> discord.Message:
        """
        The only reason this isn't votals() is because it also gets called by iv_next(), but that wants to place
        the votals reply in a different channel.
        """
        session = session_maker()
        votes = session.query(schema.Vote).filter_by(server_id=ctx.guild.id).all()

        # Filter only the invoker's own votes when generating the footer
        own_votes = [ctx.guild.get_member(vote.candidate_id) for vote in votes if vote.voter_id == ctx.author.id]
        footer = self._votes_footer(own_votes, prefix=ctx.bot.default_command_prefix)

        if flag is not None and '-f' in flag:
            # Do full votals.
            block_text = Interview._votals_text_full(ctx, votes)
            if block_text == '':
                block_text = """
                        _  /)
                       mo / )
                       |/)\)
                        /\_
                        \__|=
                       (    )
                       __)(__
                 _____/      \\_____
                |  _     ___   _   ||
                | | \     |   | \  ||
                | |  |    |   |  | ||
                | |_/     |   |_/  ||
                | | \     |   |    ||
                | |  \    |   |    ||
                | |   \. _|_. | .  ||
                |                  ||
                |  PenguinBot3000  ||
                |   2016 - 2020    ||
                |                  ||
        *       | *   **    * **   |**      **
         \))ejm97/.,(//,,..,,\||(,,.,\\,.((//"""

        else:
            # Do basic votals.
            block_text = Interview._votals_text_basic(ctx, votes)
            if block_text == '':
                block_text = ' '  # avoid the ini syntax highlighting breaking

        reply = f'**__Votals__**```ini\n{block_text}```{footer}\n'

        return await channel.send(reply)

    @commands.command()
    @_ck_server_active()
    async def votals(self, ctx: commands.Context, flag: Optional[str] = None):
        """
        View current vote standings.

        Use the --full flag to view who's voting for each candidate.
        """
        await self._votals_in_channel(ctx, flag=flag, channel=ctx.channel)

    @commands.group(invoke_without_command=True)
    @_ck_server_active()
    async def opt(self, ctx: commands.Context):
        """
        Manage opting into or out of interview voting.
        """
        await ctx.send('Opt into or out of interview voting. '
                       f'Use `{ctx.bot.default_command_prefix}help opt` for more info.')

    @opt.command(name='out')
    @_ck_server_active()
    @_ck_interview_enabled()
    async def opt_out(self, ctx: commands.Context):
        """
        Opt out of voting.

        When opting out, all votes for you are deleted.
        """
        session = session_maker()
        status = session.query(schema.OptOut).filter_by(server_id=ctx.guild.id, opt_id=ctx.author.id).one_or_none()
        if status is None:
            optout = schema.OptOut(server_id=ctx.guild.id, opt_id=ctx.author.id)
            session.add(optout)

            # null votes currently on this user
            session.query(schema.Vote).filter_by(server_id=ctx.guild.id, candidate_id=ctx.author.id).delete()

            session.commit()
            await ctx.message.add_reaction(ctx.bot.greentick)
            return
        await ctx.send('You are already opted out of interviews.')
        await ctx.message.add_reaction(ctx.bot.redtick)

    @opt.command(name='in')
    @_ck_server_active()
    @_ck_interview_enabled()
    async def opt_in(self, ctx: commands.Context):
        """
        Opt into voting.
        """
        session = session_maker()
        status = session.query(schema.OptOut).filter_by(server_id=ctx.guild.id, opt_id=ctx.author.id).one_or_none()
        if status is None:
            await ctx.send('You are already opted into interviews.')
            await ctx.message.add_reaction(ctx.bot.redtick)
            return
        session.delete(status)
        session.commit()
        await ctx.message.add_reaction(ctx.bot.greentick)
        return

    @opt.command(name='list')
    @_ck_server_active()
    async def opt_list(self, ctx: commands.Context):
        """
        Check who's opted out of interview voting.
        """
        session = session_maker()
        opts = session.query(schema.OptOut).filter_by(server_id=ctx.guild.id).all()
        cowards = [ctx.guild.get_member(opt.opt_id) for opt in opts]
        cowards = [coward for coward in cowards if coward is not None]
        cowards = sorted(cowards, key=lambda x: str(x).lower())
        if len(cowards) > 0:
            reply = '__**Opted-Out Users**__```ini\n'
        else:
            reply = '__**Opted-Out Users**__``` '
        reply += '\n'.join([str(coward) for coward in cowards])
        reply += '```_As they have opted-out, you cannot vote for any of these users for interviews._'
        await ctx.send(reply)


# TODO: Remove before release.
@commands.command()
@commands.is_owner()
async def populate(ctx: commands.Context, filename: str):
    """
    Populate Interview table from an existing JSON.

    'filename' should be located in the bot's base directory. Format is a list of dicts with the following fields:
    "interviewee_id": int,
    "start_time": posix timestamp,
    "server_id": int,
    "channel_id": int,
    "message_id": int,
    "sheet_name": "str",
    "current": bool,
    "questions_asked": int,
    "questions_answered": int
    """
    import json
    from datetime import timezone

    with open(filename, 'r') as fp:
        rows = json.load(fp)

    session = session_maker()
    ivs = []
    for row in rows:
        ts = row['start_time']
        timestamp = datetime.utcfromtimestamp(ts).replace(tzinfo=timezone.utc)
        iv = schema.Interview(
            server_id=row['server_id'],
            interviewee_id=row['interviewee_id'],
            start_time=timestamp,
            sheet_name=row['sheet_name'],
            questions_asked=row['questions_asked'],
            questions_answered=row['questions_answered'],
            current=False,
            op_channel_id=row['channel_id'],
            op_message_id=row['message_id'],
        )
        ivs.append(iv)
    session.add_all(ivs)
    session.commit()

    await ctx.message.add_reaction(ctx.bot.greentick)


def setup(bot: commands.Bot):
    bot.add_cog(Interview(bot))
    bot.add_command(populate)  # TODO: Remove before release.
