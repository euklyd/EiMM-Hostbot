import asyncio
import datetime
import io
import json
import pprint
import random
import re
from typing import Any, Dict, List, Optional, Tuple

import discord
import yaml
from discord.ext import commands
from fuzzywuzzy import process
from munkres import Munkres, DISALLOWED

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


def ability_text(row):
    limitations = 'Unlimited'
    if 'cycling' in row['Categories'].lower():
        limitations += ' - Cycling'
    targets = row['Targets']
    priority = row['Priority(s)']
    if row['B'] and row['H']:
        hb = 'B/H'
    elif row['B']:
        hb = 'B'
    elif row['H']:
        hb = 'H'
    else:
        hb = 'N'
    text = row['Rules Text']
    template = (
        f'**Ability Name (Active, {limitations}, {targets}, {priority}, {hb}):**\n'
        '_Flavor_\n'
        f'{text}'
    )
    return template


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

    # If I ever want to trim this down in the future, will just strip these out to be optional.
    em.add_field(name='Resolution Details', value=default_val(row['Resolution Details']), inline=False)
    em.add_field(name='Design Notes', value=default_val(row['Design Notes']), inline=False)
    em.add_field(name='Template', value=f'```md\n{ability_text(row)}```', inline=False)

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


# used for queue selection algorithm
class Host:
    def __init__(self, name, prefs, prio):
        self.prefs = []
        for pref in prefs:
            if type(pref) is int:
                self.prefs.append(pref)
            elif pref == '' or pref is None:
                self.prefs.append(DISALLOWED)
            else:
                self.prefs.append(int(pref))

        self.name = name
        self.prio = prio

    def __repr__(self):
        prefs = [None if pref == DISALLOWED else pref for pref in self.prefs]
        return f'<name={self.name}, prefs={prefs}, prio={self.prio}>'

    def __str__(self):
        return f'{self.name} [{self.prio}]: {self.prefs}'


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
    async def eimm_rebuild(self, ctx: commands.Context):
        """
        Rebuild the sheet cache.
        """
        diffs = self.load()
        yml = yaml.dump(diffs)
        f = io.BytesIO(bytes(yml, 'utf-8'))
        await ctx.send('Rebuilt cache.', file=discord.File(f, f'template diffs {datetime.datetime.utcnow()}'))

    @eimm.group(name='q')
    async def eimm_q(self, ctx: commands.Context, *, term: str):
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
        if message.author.id == self.bot.user.id:
            return
        ability_regex = r'<<([^<>]*)>>'
        match = re.search(ability_regex, message.content)
        if match is not None:
            match = match.group(1)
        else:
            return
        match = match.strip()
        if match == '':
            return
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

    @staticmethod
    def _mod_bias_queue_algorithm(hosts: Dict[str, dict], priority: int = 2, total: int = 6) \
            -> Tuple[List[Host], List[Host]]:
        """
        Inputs:
        - dict of hosts, in the format specified at the top of this file.
        - (optional) number of hosts selected at a higher priority (default 2)
        - (optional) total number of hosts to select (default 6)

        Returns:
        - Ordered list of assigned hosts (first in the list gets slot 1, etc.)
        - Ordered list of selected hosts, in case manual assignment is needed

        NOTE: This and following methods were lifted straight from the original PenguinBot.
        """
        picks = EiMM._mod_bias_host_selection(hosts, priority=priority)
        assignments = EiMM._mod_bias_hungarian_algorithm(picks[:total])
        return assignments, picks

    @staticmethod
    def _mod_bias_host_selection(hosts: Dict[str, dict], priority: int = 2) -> List[Host]:
        hosts = [
            Host(
                name, prefs['prefs'], prefs['priority']
            ) for name, prefs in hosts.items()
        ]

        # Select n=2 hosts from the hosts with priority
        prio_hosts = [
            host for host in hosts if host.prio > 0
        ]
        if len(prio_hosts) > priority:
            picks = random.sample(prio_hosts, priority)
        else:
            # If there are fewer than 2 prio hosts, use as many as possible
            picks = prio_hosts

        # Don't modify the original list
        hosts_copy = list(hosts)
        for host in picks:
            hosts_copy.remove(host)

        # Separate out the rest of the hosts into normal and low priorities
        normal_hosts = [
            host for host in hosts_copy if host.prio >= 0
        ]
        low_hosts = [
            host for host in hosts_copy if host.prio < 0
        ]
        random.shuffle(normal_hosts)
        random.shuffle(low_hosts)

        # The selected hosts for the six queue slots per season are:
        # n=2 priority hosts +
        # m=4 other hosts (may or may not have prio)
        # If n<2, m increases to compensate.
        picks = picks + normal_hosts + low_hosts

        return picks

    @staticmethod
    def _mod_bias_hungarian_algorithm(picks: List[Host], total: int = 6) -> List[Host]:
        """
        tl;dr Numbers go in, numbers come out.

        Uses the Hungarian Algorithm, aka Munkres Assignment Algorithm,
        to assign hosts to slots with maximum respect for preferences:
        https://en.wikipedia.org/wiki/Hungarian_algorithm
        """
        random.shuffle(picks)

        matrix = []  # type: List[List[int]]
        for pick in picks:
            matrix.append(pick.prefs)
        m = Munkres()
        indices = m.compute(matrix)

        assignments = [None] * total  # type: List[Optional[Host]]
        for row, col in indices:
            assignments[col] = picks[row]

        return assignments

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def qselect(self, ctx: commands.Context, *, jsonstr: str):
        """
        Selects hosts to fill the next EiMM season.

        Takes a JSON argument, of the format:
        {
            "host1#1234": {
                # array of preference weights, 1 (highest) to 6 (lowest); "" for N/A.
                "prefs": [1, 1, "", 1, 1, 1],
                # queue priority, -1 for low, 0 for normal, 1 for high
                "priority": -1
            },
            "host2#1234": ...,
            ...,
            "host6#1234": ...
        }
        """
        try:
            hosts = json.loads(jsonstr)
        except json.JSONDecodeError as e:
            await ctx.send(str(e))
            return
        assignments, picks = EiMM._mod_bias_queue_algorithm(hosts)
        for host in picks:
            for i in range(0, len(host.prefs)):
                if host.prefs[i] == DISALLOWED:
                    host.prefs[i] = 'N/A'
        reply = "**The next season's host slots, in order, are...** 🥁 🥁 🥁"
        await ctx.send(reply)
        nums = ['First', 'Second', 'Third', 'Fourth', 'Fifth', 'Finally']
        for num, host in zip(nums, assignments):
            await asyncio.sleep(5.0)
            reply = f'**{num},** `{host.name}`, with preferences `{host.prefs}`!'
            await ctx.send(reply)
        reply = (
            '*The full list of selected hosts, in priority order, is:*\n'
            f'```{pprint.pformat(picks)}```'
            '*("but euklyd, that\'s ugly code formatting", you may say: '
            'i\'ll fix it later u nerd - update one whole bot later: this isn\'t getting fixed)*'
            # f"```{[str(pick) + '\n' for pick in picks]}```"
        )
        await ctx.send(reply)


def setup(bot: commands.Bot):
    bot.add_cog(EiMM(bot))
