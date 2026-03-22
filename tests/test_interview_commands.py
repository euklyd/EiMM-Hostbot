"""Tests for interview command utilities and guard behaviour."""

import contextlib
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from cogs.interview.commands import Interview, TextChannelConverter, _MemberOrStr
from cogs.interview.models import InterviewServer


@pytest.fixture
def mock_text_channel() -> MagicMock:
    """Create a mock TextChannel."""
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 123456789012345678
    channel.name = "test-channel"
    channel.mention = "<#123456789012345678>"
    return channel


@pytest.fixture
def mock_guild_with_channel(mock_text_channel: MagicMock) -> MagicMock:
    """Create a mock guild that has a channel."""
    guild = MagicMock()
    guild.id = 444555666
    guild.name = "Test Server"

    def get_channel(channel_id: int) -> discord.TextChannel | None:
        if channel_id == mock_text_channel.id:
            return mock_text_channel
        return None

    guild.get_channel = get_channel
    return guild


@pytest.fixture
def mock_ctx_for_converter(mock_guild_with_channel: MagicMock, mock_bot: MagicMock) -> MagicMock:
    """Create a mock context for converter tests."""
    ctx = MagicMock()
    ctx.bot = mock_bot
    ctx.guild = mock_guild_with_channel
    return ctx


@pytest.fixture
def interview_cog(mock_bot: MagicMock) -> Interview:
    """Create an Interview cog with a mock bot (no DB setup needed)."""
    return Interview(mock_bot)


@pytest.fixture
def mock_ctx(mock_bot: MagicMock) -> MagicMock:
    """Create a mock Discord context suitable for interview command tests."""
    ctx = MagicMock()
    ctx.bot = mock_bot
    ctx.guild = MagicMock()
    ctx.guild.id = 444555666
    ctx.guild.name = "Test Server"
    ctx.author = MagicMock()
    ctx.author.id = 987654321
    ctx.author.name = "TestUser"
    ctx.author.guild_permissions = MagicMock()
    ctx.author.guild_permissions.administrator = False
    ctx.author.roles = []
    ctx.channel = MagicMock()
    ctx.channel.id = 111222333
    ctx.message = MagicMock()
    ctx.prefix = "##"
    ctx.send = AsyncMock()
    return ctx


def make_get_session(server=None):
    """Return a get_session replacement that yields a fake session and patches get_server."""

    @asynccontextmanager
    async def _inner():
        yield AsyncMock()

    return _inner


def _server(active: bool) -> InterviewServer:
    """Build a minimal InterviewServer stub."""
    s = MagicMock(spec=InterviewServer)
    s.id = 444555666
    s.name = "Test Server"
    s.active = active
    s.manager_role_id = None
    s.audience_role_id = None
    return s


# =============================================================================
# Phase 1: Guard helper tests
# =============================================================================


class TestRequireHelpers:
    """Tests for _require_server and _require_active helpers."""

    async def test_require_server_not_configured(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        """_require_server returns None and sends error when server is not configured."""
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=None)),
        ):
            result = await interview_cog._require_server(mock_ctx)

        assert result is None
        mock_ctx.send.assert_called_once()
        call_kwargs = mock_ctx.send.call_args
        assert "not configured" in call_kwargs.args[0].lower()
        assert call_kwargs.kwargs.get("ephemeral") is True

    async def test_require_server_configured_disabled(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        """_require_server returns the server even when active=False."""
        server = _server(active=False)
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=server)),
        ):
            result = await interview_cog._require_server(mock_ctx)

        assert result is server
        mock_ctx.send.assert_not_called()

    async def test_require_server_configured_active(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        """_require_server returns the server when active=True."""
        server = _server(active=True)
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=server)),
        ):
            result = await interview_cog._require_server(mock_ctx)

        assert result is server
        mock_ctx.send.assert_not_called()

    async def test_require_active_not_configured(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        """_require_active returns None and sends 'not configured' when server is absent."""
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=None)),
        ):
            result = await interview_cog._require_active(mock_ctx)

        assert result is None
        mock_ctx.send.assert_called_once()
        assert "not configured" in mock_ctx.send.call_args.args[0].lower()
        assert mock_ctx.send.call_args.kwargs.get("ephemeral") is True

    async def test_require_active_configured_disabled(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        """_require_active returns None and sends 'disabled' when active=False."""
        server = _server(active=False)
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=server)),
        ):
            result = await interview_cog._require_active(mock_ctx)

        assert result is None
        mock_ctx.send.assert_called_once()
        assert "disabled" in mock_ctx.send.call_args.args[0].lower()
        assert mock_ctx.send.call_args.kwargs.get("ephemeral") is True

    async def test_require_active_configured_active(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        """_require_active returns the server when active=True."""
        server = _server(active=True)
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=server)),
        ):
            result = await interview_cog._require_active(mock_ctx)

        assert result is server
        mock_ctx.send.assert_not_called()


# =============================================================================
# Phase 2: ask / mask guard tests (regression for the re-added guard)
# =============================================================================


def _call(cog: Interview, cmd_name: str, ctx: MagicMock, **kwargs):
    """Call a hybrid/group command's underlying callback directly.

    Hybrid commands attached to a Cog are descriptor-wrapped; when the cog
    instance hasn't been registered with a Bot, ``cmd.cog`` is None and
    calling ``await cog.cmd(ctx, ...)`` falls through to the wrong code path.
    Bypassing the wrapper via ``.callback`` fixes that.
    """
    cmd = getattr(cog, cmd_name)
    return cmd.callback(cog, ctx, **kwargs)


class TestAskMaskGuards:
    """Regression tests: ask and mask must reject when system is off."""

    async def test_ask_not_configured(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=None)),
        ):
            await _call(interview_cog, "ask", mock_ctx, question="hello")

        mock_ctx.send.assert_called_once()
        assert "not configured" in mock_ctx.send.call_args.args[0].lower()

    async def test_ask_disabled(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        server = _server(active=False)
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=server)),
        ):
            await _call(interview_cog, "ask", mock_ctx, question="hello")

        mock_ctx.send.assert_called_once()
        assert "disabled" in mock_ctx.send.call_args.args[0].lower()

    async def test_ask_active_no_interview(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        server = _server(active=True)
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=server)),
            patch("cogs.interview.commands.service.get_current_interview", new=AsyncMock(return_value=None)),
        ):
            await _call(interview_cog, "ask", mock_ctx, question="hello")

        mock_ctx.send.assert_called_once()
        assert "no interview" in mock_ctx.send.call_args.args[0].lower()

    async def test_mask_not_configured(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=None)),
        ):
            await _call(interview_cog, "mask", mock_ctx, questions="hello")

        mock_ctx.send.assert_called_once()
        assert "not configured" in mock_ctx.send.call_args.args[0].lower()

    async def test_mask_disabled(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        server = _server(active=False)
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=server)),
        ):
            await _call(interview_cog, "mask", mock_ctx, questions="hello")

        mock_ctx.send.assert_called_once()
        assert "disabled" in mock_ctx.send.call_args.args[0].lower()

    async def test_mask_active_no_interview(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        server = _server(active=True)
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=server)),
            patch("cogs.interview.commands.service.get_current_interview", new=AsyncMock(return_value=None)),
        ):
            await _call(interview_cog, "mask", mock_ctx, questions="hello")

        mock_ctx.send.assert_called_once()
        assert "no interview" in mock_ctx.send.call_args.args[0].lower()


# =============================================================================
# Phase 3: Voting command guard tests
# =============================================================================


class TestVotingGuards:
    """Tests for vote/unvote/votes/votals guard behaviour."""

    async def test_vote_not_configured(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        candidate = MagicMock(spec=discord.Member)
        candidate.bot = False
        candidate.id = 111
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=None)),
        ):
            await _call(interview_cog, "vote", mock_ctx, candidate1=candidate)

        mock_ctx.send.assert_called_once()
        assert "not configured" in mock_ctx.send.call_args.args[0].lower()

    async def test_vote_disabled(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        candidate = MagicMock(spec=discord.Member)
        candidate.bot = False
        candidate.id = 111
        server = _server(active=False)
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=server)),
        ):
            await _call(interview_cog, "vote", mock_ctx, candidate1=candidate)

        mock_ctx.send.assert_called_once()
        assert "disabled" in mock_ctx.send.call_args.args[0].lower()

    async def test_unvote_not_configured(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=None)),
        ):
            await _call(interview_cog, "unvote", mock_ctx)

        mock_ctx.send.assert_called_once()
        assert "not configured" in mock_ctx.send.call_args.args[0].lower()

    async def test_unvote_disabled(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        server = _server(active=False)
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=server)),
        ):
            await _call(interview_cog, "unvote", mock_ctx)

        mock_ctx.send.assert_called_once()
        assert "disabled" in mock_ctx.send.call_args.args[0].lower()

    async def test_votes_not_configured(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=None)),
        ):
            await _call(interview_cog, "votes", mock_ctx)

        mock_ctx.send.assert_called_once()
        assert "not configured" in mock_ctx.send.call_args.args[0].lower()

    async def test_votes_disabled_allowed(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        """votes uses _require_server (not _require_active), so disabled is OK."""
        server = _server(active=False)
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=server)),
            patch("cogs.interview.commands.service.get_user_votes", new=AsyncMock(return_value=[])),
        ):
            await _call(interview_cog, "votes", mock_ctx)

        # Should NOT send a guard error — should reach the "haven't voted" branch
        mock_ctx.send.assert_called_once()
        assert "haven't voted" in mock_ctx.send.call_args.args[0].lower()

    async def test_votals_not_configured(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=None)),
        ):
            await _call(interview_cog, "votals", mock_ctx)

        mock_ctx.send.assert_called_once()
        assert "not configured" in mock_ctx.send.call_args.args[0].lower()

    async def test_votals_disabled_allowed(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        """votals uses _require_server, so it works when disabled."""
        server = _server(active=False)
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=server)),
            patch("cogs.interview.commands.service.get_user_votes", new=AsyncMock(return_value=[])),
            patch("cogs.interview.commands.service.get_votals", new=AsyncMock(return_value=[])),
        ):
            await _call(interview_cog, "votals", mock_ctx)

        # Should reach "No votes yet!" downstream, not a guard error
        mock_ctx.send.assert_called_once()
        sent_text = mock_ctx.send.call_args.args[0]
        assert "no votes yet" in sent_text.lower()
        assert "not configured" not in sent_text.lower()
        assert "disabled" not in sent_text.lower()


# =============================================================================
# Phase 4: Opt command guard tests
# =============================================================================


class TestOptGuards:
    """Tests for opt_out / opt_in / opt_list guard behaviour."""

    async def test_opt_out_not_configured(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=None)),
        ):
            await _call(interview_cog, "opt_out", mock_ctx)

        mock_ctx.send.assert_called_once()
        assert "not configured" in mock_ctx.send.call_args.args[0].lower()

    async def test_opt_out_disabled(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        server = _server(active=False)
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=server)),
        ):
            await _call(interview_cog, "opt_out", mock_ctx)

        mock_ctx.send.assert_called_once()
        assert "disabled" in mock_ctx.send.call_args.args[0].lower()

    async def test_opt_in_not_configured(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=None)),
        ):
            await _call(interview_cog, "opt_in", mock_ctx)

        mock_ctx.send.assert_called_once()
        assert "not configured" in mock_ctx.send.call_args.args[0].lower()

    async def test_opt_in_disabled(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        server = _server(active=False)
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=server)),
        ):
            await _call(interview_cog, "opt_in", mock_ctx)

        mock_ctx.send.assert_called_once()
        assert "disabled" in mock_ctx.send.call_args.args[0].lower()

    async def test_opt_list_not_configured(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=None)),
        ):
            await _call(interview_cog, "opt_list", mock_ctx)

        mock_ctx.send.assert_called_once()
        assert "not configured" in mock_ctx.send.call_args.args[0].lower()

    async def test_opt_list_disabled_allowed(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        """opt_list uses _require_server, so it passes even when disabled."""
        server = _server(active=False)
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=server)),
            patch("cogs.interview.commands.service.get_opt_outs", new=AsyncMock(return_value=[])),
        ):
            await _call(interview_cog, "opt_list", mock_ctx)

        mock_ctx.send.assert_called_once()
        sent_text = mock_ctx.send.call_args.args[0]
        assert "not configured" not in sent_text.lower()
        assert "disabled" not in sent_text.lower()


# =============================================================================
# Phase 5: Management command guard tests
# =============================================================================


class TestManagementGuards:
    """Tests for iv_stats and iv_stage guard behaviour."""

    async def test_iv_stats_not_configured(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=None)),
        ):
            await _call(interview_cog, "iv_stats", mock_ctx)

        mock_ctx.send.assert_called_once()
        assert "not configured" in mock_ctx.send.call_args.args[0].lower()

    async def test_iv_stats_disabled_allowed(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        """iv_stats uses _require_server so it passes when disabled."""
        server = _server(active=False)
        stats = {"total_interviews": 0, "total_questions": 0, "avg_questions_per_interview": 0.0}
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=server)),
            patch("cogs.interview.commands.service.get_current_interview", new=AsyncMock(return_value=None)),
            patch("cogs.interview.commands.service.get_server_stats", new=AsyncMock(return_value=stats)),
            patch("cogs.interview.commands.service.get_top_askers", new=AsyncMock(return_value=[])),
            patch("cogs.interview.commands.service.get_interview_archive", new=AsyncMock(return_value=[])),
        ):
            await _call(interview_cog, "iv_stats", mock_ctx)

        # Should NOT send a guard error — should have sent an embed
        mock_ctx.send.assert_called_once()
        call_args = mock_ctx.send.call_args
        assert call_args.kwargs.get("embed") is not None

    async def test_iv_stage_not_configured(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        """iv_stage body uses _require_server; admin ctx bypasses @is_interviewee_or_manager."""
        mock_ctx.author.guild_permissions.administrator = True
        mock_ctx.author.roles = []
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=None)),
            patch("cogs.interview.commands.service.get_current_interview", new=AsyncMock(return_value=None)),
        ):
            await _call(interview_cog, "iv_stage", mock_ctx)

        mock_ctx.send.assert_called_once()
        assert "not configured" in mock_ctx.send.call_args.args[0].lower()

    async def test_iv_stage_disabled_allowed(self, interview_cog: Interview, mock_ctx: MagicMock) -> None:
        """iv_stage uses _require_server so it passes when disabled."""
        mock_ctx.author.guild_permissions.administrator = True
        mock_ctx.author.roles = []
        server = _server(active=False)
        server.audience_role_id = None
        with (
            patch("cogs.interview.commands.get_session", make_get_session()),
            patch("cogs.interview.commands.service.get_server", new=AsyncMock(return_value=server)),
            patch("cogs.interview.commands.service.get_current_interview", new=AsyncMock(return_value=None)),
        ):
            await _call(interview_cog, "iv_stage", mock_ctx)

        # Should pass guard and reach "No audience role configured" branch
        mock_ctx.send.assert_called_once()
        sent_text = mock_ctx.send.call_args.args[0]
        assert "audience" in sent_text.lower()
        assert "disabled" not in sent_text.lower()


# =============================================================================
# Converter tests (pre-existing, kept here for consolidation)
# =============================================================================


class TestTextChannelConverter:
    """Tests for the TextChannelConverter."""

    async def test_convert_channel_mention(
        self, mock_ctx_for_converter: MagicMock, mock_text_channel: MagicMock
    ) -> None:
        """Convert a channel mention like <#123456789012345678>."""
        converter = TextChannelConverter()

        with patch.object(commands.TextChannelConverter, "convert") as mock_convert:
            mock_convert.return_value = mock_text_channel

            result = await converter.convert(mock_ctx_for_converter, "<#123456789012345678>")

            assert result == mock_text_channel
            mock_convert.assert_called_once()

    async def test_convert_channel_name(self, mock_ctx_for_converter: MagicMock, mock_text_channel: MagicMock) -> None:
        """Convert a channel name like 'test-channel'."""
        converter = TextChannelConverter()

        with patch.object(commands.TextChannelConverter, "convert") as mock_convert:
            mock_convert.return_value = mock_text_channel

            result = await converter.convert(mock_ctx_for_converter, "test-channel")

            assert result == mock_text_channel
            mock_convert.assert_called_once()

    async def test_convert_raw_snowflake(self, mock_ctx_for_converter: MagicMock, mock_text_channel: MagicMock) -> None:
        """Convert a raw snowflake ID like '123456789012345678'."""
        converter = TextChannelConverter()

        with patch.object(commands.TextChannelConverter, "convert") as mock_convert:
            mock_convert.side_effect = commands.ChannelNotFound("123456789012345678")

            result = await converter.convert(mock_ctx_for_converter, "123456789012345678")

            assert result == mock_text_channel
            mock_convert.assert_called_once()

    async def test_convert_raw_snowflake_not_found(self, mock_ctx_for_converter: MagicMock) -> None:
        """Raise ChannelNotFound when snowflake doesn't match any channel."""
        mock_ctx_for_converter.guild.get_channel = lambda x: None
        mock_ctx_for_converter.guild.fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), "Not found"))

        converter = TextChannelConverter()

        with patch.object(commands.TextChannelConverter, "convert") as mock_convert:
            mock_convert.side_effect = commands.ChannelNotFound("999999999999999999")

            with pytest.raises(commands.ChannelNotFound):
                await converter.convert(mock_ctx_for_converter, "999999999999999999")

    async def test_convert_invalid_string(self, mock_ctx_for_converter: MagicMock) -> None:
        """Raise ChannelNotFound for invalid input."""
        converter = TextChannelConverter()

        with patch.object(commands.TextChannelConverter, "convert") as mock_convert:
            mock_convert.side_effect = commands.ChannelNotFound("not-a-valid-channel")

            with pytest.raises(commands.ChannelNotFound):
                await converter.convert(mock_ctx_for_converter, "not-a-valid-channel")

    async def test_convert_snowflake_wrong_channel_type(self, mock_ctx_for_converter: MagicMock) -> None:
        """Raise ChannelNotFound when snowflake points to non-text channel."""
        voice_channel = MagicMock(spec=discord.VoiceChannel)
        voice_channel.id = 123456789012345678
        mock_ctx_for_converter.guild.get_channel = lambda x: voice_channel if x == 123456789012345678 else None
        mock_ctx_for_converter.guild.fetch_channel = AsyncMock(return_value=voice_channel)

        converter = TextChannelConverter()

        with patch.object(commands.TextChannelConverter, "convert") as mock_convert:
            mock_convert.side_effect = commands.ChannelNotFound("123456789012345678")

            with pytest.raises(commands.ChannelNotFound):
                await converter.convert(mock_ctx_for_converter, "123456789012345678")

    async def test_convert_snowflake_fetched_when_not_cached(
        self, mock_ctx_for_converter: MagicMock, mock_text_channel: MagicMock
    ) -> None:
        """Fetch channel from API when not in cache."""
        mock_ctx_for_converter.guild.get_channel = lambda x: None
        mock_ctx_for_converter.guild.fetch_channel = AsyncMock(return_value=mock_text_channel)

        converter = TextChannelConverter()

        with patch.object(commands.TextChannelConverter, "convert") as mock_convert:
            mock_convert.side_effect = commands.ChannelNotFound("123456789012345678")

            result = await converter.convert(mock_ctx_for_converter, "123456789012345678")

            assert result == mock_text_channel
            mock_ctx_for_converter.guild.fetch_channel.assert_called_once_with(123456789012345678)

    async def test_convert_snowflake_fetch_not_found(self, mock_ctx_for_converter: MagicMock) -> None:
        """Raise ChannelNotFound when fetch fails."""
        mock_ctx_for_converter.guild.get_channel = lambda x: None
        mock_ctx_for_converter.guild.fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), "Not found"))

        converter = TextChannelConverter()

        with patch.object(commands.TextChannelConverter, "convert") as mock_convert:
            mock_convert.side_effect = commands.ChannelNotFound("123456789012345678")

            with pytest.raises(commands.ChannelNotFound):
                await converter.convert(mock_ctx_for_converter, "123456789012345678")

    async def test_convert_snowflake_with_invisible_unicode(
        self, mock_ctx_for_converter: MagicMock, mock_text_channel: MagicMock
    ) -> None:
        """Convert snowflake that has invisible Unicode chars (from Discord copy)."""
        converter = TextChannelConverter()

        snowflake_with_unicode = "\u2060123456789012345678"

        with patch.object(commands.TextChannelConverter, "convert") as mock_convert:
            mock_convert.side_effect = commands.ChannelNotFound(snowflake_with_unicode)

            result = await converter.convert(mock_ctx_for_converter, snowflake_with_unicode)

            assert result == mock_text_channel


class TestMemberOrStr:
    """Tests for the _MemberOrStr prefix converter."""

    async def test_valid_member_returns_member(self, mock_ctx_for_converter: MagicMock) -> None:
        """Returns a Member when the argument resolves to a guild member."""
        mock_member = MagicMock(spec=discord.Member)
        mock_member.name = "alice"

        with patch.object(commands.MemberConverter, "convert", new=AsyncMock(return_value=mock_member)):
            result = await _MemberOrStr().convert(mock_ctx_for_converter, "alice")

        assert result is mock_member

    async def test_invalid_member_returns_string(self, mock_ctx_for_converter: MagicMock) -> None:
        """Returns the raw string when the argument cannot be resolved to a member."""
        with patch.object(
            commands.MemberConverter, "convert", new=AsyncMock(side_effect=commands.MemberNotFound("notauser"))
        ):
            result = await _MemberOrStr().convert(mock_ctx_for_converter, "notauser")

        assert result == "notauser"
