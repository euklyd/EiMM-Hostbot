import asyncio
import json
import re
from typing import Optional, List

import discord
import requests
from discord.ext import commands

import utils
from core.bot import Bot

API = 'https://api.scryfall.com/'


# NOTE: You probably don't want to be running this module on your instance. It has a bit of
#  custom code that really doesn't serve any purposes but my own. It won't hurt you if you do
#  run it, though.


class ScryfallResponse:
    def __init__(self, cards, cardnames, card_map):
        self.cards = cards
        self.names = cardnames
        self.map = card_map


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


@commands.command()
async def oracle(ctx: commands.Context, *, expr: str):
    """
    Search Scryfall for Magic: The Gathering cards.

    Full search syntax guide online: https://scryfall.com/docs/syntax
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


async def oracle_inline(message: discord.Message):
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
    card = resp.cards[0]
    if 'image_uris' in card:
        await message.channel.send(card['image_uris']['normal'])
    else:
        await message.channel.send(f"`'image_uris'` not present ( `{card['uri']}` ). Try: {card['scryfall_uri']}")


def setup(bot: Bot):
    bot.add_command(oracle)
    bot.add_listener(oracle_inline, 'on_message')
