from abc import ABC, abstractmethod
from typing import List

from game.discord_inputs import Action


class Engine(ABC):
    """Abstract Base Class to allow for smooth support for both relational database queries and Google Sheets."""

    @abstractmethod
    async def get_aliases(self, night: int, game_id: str) -> List[str]:
        """
        Game ID is probably a server ID? We might want to abstract it further, e.g. for each server the bot
        stores a list of UUIDs and the latest one is the "current" ID.
        Regardless a local DB should be queried to get the game_id UUID.

        :param night: ...
        :param game_id: ...
        :return: List of unique players, sorted alphabetically
        """
        pass

    @abstractmethod
    async def get_actions(self, night: int, game_id: str, player_id: ...) -> List[Action]:
        """
        TODO: What type is player_id?
        TODO: Figure out what an action "is". Probably a somewhat complex dataclass but it might just be a
         container to tie strings to Cell IDs.
        :param night:
        :param game_id:
        :param player_id:
        :return:
        """
        pass

    @abstractmethod
    async def submit_actions(self, night: int, game_id: str, player_id: ..., actions: List[Action]):
        pass
