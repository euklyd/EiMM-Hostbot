"""Shared pytest fixtures for EiMM-Hostbot tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_bot() -> MagicMock:
    """Create a mock Discord bot."""
    bot = MagicMock()
    bot.user = MagicMock()
    bot.user.id = 123456789
    bot.greentick = "\u2705"
    bot.redtick = "\u274c"
    bot.wait_for_first = AsyncMock()
    return bot


@pytest.fixture
def mock_member() -> MagicMock:
    """Create a mock Discord member."""
    member = MagicMock()
    member.id = 987654321
    member.name = "TestUser"
    member.display_name = "Test User"
    member.mention = "<@987654321>"
    return member


@pytest.fixture
def mock_channel() -> MagicMock:
    """Create a mock Discord channel."""
    channel = MagicMock()
    channel.id = 111222333
    channel.name = "test-channel"
    channel.send = AsyncMock()
    return channel


@pytest.fixture
def mock_guild() -> MagicMock:
    """Create a mock Discord guild."""
    guild = MagicMock()
    guild.id = 444555666
    guild.name = "Test Server"
    return guild


@pytest.fixture
def mock_ctx(mock_bot: MagicMock, mock_member: MagicMock, mock_channel: MagicMock, mock_guild: MagicMock) -> MagicMock:
    """Create a mock Discord context."""
    ctx = MagicMock()
    ctx.bot = mock_bot
    ctx.author = mock_member
    ctx.channel = mock_channel
    ctx.guild = mock_guild
    ctx.send = AsyncMock()
    ctx.me = MagicMock()
    ctx.me.permissions_in = MagicMock(return_value=MagicMock(manage_messages=True))
    return ctx
