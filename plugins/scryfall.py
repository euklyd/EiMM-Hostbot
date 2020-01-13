import asyncio
import json
from typing import Optional

import requests
from discord.ext import commands

import utils
from core.bot import Bot

API = 'https://api.scryfall.com/'


# class Card:
#     def __init__(self, card):
#         self.name = card['name']
#         self.mana_cost = card['mana_cost']
#         self.cmc = card['cmc']
#         self.type_line = card['type_line']
#         self.oracle_text = card['oracle_text']
#         self.power = card['power']
#         self.toughness = card['toughness']


@commands.command()
async def oracle(ctx: commands.Context, *, expr: str):
    """
    Search Scryfall for Magic: The Gathering cards.

    Full search syntax guide online: https://scryfall.com/docs/syntax
    """
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

    if len(cards) > 1:
        await ctx.send(f"There were {len(cards)} that matched your search parameters. "
                       "Select the one you're looking for:")
        try:
            card = await utils.menu.menu_list(ctx, cardnames)
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
        card = card_map[card]
    else:
        card = cards[0]

    if 'image_uris' in card:
        await ctx.send(card['image_uris']['normal'])
    else:
        await ctx.send(f"`'image_uris'` not present ( `{card['uri']}` ). Try: {card['scryfall_uri']}")


def setup(bot: Bot):
    bot.add_command(oracle)
