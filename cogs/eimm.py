import datetime
import io
import re
from typing import Any, Dict, List

import discord
import yaml
from discord.ext import commands
from fuzzywuzzy import process

from core.bot import Bot
from utils import menu, spreadsheet

SCOPE = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]
SECRET = 'conf/google_creds.json'
SHEET_NAME = 'eimm role templates & keywords'


def default_val(val):
    if val == '':
        return 'None'
    else:
        return str(val)


def ability_embed(row):
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


def keyword_embed(row):
    em = discord.Embed(title=row['Keyword'])
    em.add_field(name='Meaning', value=default_val(row['Meaning']))
    em.add_field(name='Intricacies', value=default_val(row['Intricacies']))

    return em


def passive_embed(row):
    em = discord.Embed(title=row['Ability'])
    em.add_field(name='Effect', value=default_val(row['Effect']))
    em.add_field(name='Notes', value=default_val(row['Notes']))

    return em


def diff_dict(new_dict, old_dict):
    diffs = {'rm': {}, 'add': {}, 'ch': {}}
    for k, e in old_dict.items():
        if k not in new_dict:
            diffs['rm'][k] = e
    for k, e in new_dict.items():
        if k not in old_dict:
            diffs['add'][k] = e
        else:
            diff = {}
            for field in e:
                if field not in old_dict[k]:
                    diff[field] = (e[field], None)
                elif e[field] != old_dict[k][field]:
                    diff[field] = {'new': e[field], 'old': old_dict[k][field]}
                # we're ignoring "what if a field is deleted," we're not doing that
            if len(diff) != 0:
                diffs['ch'][k] = diff
    return diffs


class EiMM(commands.Cog):
    """
    Meta EiMM (the game) things, including ability queries.
    """

    def __init__(self, bot: Bot):
        self.bot = bot
        self.connection = None
        self.abilities = {}  # type: Dict[str, List]
        self.keywords = {}  # type: Dict[str, List]
        self.passives = {}  # type: Dict[str, List]
        self.load()

    def load(self) -> Dict[str, Dict]:
        self.connection = spreadsheet.SheetConnection(SECRET, SCOPE)
        abilities = self.connection.get_page(SHEET_NAME, 'Active Abilities')
        new_abilities = {
            row['Ability Name']: row for row in abilities.get_all_records()
        }
        ability_diffs = diff_dict(new_abilities, self.abilities)
        self.abilities = new_abilities

        keywords = self.connection.get_page(SHEET_NAME, 'Keywords')
        new_keywords = {
            row['Keyword']: row for row in keywords.get_all_records()
        }
        keyword_diffs = diff_dict(new_keywords, self.keywords)
        self.keywords = new_keywords

        passives = self.connection.get_page(SHEET_NAME, "Abilities but they're Passives")
        new_passives = {
            row['Ability']: row for row in passives.get_all_records()
        }
        passive_diffs = diff_dict(new_passives, self.passives)
        self.passives = new_passives

        return {
            'abilities': ability_diffs,
            'keywords': keyword_diffs,
            'passives': passive_diffs,
        }

    @commands.group(invoke_without_command=True)
    async def eimm(self, ctx: commands.Context):
        """
        Query the EiMM ability templates.

        Use "eimm q" to search broadly, or <<rolename>> to view a specific ability.
        """
        await ctx.send(f'Use `{self.bot.default_command_prefix}help eimm` for more info.')

    @eimm.group(name='rebuild')
    async def rebuild(self, ctx: commands.Context):
        """
        Rebuild the sheet cache.
        """
        diffs = self.load()
        yml = yaml.dump(diffs)
        f = io.BytesIO(bytes(yml, 'utf-8'))
        await ctx.send('Rebuilt cache.', file=discord.File(f, f'template diffs {datetime.datetime.utcnow()}'))

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
        match = match.strip()
        for abil, row in self.abilities.items():
            if match.lower() == abil.lower():
                em = ability_embed(row)
                await message.channel.send(embed=em)
                return
        for abil, row in self.keywords.items():
            if match.lower() == abil.lower():
                em = keyword_embed(row)
                await message.channel.send(embed=em)
                return
        for abil, row in self.passives.items():
            if match.lower() == abil.lower():
                em = passive_embed(row)
                await message.channel.send(embed=em)
                return


def setup(bot: commands.Bot):
    bot.add_cog(EiMM(bot))
