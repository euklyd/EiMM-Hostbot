import asyncio
import csv
import io
import json
import re
import urllib
from pprint import pprint
import random
from typing import Optional, List, Dict

import discord
from fuzzywuzzy import process
import requests
import ygoprodeck
from discord.ext import commands

import utils
from core.bot import Bot

API = 'https://api.scryfall.com/'


# NOTE: You probably don't want to be running this module on your instance. It has a bit of
#  custom code that really doesn't serve any purposes but my own. It won't hurt you if you do
#  run it, though.


class ScryfallResponse:
    def __init__(self, cards: dict, cardnames: List[str], card_map: Dict[str, dict]):
        self.cards = cards
        self.names = cardnames
        self.map = card_map

    def closest(self, query: str) -> dict:
        # match = process.extractBests(query, self.names, limit=1)
        match = process.extractOne(query, self.names)
        return self.map[match[0]]


def scryfall_search(expr: str) -> ScryfallResponse:
    ENDPOINT = 'cards/search?'
    query = f'{API}{ENDPOINT}q={expr}'
    with requests.get(query) as response:
        if not response.ok:
            # TODO: handle error
            return
        content = json.loads(response.content)
        cards = content['data']

        while content['has_more']:
            response = requests.get(content['next_page'])
            content = json.loads(response.content)
            cards += content['data']

        cardnames = [card['name'] for card in cards]
        card_map = {card['name']: card for card in cards}
    return ScryfallResponse(cards, cardnames, card_map)


class Cards(commands.Cog):
    """
    Card games, on motorcycles.

    Use [[MtG card name]] or {{Yu-Gi-Oh card name}} to search for cards inline.
    """

    def __init__(self, bot: Bot):
        self.bot = bot

    @commands.command()
    async def oracle(self, ctx: commands.Context, *, expr: str):
        """
        Search Scryfall for Magic: The Gathering cards.

        Full search syntax guide online: https://scryfall.com/docs/syntax
        Also available inline as [[expr]].
        """
        response = scryfall_search(expr)

        if len(response.cards) > 1:
            await ctx.send(f"There were {len(response.cards)} that matched your search parameters. "
                           "Select the one you're looking for:")
            try:
                card = await utils.menu.menu_list(ctx, response.names)
            except asyncio.TimeoutError:
                return
            except RuntimeError:
                await ctx.send('You already have a menu going in this channel.')
                return
            if card is None:
                return
            # card = Card(card)
            # reply = (
            #     f'{card.name} - {card.mana_cost}\n'
            #     f'{card.type_line}\n'
            #     f'{card.oracle_text}\n'
            # )
            card = response.map[card]
        else:
            card = response.cards[0]

        if 'image_uris' in card:
            await ctx.send(card['image_uris']['normal'])
        else:
            await ctx.send(f"`'image_uris'` not present ( `{card['uri']}` ). Try: {card['scryfall_uri']}")

    async def _mtg_inline(self, message: discord.Message) -> bool:
        """
        Returns True if it found cards matching the MtG inline.
        """
        mtg_regex = r'\[\[([^\[\]]*)]]'
        match = re.search(mtg_regex, message.content)
        if type(message.channel) == discord.TextChannel:
            for member in message.channel.members:  # type: discord.Member
                if member.id == 558508371821723670:
                    if member.status == discord.Status.offline:
                        # karn exists and is online
                        pass  # we can just answer queries instead of karn :)
                    else:
                        # karn exists and is online
                        return False
        if match is not None:
            expr = match.group(1)
        else:
            return False
        resp = scryfall_search(expr)
        if len(resp.cards) == 0:
            return False
        card = resp.closest(message.content)
        for c in resp.cards:
            if c['name'].lower() == expr.lower():
                card = c
        if 'image_uris' in card:
            await message.channel.send(card['image_uris']['normal'])
        else:
            await message.channel.send(f"`'image_uris'` not present ( `{card['uri']}` ). Try: {card['scryfall_uri']}")

    async def _ygo_inline(self, message: discord.Message) -> bool:
        """
        Returns True if it found cards matching the Yu-Gi-Oh inline.
        """
        ygo_regex = r'{{([^{}]*)}}'
        match = re.search(ygo_regex, message.content)
        if not match:
            return False
        ctx = await self.bot.get_context(message)
        return await self._ygo(ctx, match.group(1), text_only=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.id == self.bot.user.id:
            return

        if await self._mtg_inline(message):
            return

        if await self._ygo_inline(message):
            return

    async def _ygo(self, ctx: commands.Context, query: str, text_only: bool = False) -> bool:
        """
        Displays Yu-Gi-Oh cards in a scrollable list.

        Returns True if card(s) found, else False.
        """
        ARROW_LEFT, ARROW_RIGHT = '◀', '▶'

        ygo = ygoprodeck.YGOPro()
        result = ygo.get_cards(fname=query)
        # top level: dict key: data
        # second level: list of matches

        intermediate_keys = {card['name']: card for card in result['data']}
        matches = process.extractBests(query, intermediate_keys.keys(), limit=100)

        if text_only:
            cards = [intermediate_keys[match[0]] for match in matches]
            card_embeds = [self._ygo_textembed(card) for card in cards]

        else:
            card_embeds = []

            for match in matches:
                card = intermediate_keys[match[0]]
                card_url = self._ygo_url(card)

                em = discord.Embed()
                em.set_author(name=card['name'], url=card_url)
                em.set_image(url=card['card_images'][0]['image_url'])

                baninfo = self._ygo_baninfo(card)
                if baninfo is not None:
                    em.add_field(name='Banlist', value=baninfo)
                self._ygo_embed_field_sets(em, card, maxlen=4000)

                card_embeds.append(em)

        for i, em in enumerate(card_embeds):
            em.set_footer(text=f'{i + 1} of {len(card_embeds)}')

        msg = await ctx.send(embed=card_embeds[0])

        if len(card_embeds) > 1:
            await msg.add_reaction(ARROW_LEFT)
            await msg.add_reaction(ARROW_RIGHT)

        def check(rxn, user):
            if user != ctx.author:
                return False
            if rxn.message.id != msg.id:
                return False
            if rxn.emoji in [ARROW_RIGHT, ARROW_LEFT]:
                return True
            return False

        events = ['reaction_add', 'reaction_remove']
        checks = [check, check]

        i = 0

        while True:
            try:
                result, event_type = await ctx.bot.wait_for_first(events=events, checks=checks, timeout=60)
            except asyncio.TimeoutError:
                break

            reaction = result[0]
            assert type(
                reaction) is discord.Reaction, f'result type was {type(reaction)}, expected discord.Reaction'
            if reaction.emoji == ARROW_LEFT:
                i = (i - 1) % len(card_embeds)
            else:
                i = (i + 1) % len(card_embeds)

            await msg.edit(embed=card_embeds[i])

        if ctx.me.permissions_in(ctx.channel).manage_messages:
            await msg.clear_reactions()
        else:
            await msg.remove_reaction(ARROW_LEFT, member=ctx.bot.user)
            await msg.remove_reaction(ARROW_RIGHT, member=ctx.bot.user)

        return len(card_embeds) > 0

    @commands.command()
    async def ygo(self, ctx: commands.Context, *, query):
        """
        Search YGOPro for Yu-Gi-Oh cards, as images.

        Also available inline as {{card name}}.
        """
        await self._ygo(ctx, query, text_only=False)

    @commands.command()
    async def ygot(self, ctx: commands.Context, *, query):
        """
        Search YGOPro for Yu-Gi-Oh cards, as text.

        Also available inline as {{card name}}.
        """
        await self._ygo(ctx, query, text_only=True)

    @staticmethod
    def _ygo_textembed(card: dict) -> discord.Embed:
        """
        Returns a text embed for a YGOProDeck card dictionary.
        """
        em = discord.Embed()
        color = Cards._ygocolor(card)
        if color:
            em.colour = color

        em.set_thumbnail(url=card['card_images'][0]['image_url'])

        card_url = Cards._ygo_url(card)
        em.set_author(name=card['name'], url=card_url)
        em.description = card['desc']

        supertype = Cards._ygo_supertype(card)
        if supertype == 'Monster':
            # TODO: Once Discord figures out a way to do embed fields as double columns rather than only options of
            #  single / triple / overflow, update this to be:
            #       level, attribute
            #       type,  atk/def

            if 'level' in card:
                if 'xyz' in card['type'].lower():
                    em.add_field(name='Rank', value=str(card['level']), inline=False)
                else:
                    em.add_field(name='Level', value=str(card['level']), inline=False)

            em.add_field(name='Attribute', value=card['attribute'], inline=False)
            em.add_field(name='Type', value=f'[{card["race"]} / {card["type"]}]', inline=False)

            if 'def' in card:
                em.add_field(name='ATK/DEF', value=f'ATK/{card["atk"]},  DEF/{card["def"]}', inline=False)
            elif 'linkval' in card:
                em.add_field(name='ATK/LINK', value=f'ATK/{card["atk"]},  LINK-{card["linkval"]}', inline=False)

            if 'scale' in card:
                # for pendulum monsters
                em.add_field(name='Pendulum Scale', value=f'{card["scale"]} / {card["scale"]}', inline=False)
            if 'linkmarkers' in card:
                # for link monsters
                em.add_field(name='Link Markers', value=card['linkmarkers'], inline=False)
        elif supertype == 'Spell':
            em.add_field(name='Type', value=card['race'], inline=False)
        elif supertype == 'Trap':
            em.add_field(name='Type', value=card['race'], inline=False)
        else:
            # something went wrong
            em.description = f'Type info could not be found for `{card["name"]}`.'
            return em

        if 'archetype' in card:
            archetype_url = Cards._ygo_archetype_url(card)
            if archetype_url:
                em.add_field(name='Archetype', value=f'[{card["archetype"]}]({archetype_url})')

        baninfo = Cards._ygo_baninfo(card)
        if baninfo is not None:
            em.add_field(name='Banlist', value=baninfo, inline=False)
        if 'card_sets' in card:
            Cards._ygo_embed_field_sets(em, card, maxlen=3000)
        return em

    @staticmethod
    def _ygo_embed_field_sets(em: discord.Embed, card: dict, maxlen: int = 4000):
        if 'card_sets' not in card:
            return

        sets = []
        for set_info in card['card_sets']:
            set_url = Cards._ygo_set_url(set_info)
            text = '[{} {}]({})'.format(set_info['set_name'], set_info['set_rarity_code'], set_url)
            sets.append(text)
        sets_text = ' | '.join(sets)
        if len(sets_text) > maxlen:
            card_url = Cards._ygo_url(card)
            em.add_field(name='Sets',
                         value=f'Listing all the sets this card has appeared in would overflow the embed, check [its ygoprodeck page]({card_url}).')
        else:
            if len(sets_text) <= 1000:
                em.add_field(name='Sets', value=sets_text, inline=False)
            else:
                subsets = []
                length = 0
                n = 1
                for s in sets:
                    if length + len(s) + 3 > 1000:
                        em.add_field(name=f'Sets ({n})', value=' | '.join(subsets), inline=False)
                        n += 1
                        subsets = []
                        length = 0
                    subsets.append(s)
                    length += len(s) + 3  # the separator is 3 chars long
                if len(subsets) > 0:
                    em.add_field(name=f'Sets ({n})', value=' | '.join(subsets), inline=False)

    @staticmethod
    def _ygo_url(card: dict) -> str:
        base_card_url = 'https://db.ygoprodeck.com/card/?search='
        return base_card_url + urllib.parse.quote(card['name'])

    @staticmethod
    def _ygo_set_url(set_info: dict) -> str:
        """
        As a card can have multiple sets, this needs to take a set dict rather than a card dict.
        """
        base_set_url = 'https://db.ygoprodeck.com/set/?search='
        return base_set_url + urllib.parse.quote(set_info['set_name'])

    @staticmethod
    def _ygo_archetype_url(card: dict) -> Optional[str]:
        if 'archetype' not in card:
            return None
        base_archetype_url = 'https://db.ygoprodeck.com/search/?&archetype='
        return base_archetype_url + urllib.parse.quote(card['archetype'])

    @staticmethod
    def _ygo_supertype(card: dict) -> Optional[str]:
        cardtype = card['type']
        if 'monster' in cardtype.lower():
            return 'Monster'
        if 'spell' in cardtype.lower():
            return 'Spell'
        if 'trap' in cardtype.lower():
            return 'Trap'
        return None

    @staticmethod
    def _ygo_baninfo(card: dict) -> Optional[str]:
        if 'banlist_info' in card:
            if 'ban_tcg' in card['banlist_info']:
                tcg = card['banlist_info']['ban_tcg']
            else:
                tcg = 'Unlimited'
            if 'ban_ocg' in card['banlist_info']:
                ocg = card['banlist_info']['ban_ocg']
            else:
                ocg = 'Unlimited'
            if 'ban_goat' in card['banlist_info']:
                goat = card['banlist_info']['ban_goat']
            else:
                goat = 'Unlimited'

            return f'TCG: {tcg} | OCG: {ocg} | Goat: {goat}'
        return None

    @staticmethod
    def _ygocolor(card: dict) -> Optional[discord.Colour]:
        """
        Unfortunately will never support Pendulums, as gradients are not a thing on Discord.

        May support Egyptian Gods at some point.
        """
        color_dict = {
            'normal monster': 0xc9b175,
            'normal tuner monster': 0xc9b175,

            'effect monster': 0xc26727,
            'flip effect monster': 0xc26727,
            'tuner monster': 0xc26727,
            'union effect monster': 0xc26727,
            'gemini monster': 0xc26727,

            'synchro monster': 0xfefefe,
            'synchro tuner monster': 0xfefefe,

            'ritual monster': 0x446ec7,
            'ritual effect monster': 0x446ec7,  # yu-gi-oh drives me nuts with how it codifies typelines
            'fusion monster': 0x9051a6,
            'xyz monster': 0x000000,
            'link monster': 0x2652ab,

            'spell card': 0x30ab83,
            'trap card': 0xb135b5,
        }
        if card['type'].lower() in color_dict:
            return discord.Colour(color_dict[card['type'].lower()])
        return None

    @commands.command(name='dt')
    async def duel_terminal(self, ctx: commands.Context, dt_num: str, num_cards: int = 1):
        """
        Pull Duel Terminal cards.

        Pull ratios are assumed to be identical to those in Dark Legends, etc (11:1, 1:1, 1:5, 1:12).
        """
        if num_cards > 100:
            await ctx.send('Pick a lower number of cards.')
            return
        elif num_cards < 1:
            num_cards = 1

        COMMONS_PER_PACK = 6  # we're deciding there's 10 cards per pack so that's 9 common slots

        dt_nums = ['1', '2', '3', '4', '5a', '5b', '6a', '6b', '7a', '7b']
        if dt_num.lower() not in dt_nums:
            await ctx.send(f'{dt_num} not a valid Duel Terminal (1-7).')
            return

        dt_name = f'Duel Terminal {dt_num}'

        ygo = ygoprodeck.YGOPro()
        cards = ygo.get_cards(cardset=dt_name)['data']

        # This isn't actually used, but it's useful to keep track of how I arrived at these numbers
        # pull_ratios = {
        #     '(DNPR)': 660,  # 11:1
        #     '(DRPR)': 60,   # 1:1
        #     '(DSPR)': 12,   # 1:5
        #     '(DUPR)': 5,    # 1:12
        # }

        rarity_dict = {
            '(DNPR)': [],  # C
            '(DRPR)': [],  # R
            '(DSPR)': [],  # SR
            '(DUPR)': [],  # UR
            # '': []  # duel terminal secret rare doesn't exist in the TCG (yet?)
        }

        for card in cards:
            for card_set in card['card_sets']:
                if card_set['set_name'].lower() == dt_name.lower():
                    if card_set['set_rarity_code'] not in rarity_dict:
                        # When rarities are missing, treat them as commons:
                        card_set['set_rarity_code'] = '(DNPR)'
                    rarity_dict[card_set['set_rarity_code']].append(card)

        pulls = {}
        c_odds = COMMONS_PER_PACK * 1 * 5 * 12
        r_odds = 5 * 12
        sr_odds = 12
        ur_odds = 5
        for i in range(num_cards):
            rand = random.randint(0, c_odds + r_odds + sr_odds + ur_odds)

            if rand < c_odds:
                # common
                rarity = '(DNPR)'
            elif rand < c_odds + r_odds:
                # rare
                rarity = '(DRPR)'
            elif rand < c_odds + r_odds + sr_odds:
                # super rare
                rarity = '(DSPR)'
            else:
                # ultra rare
                rarity = '(DUPR)'

            pull = random.choice(rarity_dict[rarity])
            pull['num'] = 1
            pull['rarity'] = rarity

            if pull['name'] in pulls:
                pulls[pull['name']]['num'] += 1
            else:
                pulls[pull['name']] = pull

        pulls = [card for card in pulls.values()]
        pulls = sorted(pulls, key=lambda x: x['name'].lower())
        result = ''
        for card in pulls:
            # I don't want to use the awful rarity symbols
            rarity = {
                '(DNPR)': 'C',
                '(DRPR)': 'R',
                '(DSPR)': 'SR',
                '(DUPR)': 'UR',
            }[card['rarity']]
            result += f'{card["num"]}x {card["name"]} ({rarity})\n'

        await ctx.send(result)

    @commands.command(name='ygocsv')
    async def collection_to_csv(self, ctx: commands.Context):
        """
        Exports a YGOProDeck collection CSV to something more detailed.

        I suggest importing the output CSV to Google sheets / MS Excel so you can easily filter it.
        """
        ENDPOINT = 'https://db.ygoprodeck.com/api/v7/cardinfo.php'

        if len(ctx.message.attachments) != 1:
            await ctx.send(f'Attach exactly one (1) item! ({len(ctx.message.attachments)} found.)')
            return

        ls_cards = requests.get(ENDPOINT).json()['data']
        cards = {}

        for card in ls_cards:
            cards[card['id']] = card

        attachment = ctx.message.attachments[0]
        with io.BytesIO() as buffer:
            await attachment.save(buffer)
            csv_contents = [line.decode('utf-8') for line in buffer.readlines()]

        collection = {}
        reader = csv.DictReader(csv_contents)
        for card_row in reader:
            card = cards[int(card_row['cardid'])]

            key = f"{card['id']}-{card_row['cardcode']}"
            if card_row['card_edition'] == '1st Edition':
                key += '-1st'

            collection[key] = {
                'quantity': int(card_row['cardq']),
                'id': card['id'],
                'name': card['name'],
                'type': self._ygo_supertype(card),
                'subtype': card['type'],
                'atk': card['atk'] if 'atk' in card else None,
                'def': card['def'] if 'def' in card else None,
                'level': card['level'] if 'level' in card else None,
                'race': card['race'],
                'attribute': card['attribute'] if 'attribute' in card else None,
                'desc': card['desc'],
                'archetype': card['archetype'] if 'archetype' in card else '',
                'set': card_row['cardset'],
                'rarity': card_row['cardrarity'],
                'set code': card_row['cardcode'],
            }

        ls_collection = list(collection.values())
        ls_collection = sorted(ls_collection, key=lambda x: x['name'])
        keys = ls_collection[0].keys()

        with io.StringIO() as csv_out:
            writer = csv.DictWriter(csv_out, keys)
            writer.writeheader()
            writer.writerows(ls_collection)
            csv_out.seek(0)
            await ctx.send(f'Processed your collection.',
                           file=discord.File(csv_out, filename=f'{ctx.author} collection.csv'))


def setup(bot: Bot):
    bot.add_cog(Cards(bot))
