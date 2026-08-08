"""Smoke tests for hybrid command registration."""

from unittest.mock import MagicMock, patch

import discord
import pytest
from discord.ext import commands


@pytest.fixture
def mock_bot():
    """Create a minimal mock bot for testing cog loading."""
    bot = MagicMock(spec=commands.Bot)
    bot.loop = MagicMock()
    bot.user = MagicMock()
    bot.user.id = 123456789
    bot.owner_id = 987654321
    bot.default_command_prefix = "##"

    # Mock emoji attributes
    bot.greentick = "✅"
    bot.redtick = "❌"
    bot.waitemoji = "⏳"
    bot.boostemoji = "🚀"

    # Mock google credentials
    bot.google_creds = None
    bot.google_scope = None

    # Track added cogs and commands
    bot._cogs = {}
    bot._commands = {}

    async def add_cog(cog):
        bot._cogs[cog.__class__.__name__] = cog
        for cmd in cog.get_commands():
            bot._commands[cmd.qualified_name] = cmd

    bot.add_cog = add_cog

    return bot


def get_hybrid_commands(cog: commands.Cog) -> list[commands.HybridCommand | commands.HybridGroup]:
    """Extract all hybrid commands from a cog."""
    hybrid_cmds = []
    for cmd in cog.get_commands():
        if isinstance(cmd, (commands.HybridCommand, commands.HybridGroup)):
            hybrid_cmds.append(cmd)
            # Also check subcommands for groups
            if isinstance(cmd, commands.HybridGroup):
                for subcmd in cmd.commands:
                    if isinstance(subcmd, commands.HybridCommand):
                        hybrid_cmds.append(subcmd)
    return hybrid_cmds


def get_all_commands(cog: commands.Cog) -> list[commands.Command]:
    """Get all commands including subcommands."""
    all_cmds = []
    for cmd in cog.get_commands():
        all_cmds.append(cmd)
        if isinstance(cmd, commands.Group):
            for subcmd in cmd.walk_commands():
                all_cmds.append(subcmd)
    return all_cmds


class TestMacroCog:
    """Test cogs/macro.py hybrid commands."""

    @pytest.fixture
    def cog(self, mock_bot):
        from cogs.macro import Macro

        return Macro(mock_bot)

    def test_cog_loads(self, cog):
        assert cog is not None

    def test_hybrid_commands_registered(self, cog):
        hybrid_cmds = get_hybrid_commands(cog)
        cmd_names = [c.name for c in hybrid_cmds]

        assert "bidoof" in cmd_names
        assert "sadcat" in cmd_names

    def test_commands_have_descriptions(self, cog):
        for cmd in get_hybrid_commands(cog):
            assert cmd.description, f"{cmd.name} missing description"


class TestUtilityCog:
    """Test cogs/utility.py hybrid commands."""

    @pytest.fixture
    def cog(self, mock_bot):
        from cogs.utility import Utility

        return Utility(mock_bot)

    def test_cog_loads(self, cog):
        assert cog is not None

    def test_hybrid_commands_registered(self, cog):
        hybrid_cmds = get_hybrid_commands(cog)
        cmd_names = [c.name for c in hybrid_cmds]

        expected = ["avatar", "bigmoji", "ping", "roll", "trunc", "choose"]
        for name in expected:
            assert name in cmd_names, f"{name} not registered as hybrid"

    def test_bigmoji_uses_string_param(self, cog):
        """Verify bigmoji uses str instead of unsupported Emoji union."""
        cmd = next(c for c in cog.get_commands() if c.name == "bigmoji")
        params = cmd.clean_params
        assert "emoji" in params
        # The annotation should be str, not a union
        assert params["emoji"].annotation is str


class TestScryfallCog:
    """Test cogs/scryfall.py hybrid commands."""

    @pytest.fixture
    def cog(self, mock_bot):
        # Cards cog requires db session, so we mock it
        with patch("cogs.scryfall.async_sessionmaker"), patch("cogs.scryfall.create_async_engine"):
            from cogs.scryfall import Cards

            return Cards(mock_bot, MagicMock(), "test.db")

    def test_cog_loads(self, cog):
        assert cog is not None

    def test_hybrid_commands_registered(self, cog):
        hybrid_cmds = get_hybrid_commands(cog)
        cmd_names = [c.name for c in hybrid_cmds]

        expected = ["oracle", "ygo", "ygot", "dt", "ygocsv", "sftext"]
        for name in expected:
            assert name in cmd_names, f"{name} not registered as hybrid"


class TestEmojiCountCog:
    """Test cogs/emoji_count.py hybrid commands."""

    @pytest.fixture
    def cog(self, mock_bot):
        from cogs.emoji_count import Emoji

        return Emoji(mock_bot)

    def test_cog_loads(self, cog):
        assert cog is not None

    def test_emoji_group_is_hybrid(self, cog):
        emoji_cmd = next(c for c in cog.get_commands() if c.name == "emoji")
        assert isinstance(emoji_cmd, commands.HybridGroup)

    def test_evemoji_group_is_hybrid(self, cog):
        evemoji_cmd = next(c for c in cog.get_commands() if c.name == "evemoji")
        assert isinstance(evemoji_cmd, commands.HybridGroup)

    def test_emoji_subcommands_exist(self, cog):
        emoji_cmd = next(c for c in cog.get_commands() if c.name == "emoji")
        subcmd_names = [c.name for c in emoji_cmd.commands]

        expected = ["enable", "disable", "count", "stats", "head", "tail", "all", "export"]
        for name in expected:
            assert name in subcmd_names, f"emoji {name} subcommand missing"

    def test_emoji_params_are_strings(self, cog):
        """Verify emoji parameters use str instead of unsupported unions."""
        emoji_cmd = next(c for c in cog.get_commands() if c.name == "emoji")

        count_cmd = next(c for c in emoji_cmd.commands if c.name == "count")
        assert count_cmd.clean_params["em"].annotation is str

        stats_cmd = next(c for c in emoji_cmd.commands if c.name == "stats")
        # str | None is fine
        assert "str" in str(stats_cmd.clean_params["em"].annotation)


class TestHostbotCog:
    """Test cogs/hostbot.py hybrid commands."""

    @pytest.fixture
    def cog(self, mock_bot):
        # Need to patch the database setup
        with (
            patch("cogs.hostbot.create_engine"),
            patch("cogs.hostbot.sessionmaker"),
            patch("cogs.hostbot.spreadsheet.SheetConnection"),
        ):
            from cogs.hostbot import HostBot

            return HostBot(mock_bot)

    def test_cog_loads(self, cog):
        assert cog is not None

    def test_init_group_is_hybrid(self, cog):
        init_cmd = next(c for c in cog.get_commands() if c.name == "init")
        assert isinstance(init_cmd, commands.HybridGroup)

    def test_init_subcommands_exist(self, cog):
        init_cmd = next(c for c in cog.get_commands() if c.name == "init")
        subcmd_names = [c.name for c in init_cmd.commands]

        expected = ["server", "badly", "pmlist", "reset", "setrole", "setchan", "status"]
        for name in expected:
            assert name in subcmd_names, f"init {name} subcommand missing"

    def test_addspec_group_is_hybrid(self, cog):
        addspec_cmd = next(c for c in cog.get_commands() if c.name == "addspec")
        assert isinstance(addspec_cmd, commands.HybridGroup)

    def test_addspec_subcommands_exist(self, cog):
        addspec_cmd = next(c for c in cog.get_commands() if c.name == "addspec")
        subcmd_names = [c.name for c in addspec_cmd.commands]

        expected = ["all", "rm", "off", "on"]
        for name in expected:
            assert name in subcmd_names, f"addspec {name} subcommand missing"

    def test_standalone_hybrid_commands(self, cog):
        hybrid_cmds = get_hybrid_commands(cog)
        cmd_names = [c.name for c in hybrid_cmds]

        expected = ["confessional", "gameavatars", "enrole", "lock", "unlock"]
        for name in expected:
            assert name in cmd_names, f"{name} not registered as hybrid"

    def test_enrole_uses_string_members(self, cog):
        """Verify enrole uses str instead of Greedy[Member]."""
        enrole_cmd = next(c for c in cog.get_commands() if c.name == "enrole")
        params = enrole_cmd.clean_params
        assert "members" in params
        assert params["members"].annotation is str

    def test_addspec_uses_string_members(self, cog):
        """Verify addspec uses str instead of Greedy[Member]."""
        addspec_cmd = next(c for c in cog.get_commands() if c.name == "addspec")
        params = addspec_cmd.clean_params
        assert "members" in params
        assert params["members"].annotation is str

    def test_setchan_uses_guild_channel(self, cog):
        """Verify setchan uses GuildChannel for union type compatibility."""
        init_cmd = next(c for c in cog.get_commands() if c.name == "init")
        setchan_cmd = next(c for c in init_cmd.commands if c.name == "setchan")
        params = setchan_cmd.clean_params
        assert "channel" in params
        assert params["channel"].annotation == discord.abc.GuildChannel


class TestResolveMembersHelper:
    """Test utils/members.py helper function."""

    @pytest.fixture
    def mock_guild(self):
        guild = MagicMock(spec=discord.Guild)

        # Create mock members
        member1 = MagicMock(spec=discord.Member)
        member1.id = 111111111111111111
        member2 = MagicMock(spec=discord.Member)
        member2.id = 222222222222222222
        member3 = MagicMock(spec=discord.Member)
        member3.id = 333333333333333333

        def get_member(user_id):
            members = {
                111111111111111111: member1,
                222222222222222222: member2,
                333333333333333333: member3,
            }
            return members.get(user_id)

        guild.get_member = get_member
        return guild, [member1, member2, member3]

    @pytest.mark.asyncio
    async def test_resolve_mentions(self, mock_guild):
        from utils.members import resolve_members

        guild, members = mock_guild

        result = await resolve_members(guild, "<@111111111111111111> <@222222222222222222>")
        assert len(result) == 2
        assert members[0] in result
        assert members[1] in result

    @pytest.mark.asyncio
    async def test_resolve_mentions_with_nickname(self, mock_guild):
        from utils.members import resolve_members

        guild, members = mock_guild

        # Nickname mention format <@!id>
        result = await resolve_members(guild, "<@!111111111111111111>")
        assert len(result) == 1
        assert members[0] in result

    @pytest.mark.asyncio
    async def test_resolve_raw_ids(self, mock_guild):
        from utils.members import resolve_members

        guild, members = mock_guild

        result = await resolve_members(guild, "111111111111111111 222222222222222222")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_resolve_mixed(self, mock_guild):
        from utils.members import resolve_members

        guild, members = mock_guild

        result = await resolve_members(guild, "<@111111111111111111> 222222222222222222 <@!333333333333333333>")
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_resolve_skips_unknown(self, mock_guild):
        from utils.members import resolve_members

        guild, members = mock_guild

        result = await resolve_members(guild, "<@111111111111111111> <@999999999999999999>")
        assert len(result) == 1
        assert members[0] in result

    @pytest.mark.asyncio
    async def test_resolve_deduplicates(self, mock_guild):
        from utils.members import resolve_members

        guild, members = mock_guild

        result = await resolve_members(guild, "<@111111111111111111> <@111111111111111111> 111111111111111111")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_resolve_empty_string(self, mock_guild):
        from utils.members import resolve_members

        guild, _ = mock_guild

        result = await resolve_members(guild, "")
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_resolve_no_matches(self, mock_guild):
        from utils.members import resolve_members

        guild, _ = mock_guild

        result = await resolve_members(guild, "hello world no ids here")
        assert len(result) == 0
