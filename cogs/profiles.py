import datetime
import re
from typing import List, Any

import discord
import gspread
import pycountry
from discord.ext import commands

from oauth2client.service_account import ServiceAccountCredentials

from core.bot import Bot
from utils import menu

SCOPE = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]
SECRET = 'conf/google_client_secret.json'
SHEET_NAME = 'EiMM Community Profiles'


class InputError(Exception):
    def __init__(self, bad_input: Any, message: str):
        self.input = bad_input
        self.message = message

    def __repr__(self):
        return f'InputError({self.input}, {self.message})'


def open_sheet(sheet_name: str) -> gspread.Spreadsheet:
    creds = ServiceAccountCredentials.from_json_keyfile_name(SECRET, SCOPE)
    client = gspread.authorize(creds)
    return client.open(sheet_name)


# class Sheet(gspread.Worksheet):
#     def headings(self):
#         return self.row_values(1)


class ProfileValidation:
    legal_pronouns = [
        'he/him/his',
        'she/her/hers',
        'they/them/theirs',
    ]
    legal_communities = [
        'Danmaku Paradise',
        'EpicMafia',
        'Hypixel Forums',
        'Mafia 451',
        'Mafia Universe',
        'MafiaScum',
        'Maidens of the Kaleidoscope',
        'Personality Cafe',
        'Phansite (Persona 5)',
        'Pokecommunity',
        'Pokemon Showdown',
        'Pokemon Showdown',
        'Realms Beyond',
        'Rivals of Aether',
        'Serenes Forest',
        'Smash World Forums',
        'SmashBoards',
        'Smogon',
        'Zelda Universe',
    ]
    legal_countries = [c.name for c in pycountry.countries]  # type: List[str]
    legal_age_ranges = [
        'Under 18',
        '18 to 24',
        '25 and over',
    ]

    @staticmethod
    def primary_name(name: str) -> str:
        return name

    @staticmethod
    def aka(names: str) -> str:
        return names

    @classmethod
    def pronouns(cls, pronouns: str) -> str:
        if pronouns is None or pronouns == '':
            return ''
        if pronouns not in cls.legal_pronouns:
            raise InputError(pronouns, "input not in allowed 'pronoun' values")
        return pronouns

    @classmethod
    def home_communities(cls, communities: List[str]) -> List[str]:
        if communities is None or communities == []:
            return []
        for community in communities:
            if community not in cls.legal_communities:
                raise InputError(community, "input not in allowed 'community' values")
        return communities

    @classmethod
    def country(cls, country: str) -> str:
        if country is None or country == '':
            return ''
        if country not in cls.legal_countries:
            raise InputError(country, "input not in 'country' values")
        return country

    @classmethod
    def offset(cls, timezone: str) -> str:
        matches = re.search(r'([-+])(\d{1,2}):(\d{2})', timezone)
        if matches is None:
            raise InputError(timezone, "input has an invalid timezone offset format")
        plus_minus = matches.group(1)
        hour = matches.group(2)
        minutes = matches.group(3)
        if minutes not in ['00', '15', '30', '45']:
            raise InputError(timezone, "input not a valid timezone offset")
        return f'UTC{plus_minus}{hour:>02}:{minutes}'

    @staticmethod
    def birthday_year(birthday: str) -> datetime.datetime:
        matches = re.match(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', birthday)
        if matches is None:
            raise InputError(birthday, "input has an invalid date format")
        try:
            year = int(matches.group(1))
            month = int(matches.group(2))
            day = int(matches.group(3))
            date = datetime.datetime(year=year, month=month, day=day)
        except ValueError:
            raise InputError(birthday, "input is not a valid date")

        return date

    @staticmethod
    def birthday_day(birthday: str) -> str:
        """
        dear god it's MM/DD not DD/YY @sb
        """
        matches = re.match(r'(\d{1,2})[-/](\d{1,2})', birthday)
        if matches is None:
            raise InputError(birthday, "input has an invalid date format")
        try:
            year = int(2004)  # 2004 is a leap year, so 02/29 will exist
            month = int(matches.group(1))
            day = int(matches.group(2))
            # we don't need to store this result, it is just a check
            datetime.datetime(year=year, month=month, day=day)
        except ValueError:
            raise InputError(birthday, "input is not a valid date")

        return f'{month:>02}/{day:>02}'

    @classmethod
    def age_range(cls, age_range: str) -> str:
        if age_range not in cls.legal_age_ranges:
            raise InputError(age_range, "input not in 'age range' values")
        return age_range

    @staticmethod
    def student(student: str) -> str:
        if student.lower() in ['true', 'yes', 'y'] or student is True:
            return 'TRUE'
        return 'FALSE'

    @classmethod
    def fave_game(cls, game: str) -> str:
        pass

    @staticmethod
    def fave_role(role: str) -> str:
        return role

    @classmethod
    def fave_game_type(cls, game_type: str) -> str:
        pass


class Profiles(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @commands.command()
    async def profile(self, ctx: commands.Context, *, member: discord.Member = None):
        if member is None:
            await ctx.send('back off bitch')
            pass
        else:
            await ctx.send(f"you're not {member}, nice try")
            pass

    @commands.group(invoke_without_command=True)
    async def set(self, ctx: commands.Context):
        """
        Set various profile fields. For examples, check the EiMM Community Profiles spreadsheet.
        """
        await ctx.send(f'Use `{self.bot.default_command_prefix}help set` for more info.')

    @set.group(name='name')
    async def set_name(self, ctx: commands.Context, name: str):
        """
        Sets the "primary name" field. Simple text entry.
        Ex: 'set name Bidoof'
        """
        try:
            checked = ProfileValidation.primary_name(name)
            await ctx.send(checked)
        except InputError as ie:
            await ctx.send(ie)

    @set.group(name='aka')
    async def set_aka(self, ctx: commands.Context, aka: str):
        """
        Sets the "also known as" field. Simple text entry.
        Ex: 'set aka Baby Bibarel'
        """
        try:
            checked = ProfileValidation.primary_name(aka)
            await ctx.send(checked)
        except InputError as ie:
            await ctx.send(ie)

    @set.group(name='pronouns')
    async def set_pronouns(self, ctx: commands.Context):
        """
        Sets the "also known as" field. Opens a selection menu.
        Allowed values:
        - he/him/his
        - she/her/her
        - they/them/theirs
        """
        pronouns = await menu.menu_list(ctx, ProfileValidation.legal_pronouns)
        try:
            checked = ProfileValidation.pronouns(pronouns)
            await ctx.send(f'Checked: `{checked}`.')
        except InputError as ie:
            await ctx.send(f'Error: `{ie}`')

    @set.group(name='communities')
    async def set_communities(self, ctx: commands.Context):
        """
        Sets the "home communities" field. Opens a selection menu.
        If your community isn't listed, feel free to message a staff member.
        """
        communities = await menu.menu_list(ctx, ProfileValidation.legal_communities, select_max=None)
        try:
            checked = ProfileValidation.home_communities(communities)
            await ctx.send(f'Checked: `{checked}`.')
        except InputError as ie:
            await ctx.send(f'Error: `{ie}`')
        pass

    @set.group(name='country')
    async def set_country(self, ctx: commands.Context):
        """
        Sets the "country" field. Opens a selection menu.
        """
        countries = await menu.menu_list(ctx, ProfileValidation.legal_countries)
        try:
            checked = ProfileValidation.country(countries)
            await ctx.send(f'Checked: `{checked}`.')
        except InputError as ie:
            await ctx.send(f'Error: `{ie}`')

    @set.group(name='offset')
    async def set_offset(self, ctx: commands.Context):
        """
        Sets the "timezone" field. Opens an input menu.
        This is a UTC offset, in the format UTC±HH:MM. See https://en.wikipedia.org/wiki/List_of_time_zone_abbreviations for a list.
        """
        # use selection: offset
        await ctx.send('Enter the UTC offset for your timezone (i.e., `UTC±HH:MM`).')
        answer = None
        while answer is None:
            msg = await self.bot.wait_for(event='message', check=lambda m: m.author == ctx.author, timeout=600)
            if msg.content.lower() == 'cancel':
                answer = 'cancel'
                break
            try:
                answer = ProfileValidation.offset(msg.content)
            except InputError as ie:
                await ctx.send(f'Error: `{ie}`. Try again.')
                answer = None
        if answer == 'cancel':
            await ctx.send('Canceled.')
        else:
            await ctx.send(f'Checked: `{answer}`.')

    @set.group(name='birthday')
    async def set_birthday(self, ctx: commands.Context):
        """
        Sets the "birthday" and "age range" fields. Opens an input menu.
        All dates are in MM/DD or YYYY/MM/DD. Sorry Euros.
        """
        options = ['birthday and year', 'birthday only', 'age range only', 'birthday and age range']
        selection = await menu.menu_list(ctx, options)
        birthdate = None
        birthday = None
        age_range = None
        if selection == 'birthday and year':
            def check(m):
                try:
                    ProfileValidation.birthday_year(m.content)
                    return True
                except InputError:
                    return False
            await ctx.send('Enter your birthdate (YYYY/MM/DD):')
            msg = await self.bot.wait_for('message', check=check, timeout=600)
            birthdate = ProfileValidation.birthday_year(msg.content)
            birthdate = birthdate.strftime('%Y/%m/%d')
        if selection == 'birthday only' or selection == 'birthday and age range':
            def check(m):
                try:
                    ProfileValidation.birthday_day(m.content)
                    return True
                except InputError:
                    return False
            await ctx.send('Enter your birthdate (MM/DD):')
            msg = await self.bot.wait_for('message', check=check, timeout=600)
            birthday = ProfileValidation.birthday_day(msg.content)
        if selection == 'age range only' or selection == 'birthday and age range':
            age_range = await menu.menu_list(ctx, ProfileValidation.legal_age_ranges)

        if birthdate is not None:
            await ctx.send(f'Checked birthdate: `{birthdate}`')
            # TODO: clear prev content
        if birthday is not None:
            await ctx.send(f'Checked birthday: `{birthday}`')
            # TODO: clear prev content
        if age_range is not None:
            await ctx.send(f'Checked age range: `{age_range}`')
            # TODO: clear prev content

    @set.group(name='student')
    async def set_student(self, ctx: commands.Context, student: str):
        """
        Sets the "student?" field. Simple text entry.
        Enter either Y/N.
        """
        # lol
        pass

    @set.group(name='game')
    async def set_fave_game(self, ctx: commands.Context):
        """
        Sets the "favorite EiMM game" field. Opens a selection menu.
        If your favorite game isn't listed yet, message a mod to update the list.
        """
        # use menu: fave_game
        pass

    @set.group(name='role')
    async def set_fave_role(self, ctx: commands.Context, role: str):
        """
        Sets the "favorite EiMM role" field. Simple text entry.
        """
        print(role)
        pass

    @set.group(name='game type')
    async def set_fave_game_type(self, ctx: commands.Context):
        """
        Sets the "favorite type of EiMM" field. Opens a selection menu.
        """
        # use menu: fave_game_type
        pass
