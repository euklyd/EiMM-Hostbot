import asyncio
import math
import re
from collections import OrderedDict
from contextlib import ExitStack
from typing import Iterable, MutableMapping, List, Set, Tuple, Union

import discord
from discord.ext import commands

import core

_locks = set()  # type: Set[Tuple[int, int]]  # represents a tuple of user IDs and channel IDs


async def menu_list(ctx: commands.Context, ls: Iterable, timeout: int = 600,
                    select_max: Union[int, None] = 1, repeats: bool = False):
    keys, elems = [], []
    for i, e in enumerate(ls):
        keys.append(str(i))
        elems.append(e)
    return await menu_wrapper(ctx, keys, elems, timeout=timeout, select_max=select_max, repeats=repeats)


async def menu_dict(ctx: commands.Context, d: MutableMapping, timeout: int = 600,
                    select_max: Union[int, None] = 1, repeats: bool = False):
    keys, elems = [], []
    for k, e in d.items():
        keys.append(str(k).replace(',', ''))
        elems.append(e)
    return await menu_wrapper(ctx, keys, elems, timeout=timeout, select_max=select_max, repeats=repeats)


def menu_str(keys: List, elements: List, page, items_per_page=20, select_max: Union[int, None] = 1):
    start, stop = page * items_per_page, (page + 1) * items_per_page

    max_len = 0
    for key in keys:
        max_len = max(len(str(key)), max_len)

    output_str = ''
    for k, e in zip(keys[start:stop], elements[start:stop]):
        output_str += f'{k!s:>{max_len}}- {e}\n'
    output_str = f'```\n{output_str}\n```'
    select_str = 'an item'
    if select_max is None:
        select_str = 'one or more items, separated by commas,'
    elif select_max > 1:
        select_str = f"up to {select_max} items, separated by commas,"
    if len(keys) > items_per_page:
        output_str += f'*(Page {page + 1} of {math.ceil(len(keys) / items_per_page)}. Select {select_str} or `cancel`.)*'
    else:
        output_str += f'*(Select {select_str} or `cancel`.)*'
    return output_str


async def menu_wrapper(ctx: commands.Context, keys: List, elements: List, timeout: int = 600,
                       select_max: Union[int, None] = 1, repeats: bool = False):
    lock = (ctx.author.id, ctx.channel.id)
    if lock in _locks:
        raise RuntimeError("A menu instance in this channel already exists for this user.")
    _locks.add(lock)
    with ExitStack() as stack:
        stack.callback(_locks.remove, lock)
        return await menu_loop(ctx, keys, elements, timeout=timeout, select_max=select_max, repeats=repeats)


async def menu_loop(ctx: commands.Context, keys: List, elements: List, timeout: int = 600,
                    select_max: Union[int, None] = 1, repeats: bool = False):
    NUM_ITEMS = 20
    ARROW_LEFT, ARROW_RIGHT = '\U000025c0', '\U000025b6'

    def single_condition(s: str):
        return s in keys

    def multi_condition(ls: List[str]):
        if ls is None:
            return False
        for elem in ls:
            if elem not in keys:
                return False
        return True

    if select_max is None or select_max > 1:
        multi_select = True
        cond = multi_condition
    else:
        multi_select = False
        cond = single_condition

    page = 0

    initial_menu = menu_str(keys, elements, page, items_per_page=NUM_ITEMS, select_max=select_max)
    selection = None  # type: Union[None, str, List[str]]
    assert None not in keys

    menu_msg = await ctx.send(initial_menu)  # type: discord.Message

    if len(keys) > NUM_ITEMS:
        await menu_msg.add_reaction(ARROW_LEFT)
        await menu_msg.add_reaction(ARROW_RIGHT)

    bot = ctx.bot  # type: core.bot.Bot

    events = ['message', 'reaction_add', 'reaction_remove']
    checks = [
        lambda msg: msg.author == ctx.author and msg.channel == ctx.channel,
        lambda rxn, usr: usr == ctx.author and rxn.message.id == menu_msg.id and rxn.emoji in [ARROW_LEFT, ARROW_RIGHT],
        lambda rxn, usr: usr == ctx.author and rxn.message.id == menu_msg.id and rxn.emoji in [ARROW_LEFT, ARROW_RIGHT],
    ]

    while not cond(selection):
        try:
            result, event_type = await bot.wait_for_first(events=events, checks=checks, timeout=timeout)
        except asyncio.TimeoutError:
            break

        if event_type == 'message':
            # check for selection
            assert type(result) is discord.Message, f'result type was {type(result)}, expected discord.Message'
            if result.content.lower() == 'cancel':
                # exit menu loop
                selection = 'cancel'
                break
            selection = result.content
            if multi_select:
                selection = re.split(r', *', selection)
                if select_max is not None and len(selection) > select_max:
                    await ctx.send(f'ERR: select a maximum of {select_max} options.')
                    selection = None
            # if result.content in keys:
            #     selection = result.content
            #     # await ctx.send(elements[keys.index(selection)])
            #     break
        else:
            # check for arrow direction
            reaction = result[0]
            assert type(reaction) is discord.Reaction, f'result type was {type(reaction)}, expected discord.Reaction'
            if reaction.emoji == ARROW_LEFT:
                page = max(0, page - 1)
            else:
                page = min(int(len(keys) / NUM_ITEMS), page + 1)
            new_menu = menu_str(keys, elements, page, items_per_page=NUM_ITEMS, select_max=select_max)
            await menu_msg.edit(content=new_menu)

    if ctx.me.permissions_in(ctx.channel).manage_messages:
        await menu_msg.clear_reactions()
    else:
        await menu_msg.remove_reaction(ARROW_LEFT, member=ctx.bot.user)
        await menu_msg.remove_reaction(ARROW_RIGHT, member=ctx.bot.user)

    if selection == 'cancel':
        await menu_msg.add_reaction(ctx.bot.redtick)
        return None

    if selection is None:
        await menu_msg.add_reaction(ctx.bot.redtick)
        raise asyncio.TimeoutError

    if multi_select:
        ret = [elements[keys.index(sel)] for sel in selection]
        if not repeats:
            # TODO: Once using python 3.7, use the dict built-in, as it is guaranteed to maintain order in >=3.7
            ret = list(OrderedDict.fromkeys(ret))
    else:
        ret = elements[keys.index(selection)]

    await menu_msg.add_reaction(ctx.bot.greentick)
    return ret

