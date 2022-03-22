from typing import List, Dict, Any

from game.data_engine.abstract_engine import Engine
from gspread_asyncio import Credentials, AsyncioGspreadClientManager


# TODO: Move to a shared gspread aio utils file
def get_creds():
    # To obtain a service account JSON file, follow these steps:
    # https://gspread.readthedocs.io/en/latest/oauth2.html#for-bots-using-service-account
    creds = Credentials.from_service_account_file(...)
    scoped = creds.with_scopes(
        [
            "https://www.googleapis.com/auth/spreadsheets",
        ]
    )
    return scoped


class SheetEngine(Engine):
    def __init__(self):
        self.agcm = AsyncioGspreadClientManager(get_creds)

    async def get_game_records(self, night: int, game_id: str) -> List[Dict[str, Any]]:
        agc = await self.agcm.authorize()

        # implementation of these two methods is left as an exercise for the reader
        sheet_title = get_title_from_game_id(game_id)
        night_title = night_number_to_title(night)

        sheet = await agc.open(sheet_title)
        worksheet = await sheet.worksheet(night_title)
        return await worksheet.get_all_records()

    async def get_aliases(self, night: int, game_id: str) -> List[str]:
        """
        For this function, instead of game UUIDs, we'd just want spreadsheet links, probably.
        """
        records = await self.get_game_records(night, game_id)
        aliases = {record["alias"] for record in records}
        return sorted(aliases, key=lambda alias: alias.lower())

    async def get_actions(self, night: int, game_id: str, player_id: str) -> ...:

        pass
