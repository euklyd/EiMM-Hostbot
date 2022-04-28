from pathlib import Path
from typing import Dict, List, Iterable

import discord
import sqlalchemy
from discord.ext import commands
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.bot import Bot
from cogs import walrus_schema as walr


def menu_opener_button(label: str, menu: discord.ui.Modal) -> discord.ui.View:
    async def menu_cb(interaction: discord.Interaction):
        await interaction.response.send_modal(menu)

    view = discord.ui.View()
    button = discord.ui.Button(label=label, style=discord.ButtonStyle.blurple)
    button.callback = menu_cb
    view.add_item(button)

    return view


class SubmitMenu(discord.ui.Modal, title="Walrus Submission"):
    def __init__(self, categories: Iterable[walr.Category]):
        super().__init__()
        self.values = {}

        for cat in categories:
            field = discord.ui.TextInput(
                label=cat.name[:40],
                custom_id=cat.id,
                style=discord.TextStyle.short,
                required=True,
                placeholder="http://www.youtube.com/watch?v=oHg5SJYRHA0",
            )
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message("Your submissions have been recorded.")
        for datum in interaction.data.get("components"):
            field = datum.get("components")[0]
            self.values[field.get("custom_id")] = field.get("value")
        self.stop()


class SetupMenu(discord.ui.Modal, title="Walrus Setup"):
    name = discord.ui.TextInput(
        label="Walrus name",
        style=discord.TextStyle.short,
        required=True,
        placeholder="Encyclopedia Chromatica 2",
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            f"**{self.name}** is now ready for setup. Add categories with `walctl addc`."
        )
        self.stop()


class Walrus(commands.Cog):
    """
    Welcome to Walrus!

    This is created to mess with Discord user [redacted] hf.
    """

    def __init__(self, bot: Bot):
        self.bot = bot

        db_dir = "databases/"
        db_file = f"{db_dir}/walrus.db"
        Path(db_dir).mkdir(exist_ok=True)

        engine = create_engine(f"sqlite:///{db_file}")
        session_maker = sessionmaker(bind=engine)

        self.session = session_maker()
        walr.Base.metadata.create_all(engine)

    def ongoing_walrus(self, host: discord.User) -> walr.Walrus:
        return (
            self.session.query(walr.Walrus)
            .filter(
                walr.Walrus.host_id == host.id,
                walr.Walrus.state.in_([walr.WalrusState.SETUP, walr.WalrusState.ONGOING]),
            )
            .one_or_none()
        )

    async def fail_if_ongoing_walrus(self, ctx: commands.Context):
        wal = self.ongoing_walrus(ctx.author)
        if wal:
            await ctx.message.add_reaction(self.bot.redtick)
            await ctx.send(f"{ctx.author}, you already have a walrus ongoing: **{wal.name}**.")
            raise RuntimeError()

    async def fail_if_no_walrus(self, ctx: commands.Context):
        wal = self.ongoing_walrus(ctx.author)
        if not wal:
            await ctx.message.add_reaction(self.bot.redtick)
            await ctx.send(f"{ctx.author}, you don't have a walrus ongoing.")
            raise RuntimeError()
        return wal

    @commands.group(invoke_without_command=True)
    async def walctl(self, ctx: commands.Context):
        wal = self.ongoing_walrus(ctx.author)
        if wal:
            resp = f"Your current ongoing walrus is **{wal.name}**."
            if wal.categories:
                resp += " It has the following categories"
                if wal.state == walr.WalrusState.SETUP:
                    resp += " (so far)"
                resp += ":\n"
                for cat in wal.categories:
                    resp += f"• {cat.name}\n"
                if wal.state == walr.WalrusState.SETUP:
                    resp += "When you're ready to start your walrus, use `walctl start`."
            else:
                resp += " It has no categories (yet); get working on that!"
        else:
            resp = "You have no ongoing walrus."
        await ctx.send(resp)

    @walctl.command(name="setup")
    async def walctl_setup(self, ctx: commands.Context):
        """Set up a new walrus."""
        await self.fail_if_ongoing_walrus(ctx)
        menu = SetupMenu()
        await ctx.send(view=menu_opener_button("Setup a new Walrus", menu))
        await menu.wait()
        wal = walr.Walrus(name=menu.name.value, host_id=ctx.author.id, state=walr.WalrusState.SETUP)
        self.session.add(wal)
        self.session.commit()

    @walctl.command(name="addc")
    async def walctl_addc(self, ctx: commands.Context, category: str):
        """Add a category to a walrus during setup."""
        wal = await self.fail_if_no_walrus(ctx)
        if wal.state != walr.WalrusState.SETUP:
            await ctx.send("You can't add new categories to an ongoing walrus.")
            await ctx.message.add_reaction(self.bot.redtick)
            return
        cat = walr.Category(name=category, walrus_id=wal.id)
        self.session.add(cat)
        try:
            self.session.commit()
            await ctx.message.add_reaction(self.bot.greentick)
        except sqlalchemy.exc.IntegrityError:
            self.session.rollback()
            await ctx.message.add_reaction(self.bot.redtick)
            await ctx.send(f"**{wal.name}** already has a category *{category}*.")

    @walctl.command(name="start")
    async def walctl_start(self, ctx: commands.Context):
        """Start a walrus."""
        wal = await self.fail_if_no_walrus(ctx)
        wal.state = walr.WalrusState.ONGOING
        self.session.commit()
        await ctx.message.add_reaction(self.bot.greentick)
        await ctx.send(f"Your walrus has begun. Entrants can submit songs using `walrus submit {ctx.author}`.")

    @walctl.command(name="end")
    async def walctl_end(self, ctx: commands.Context):
        """End an ongoing walrus."""
        wal = await self.fail_if_no_walrus(ctx)
        # TODO
        await ctx.send("TODO: Implement lol.")

    @walctl.command(name="distribute")
    async def walctl_distribute(self, ctx: commands.Context):
        """Distribute walrus submissions to submitters to score."""
        wal = await self.fail_if_no_walrus(ctx)
        # TODO
        await ctx.send("TODO: Implement lol.")

    @commands.group(invoke_without_command=True)
    async def walrus(self, ctx: commands.Context):
        await self.walrus_ls(ctx)

    @walrus.command(name="ls")
    async def walrus_ls(self, ctx: commands.Context):
        """List ongoing walruses."""
        walruses = self.session.query(walr.Walrus).filter_by(state=walr.WalrusState.ONGOING).all()
        if not walruses:
            await ctx.send("No ongoing walruses.")
            return
        resp = "**Ongoing walruses**\n"
        for walrus in walruses:
            resp += f"• `{self.bot.get_user(walrus.host_id)}`: _{walrus.name}_"
        await ctx.send(resp)

    @walrus.command(name="submit")
    async def walrus_submit(self, ctx: commands.Context, host: discord.User):
        """Submit songs to a host's walrus."""
        walrus = self.ongoing_walrus(host)
        if walrus.state != walr.WalrusState.ONGOING:
            await ctx.message.add_reaction(self.bot.redtick)
            await ctx.send(f"{walrus.name} is still in the setup stage.")
            return
        menu = SubmitMenu(walrus.categories)
        view = menu_opener_button("Submit songs", menu)
        await ctx.send(view=view)
        await menu.wait()
        for cat_id, value in menu.values.items():
            submission = (
                self.session.query(walr.Submission)
                .filter_by(submitter_id=ctx.author.id, category_id=cat_id)
                .one_or_none()
            )
            if submission:
                submission.link = value
                continue
            self.session.add(walr.Submission(link=value, submitter_id=ctx.author.id, category_id=cat_id))

        self.session.commit()

        await ctx.message.add_reaction(self.bot.greentick)

    # @walrus.command(name="score")
    # async def walrus_score(self, ctx: commands.Context):
    #     """Score submissions assigned to you."""
    #     ...


async def setup(bot: Bot):
    await bot.add_cog(Walrus(bot))
