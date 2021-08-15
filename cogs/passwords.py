import logging

import discord
from discord import abc
from discord.ext import commands
from datetime import datetime
from core.bot import Bot
from utils import spreadsheet

SCOPE = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]
SECRET = 'conf/google_creds.json'
SHEET_NAME = 'EiMM Passwords'

USER_ID = 'Discord Snowflake'
NAME = 'Name'
PASSWORD = 'Password'
TIMESTAMP = 'Timestamp'

COLS = {
    USER_ID: 'A',
    NAME: 'B',
    PASSWORD: 'C',
    TIMESTAMP: 'D'
}


class Passwords(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.connection = spreadsheet.SheetConnection(SECRET, SCOPE)
        sheet = self.connection.get_page(SHEET_NAME)
        self.users = {}
        for i, record in enumerate(sheet.get_all_records()):
            row = i + 2
            self.users[int(record[USER_ID])] = row

    @staticmethod
    async def check_priv(ctx: commands.Context):
        if not isinstance(ctx.channel, abc.PrivateChannel):
            await ctx.send(
                'This channel is not private! This command can only be used in DMs.'
            )
            await ctx.message.add_reaction(ctx.bot.redtick)
            return False
        return True

    def update_sheet(self, user: discord.User, password: str):
        sheet = self.connection.get_page(SHEET_NAME)
        if user.id in self.users:
            cell_list = sheet.range(
                f'{COLS[NAME]}{self.users[user.id]}:{COLS[TIMESTAMP]}{self.users[user.id]}'
            )
            cell_list[0].value = str(user)
            cell_list[1].value = password
            cell_list[2].value = datetime.utcnow().strftime('%m/%d/%Y %H:%M:%S')
            sheet.update_cells(cell_list)
        else:
            sheet.append_row([
                # i hate google sheets so much how DARE you convert to scientific notation
                # and lose about 20 digits of precision
                str(user.id),
                str(user),
                password,
                datetime.utcnow().strftime('%m/%d/%Y %H:%M:%S')
            ])
            sheet = self.connection.get_page(SHEET_NAME)
            self.users[user.id] = sheet.row_count
        return None

    @commands.group(invoke_without_command=True)
    async def password(self, ctx: commands.Context):
        """
        Show your current password. Use only in DMs.
        """
        if not await self.check_priv(ctx):
            return
        if ctx.author.id not in self.users:
            await ctx.send(f'You have no password set yet.')
        sheet = self.connection.get_page(SHEET_NAME)
        records = sheet.get_all_records()
        logging.info(f'records: {records}')
        idx = self.users[ctx.author.id] - 2
        logging.info(f'idx: {idx}')
        record = records[idx]
        await ctx.send(f'Your current password is `{record[PASSWORD]}`, and your user ID is `{ctx.author.id}`.')

    @password.group(name='set')
    async def password_set(self, ctx: commands.Context, *, password: str):
        """
        Set a new password. Use only in DMs.
        """
        if not await self.check_priv(ctx):
            return

        if ctx.author.id not in self.users:
            new = True
        else:
            new = False

        self.update_sheet(ctx.author, password)

        if new:
            await ctx.send(f'Congrats, your password has now been set! Your user ID is `{ctx.author.id}`.')
        else:
            await ctx.send(f'Password changed. Your user ID is `{ctx.author.id}`.')


def setup(bot: commands.Bot):
    bot.add_cog(Passwords(bot))
