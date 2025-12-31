from typing import Any

import gspread
from gspread import Worksheet
from oauth2client.service_account import ServiceAccountCredentials


class SheetConnection:
    def __init__(self, secret: str, scope: list[str]):
        self.creds = ServiceAccountCredentials.from_json_keyfile_name(secret, scope)

    def get_sheet(self, sheet_name: str) -> gspread.Spreadsheet:
        client = gspread.authorize(self.creds)
        return client.open(sheet_name)

    def get_page(self, sheet_name: str, page_name: str | None = None) -> gspread.Worksheet:
        if page_name is None:
            return self.get_sheet(sheet_name).sheet1
        else:
            return self.get_sheet(sheet_name).worksheet(page_name)

    def client(self) -> gspread.Client:
        return gspread.authorize(self.creds)


def get_headings(ws: Worksheet) -> list[str]:
    return ws.row_values(1)


def get_column_values(ws: Worksheet, heading: str) -> list[Any] | None:
    if heading not in get_headings(ws):
        return None
    return [record[heading] for record in ws.get_all_records()]


def get_headings_to_columns(ws: Worksheet) -> dict[str, int]:
    return {k: i + 1 for i, k in enumerate(ws.row_values(1))}


def find_row(records: list[dict[str, Any]], lookup_value: Any, search_heading: str) -> int | None:
    for i, record in enumerate(records):
        if record[search_heading] == lookup_value:
            return i + 2
    return None


def find_record(records: list[dict[str, Any]], lookup_value: Any, search_heading: str) -> dict[str, Any] | None:
    for record in records:
        if record[search_heading] == lookup_value:
            return record
    return None


# def vlookup_column(ws: List[Dict[str, Any]], lookup_value, search_col, return_col):
#     pass


def vlookup_heading(records: list[dict[str, Any]], lookup_value: Any, search_heading: str, return_heading: str) -> Any:
    for record in records:
        if record[search_heading] == lookup_value:
            return record[return_heading]
