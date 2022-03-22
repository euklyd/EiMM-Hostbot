from discord import Interaction, SelectOption, ui
from typing import Any, List, Dict, Callable, Awaitable

from game.data_engine.abstract_engine import Engine

Action = ...  # TODO


class ActionDropdown(ui.Select):
    def __init__(self, players: List[str], action: Action, actions_map: Dict[..., ...]):
        players = sorted(set(players), key=lambda x: x.lower())
        super().__init__(
            placeholder=Action.prompt,
            options=[SelectOption(label=player) for player in players],
        )
        self.action = action
        self.actions_map = actions_map

    async def callback(self, interaction: Interaction) -> Any:
        self.action.target = self.values[0]
        self.actions_map[self.action.key] = self.action
        # await interaction.response.send_message(f"**{self.values[0]}**, you're dead.")


class ActionConfirmation(ui.Button):
    def __init__(self, view_callback: Callable[[Interaction], Awaitable[None]]):
        super(ActionConfirmation, self).__init__()
        self.view_callback = view_callback

    def callback(self, interaction: Interaction):
        self.view_callback(interaction)


class ActionView(ui.View):
    def __init__(self, players: List[str], actions: List[Action], data_engine: Engine):
        """

        :param players:
        :param actions: This should actually be ordered, probably.
        """
        super(ActionView, self).__init__()
        self.actions = actions
        self.actions_map = {}
        self.data_engine = data_engine
        for action in actions:
            self.add_item(ActionDropdown(players, action, self.actions_map))
        self.add_item(ActionConfirmation(self.button_callback))  # for confirmation

    async def button_callback(self, interaction: Interaction):
        if len(self.actions_map) < len(self.actions):
            # not a complete submission
            return ...
        await self.data_engine.submit_actions(..., ..., ..., list(self.actions_map.values()))
