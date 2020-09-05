import datetime
import re
from typing import List, Any

import discord
import gspread
import pycountry
from discord.ext import commands
from fuzzywuzzy import process

from oauth2client.service_account import ServiceAccountCredentials

from core.bot import Bot
from utils import menu, spreadsheet

SCOPE = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]
SECRET = 'conf/google_creds.json'
SHEET_NAME = 'eimm role templates & keywords'


def ability_embed(row):
    def default_val(val):
        if val == '':
            return 'None'
        else:
            return str(val)
    em = discord.Embed(title=row['Ability Name'])
    em.add_field(name='Priority', value=default_val(row['Priority(s)']))
    em.add_field(name='Targets', value=default_val(row['Targets']))
    em.add_field(name='Supertype', value=default_val(row['Supertype']))
    bh_val = ''
    if row['B'] == 'TRUE':
        bh_val += '❤️'
    if row['H'] == 'TRUE':
        bh_val += '💀'
    if bh_val == '':
        bh_val = 'N/A'
    em.add_field(name='B/H', value=bh_val)
    em.add_field(name='Categories', value=default_val(row['Categories']))
    em.add_field(name='Rules Text', value=default_val(row['Rules Text']), inline=False)
    em.add_field(name='Details & Design Notes', value=default_val(row['Details & Design Notes']), inline=False)

    return em



class EiMM(commands.Cog):
    """
    Meta EiMM (the game) things, including ability queries.
    """
    def __init__(self, bot: Bot):
        self.load()
        self.bot = bot

    def load(self):
        self.connection = spreadsheet.SheetConnection(SECRET, SCOPE)
        abilities = self.connection.get_page(SHEET_NAME, 'Active Abilities')
        self.abilities = {
            row['Ability Name']: row for row in abilities.get_all_records()
        }

    @commands.group(invoke_without_command=True)
    async def eimm(self, ctx: commands.Context):
        # TODO: docstr
        await ctx.send(f'Use `{self.bot.default_command_prefix}help eimm` for more info.')

    @eimm.group(name='rebuild')
    async def rebuild(self, ctx: commands.Context):
        """
        Rebuild the sheet cache.
        """
        self.load()
        await ctx.send('Rebuilt cache.')

    @eimm.group(name='q')
    async def q(self, ctx: commands.Context, *, term: str):
        """
        Search the template sheet for an ability.

        You can also use <<fullblock>> to search for abilities inline.
        """
        choices = self.abilities.keys()
        matches = process.extractBests(term, choices, limit=10)
        if matches[0][1] == 100:
            match = matches[0][0]
        else:
            matches = [match[0] for match in matches]  # type: List[str]
            await ctx.send('Which ability did you mean?')
            match = await menu.menu_list(ctx, matches)
        em = ability_embed(self.abilities[match])
        await ctx.send(embed=em)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        ability_regex = r'<<([^<>]*)>>'
        match = re.search(ability_regex, message.content)
        if match is not None:
            match = match.group(1)
        else:
            return
        for abil, row in self.abilities.items():
            if match.lower() == abil.lower():
                em = ability_embed(row)
                await message.channel.send(embed=em)
                return
