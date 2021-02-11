import asyncio
import json
import re
import urllib
from pprint import pprint
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

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.id == self.bot.user.id:
            return
        img_regex = r'\[\[([^\[\]]*)]]'
        match = re.search(img_regex, message.content)
        if type(message.channel) == discord.TextChannel:
            for member in message.channel.members:  # type: discord.Member
                if member.id == 558508371821723670:
                    if member.status == discord.Status.offline:
                        # karn exists and is online
                        pass  # we can just answer queries instead of karn :)
                    else:
                        # karn exists and is online
                        return
        if match is not None:
            expr = match.group(1)
        else:
            return
        resp = scryfall_search(expr)
        if len(resp.cards) == 0:
            return
        card = resp.closest(message.content)
        for c in resp.cards:
            if c['name'].lower() == expr.lower():
                card = c
        if 'image_uris' in card:
            await message.channel.send(card['image_uris']['normal'])
        else:
            await message.channel.send(f"`'image_uris'` not present ( `{card['uri']}` ). Try: {card['scryfall_uri']}")

    @commands.command()
    async def ygo(self, ctx: commands.Context, *, query):
        """
        Search YGOPro for Yu-Gi-Oh cards.
        """
        base_card_url = 'https://db.ygoprodeck.com/card/?search='
        base_set_url = 'https://db.ygoprodeck.com/set/?search='

        ygo = ygoprodeck.YGOPro()
        result = ygo.get_cards(fname=query)
        # top level: dict key: data
        # second level: list of matches

        intermediate_keys = {card['name']: card for card in result['data']}
        matches = process.extractBests(query, intermediate_keys.keys(), limit=10)
        card = intermediate_keys[matches[0][0]]

        card_url = base_card_url + urllib.parse.quote(card['name'])
        description = f'_Other possible matches: {", ".join([match[0] for match in matches[1:]])}_'
        if len(matches) == 10:
            description += ' ...'
        elif len(matches) <= 1:
            description += ' _None_'

        em = discord.Embed(description=description)
        em.set_author(name=card['name'], url=card_url)
        em.set_image(url=card['card_images'][0]['image_url'])

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

            baninfo = f'TCG: {tcg} | OCG: {ocg} | Goat: {goat}'

            em.add_field(name='Banlist', value=baninfo)

        sets = []
        for s in card['card_sets']:
            set_url = base_set_url + urllib.parse.quote(s['set_name'])
            text = '[{} {}]({})'.format(s['set_name'], s['set_rarity_code'], set_url)
            sets.append(text)
        # sets_text = '\n'.join(sets)
        sets_text = ' | '.join(sets)
        if len(sets_text) > 4000:
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

        await ctx.send(embed=em)


def setup(bot: Bot):
    bot.add_cog(Cards(bot))
