import asyncio
import time
from typing import List, Optional, Callable, Union, Any, Tuple, Iterable

import discord
from discord.ext import commands

from conf.conf import Conf


class Bot(commands.Bot):
    def __init__(self, command_prefix: Union[str, Iterable[str], Callable[['Bot', discord.Message], str]], conf: Conf,
                 help_command=None, description: str = None, **options):
        if help_command is None:
            super().__init__(command_prefix, description=description, **options)
        else:
            super().__init__(command_prefix, help_command=help_command, description=description, **options)
        self.conf = conf  # type: Conf
        self._greentick = self.get_emoji(conf.greentick_id)  # type: discord.Emoji
        self._redtick = self.get_emoji(conf.redtick_id)  # type: discord.Emoji

    @property
    def greentick(self) -> discord.Emoji:
        if self._greentick is None:
            self._greentick = self.get_emoji(self.conf.greentick_id)  # type: discord.Emoji
        return self._greentick

    @property
    def redtick(self) -> discord.Emoji:
        if self._redtick is None:
            self._redtick = self.get_emoji(self.conf.redtick_id)  # type: discord.Emoji
        return self._redtick

    async def wait_for_first(self, events: List[str], *, checks: Optional[List[Callable[..., bool]]] = None,
                             timeout=None) -> Tuple[Any, str]:
        """|coro|

        Waits for the first of multiple WebSocket events to be dispatched.

        This could be used to wait for a user to reply to a message,
        or to react to a message, or to edit a message in a self-contained
        way.

        The ``timeout`` parameter is passed onto :func:`asyncio.wait_for`. By default,
        it does not timeout. Note that this does propagate the
        :exc:`asyncio.TimeoutError` for you in case of timeout and is provided for
        ease of use.

        In case the event returns multiple arguments, a :class:`tuple` containing those
        arguments is returned instead. Please check the
        :ref:`documentation <discord-api-events>` for a list of events and their
        parameters.

        This function returns the **first event that meets the requirements**.

        Parameters
        ------------
        events: List[:class:`str`]
            The event names, similar to the :ref:`event reference <discord-api-events>`,
            but without the ``on_`` prefix, to wait for.
        checks: Optional[List[Callable[..., :class:`bool`]]]
            A list of predicates corresponding to each event name, to check what to wait for.
            The arguments must meet the parameters of the event being waited for.
        timeout: Optional[:class:`float`]
            The number of seconds to wait before timing out and raising
            :exc:`asyncio.TimeoutError`.

        Raises
        -------
        asyncio.TimeoutError
            If a timeout is provided and it was reached.

        Returns
        --------
        Any
            Returns no arguments, a single argument, or a :class:`tuple` of multiple
            arguments that mirrors the parameters passed in the
            :ref:`event reference <discord-api-events>`.
        """

        if checks is None:
            checks = [None] * len(events)

        assert len(events) == len(checks), "number of events and checks must be equal"

        futures = []  # type: List[asyncio.Future]

        for event, check in zip(events, checks):
            future = self.loop.create_future()
            if check is None:
                def _check(*args):
                    return True

                check = _check

            ev = event.lower()
            try:
                listeners = self._listeners[ev]
            except KeyError:
                listeners = []
                self._listeners[ev] = listeners

            listeners.append((future, check))
            futures.append(future)

        complete, pending = await asyncio.wait(futures, timeout=timeout, loop=self.loop, return_when=asyncio.FIRST_COMPLETED)
        for future in pending:  # type: asyncio.Future
            future.cancel()
        if len(complete) == 0:
            raise asyncio.TimeoutError
        completed_future = complete.pop()  # type: asyncio.Future
        index = futures.index(completed_future)
        event_type = events[index]
        return completed_future.result(), event_type
