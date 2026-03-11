"""Tests for interview command utilities."""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from cogs.interview.commands import TextChannelConverter, _MemberOrStr


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


class TestTextChannelConverter:
    """Tests for the TextChannelConverter."""

    async def test_convert_channel_mention(
        self, mock_ctx_for_converter: MagicMock, mock_text_channel: MagicMock
    ) -> None:
        """Convert a channel mention like <#123456789012345678>."""
        converter = TextChannelConverter()

        # Mock the standard converter to succeed for mentions
        with patch.object(commands.TextChannelConverter, "convert") as mock_convert:
            mock_convert.return_value = mock_text_channel

            result = await converter.convert(mock_ctx_for_converter, "<#123456789012345678>")

            assert result == mock_text_channel
            mock_convert.assert_called_once()

    async def test_convert_channel_name(self, mock_ctx_for_converter: MagicMock, mock_text_channel: MagicMock) -> None:
        """Convert a channel name like 'test-channel'."""
        converter = TextChannelConverter()

        # Mock the standard converter to succeed for names
        with patch.object(commands.TextChannelConverter, "convert") as mock_convert:
            mock_convert.return_value = mock_text_channel

            result = await converter.convert(mock_ctx_for_converter, "test-channel")

            assert result == mock_text_channel
            mock_convert.assert_called_once()

    async def test_convert_raw_snowflake(self, mock_ctx_for_converter: MagicMock, mock_text_channel: MagicMock) -> None:
        """Convert a raw snowflake ID like '123456789012345678'."""
        converter = TextChannelConverter()

        # Mock the standard converter to FAIL (so we fall through to snowflake handling)
        with patch.object(commands.TextChannelConverter, "convert") as mock_convert:
            mock_convert.side_effect = commands.ChannelNotFound("123456789012345678")

            result = await converter.convert(mock_ctx_for_converter, "123456789012345678")

            assert result == mock_text_channel
            # Verify we tried standard converter first
            mock_convert.assert_called_once()

    async def test_convert_raw_snowflake_not_found(self, mock_ctx_for_converter: MagicMock) -> None:
        """Raise ChannelNotFound when snowflake doesn't match any channel."""
        # Mock get_channel to return None and fetch_channel to raise NotFound
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
        # Make the guild return a voice channel instead
        voice_channel = MagicMock(spec=discord.VoiceChannel)
        voice_channel.id = 123456789012345678
        mock_ctx_for_converter.guild.get_channel = lambda x: voice_channel if x == 123456789012345678 else None
        # Also mock fetch_channel to return the same voice channel
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
        # get_channel returns None (not cached)
        mock_ctx_for_converter.guild.get_channel = lambda x: None
        # fetch_channel returns the channel
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

        # Simulate what Discord does when copying IDs - adds zero-width chars
        # U+2060 WORD JOINER is commonly inserted
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
