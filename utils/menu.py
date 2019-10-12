import asyncio
from contextlib import ExitStack
from typing import Iterable, MutableMapping, List, Set, Tuple

import discord
from discord.ext import commands

import core


_locks = set()  # type: Set[Tuple[int, int]]  # represents a tuple of user IDs and channel IDs


async def menu_list(ctx: commands.context.Context, ls: Iterable, timeout: int = 600):
    keys, elems = [], []
    for i, e in enumerate(ls):
        keys.append(str(i))
        elems.append(e)
    await menu_wrapper(ctx, keys, elems, timeout)


async def menu_dict(ctx: commands.context.Context, d: MutableMapping, timeout: int = 600):
    keys, elems = [], []
    for k, e in d.items():
        keys.append(str(k))
        elems.append(e)
    await menu_wrapper(ctx, keys, elems, timeout)


def menu_str(keys: List, elements: List, page, items_per_page=20):
    start, stop = page * items_per_page, (page + 1) * items_per_page

    max_len = 0
    for key in keys:
        max_len = max(len(str(key)), max_len)

    output_str = ''
    for k, e in zip(keys[start:stop], elements[start:stop]):
        output_str += f'{k!s:>{max_len}}- {e}\n'
    return f'```{output_str}```'


async def menu_wrapper(ctx: commands.context.Context, keys: List, elements: List, timeout: int = 600):
    lock = (ctx.author.id, ctx.channel.id)
    if lock in _locks:
        raise RuntimeError("you already have a menu instance in this channel")
    _locks.add(lock)
    with ExitStack() as stack:
        stack.callback(_locks.remove, lock)
        await menu_loop(ctx, keys, elements, timeout)


async def menu_loop(ctx: commands.context.Context, keys: List, elements: List, timeout: int = 600):
    NUM_ITEMS = 20
    ARROW_LEFT, ARROW_RIGHT = '◀', '▶'

    page = 0

    initial_menu = menu_str(keys, elements, page, items_per_page=NUM_ITEMS)
    selection = None
    assert None not in keys

    menu_msg = await ctx.send(initial_menu)  # type: discord.Message
    await menu_msg.add_reaction(ARROW_LEFT)
    await menu_msg.add_reaction(ARROW_RIGHT)

    bot = ctx.bot  # type: core.bot.Bot

    events = ['message', 'reaction_add', 'reaction_remove']
    checks = [
        lambda msg: msg.author == ctx.author and msg.channel == ctx.channel,
        lambda rxn, usr: usr == ctx.author and rxn.message.id == menu_msg.id and rxn.emoji in [ARROW_LEFT, ARROW_RIGHT],
        lambda rxn, usr: usr == ctx.author and rxn.message.id == menu_msg.id and rxn.emoji in [ARROW_LEFT, ARROW_RIGHT],
    ]

    while selection not in keys:
        try:
            result, event_type = await bot.wait_for_first(events=events, checks=checks, timeout=timeout)
        except asyncio.TimeoutError:
            break

        if event_type == 'message':
            # check for selection
            assert type(result) is discord.Message, f'result type was {type(result)}, expected discord.Message'
            if result.content in keys:
                selection = result.content
                await ctx.send(elements[keys.index(selection)])
                break
        else:
            # check for arrow direction
            reaction = result[0]
            assert type(reaction) is discord.Reaction, f'result type was {type(reaction)}, expected discord.Reaction'
            if reaction.emoji == ARROW_LEFT:
                page = max(0, page - 1)
            else:
                page = min(int(len(keys)/NUM_ITEMS), page + 1)
            new_menu = menu_str(keys, elements, page)
            await menu_msg.edit(content=new_menu)

    if ctx.me.permissions_in(ctx.channel).manage_messages:
        await menu_msg.clear_reactions()
    else:
        await menu_msg.remove_reaction(ARROW_LEFT, member=ctx.bot.user)
        await menu_msg.remove_reaction(ARROW_RIGHT, member=ctx.bot.user)

    if selection is None:
        await menu_msg.add_reaction(ctx.bot.redtick)
        raise asyncio.TimeoutError

    await menu_msg.add_reaction(ctx.bot.greentick)
    return selection
