"""Tests for cogs/hostbot.py business logic."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import discord

from cogs.hostbot import HostBot, NotFoundMember


class TestNotFoundMember:
    """Tests for the NotFoundMember class."""

    def test_valid_name_and_discriminator(self) -> None:
        """Valid 'name#discriminator' format should be parsed."""
        member = NotFoundMember("TestUser#1234")
        assert member.name == "TestUser"
        assert member.discriminator == 1234

    def test_missing_discriminator(self) -> None:
        """Missing discriminator should default to '----'."""
        member = NotFoundMember("TestUser")
        assert member.name == "TestUser"
        assert member.discriminator == "----"

    def test_name_with_spaces(self) -> None:
        """Names with spaces should be handled."""
        member = NotFoundMember("Test User#5678")
        assert member.name == "Test User"
        assert member.discriminator == 5678

    def test_name_with_special_chars(self) -> None:
        """Names with special characters should be handled."""
        member = NotFoundMember("Test_User-123#9999")
        assert member.name == "Test_User-123"
        assert member.discriminator == 9999

    def test_str_formatting(self) -> None:
        """__str__ should format as 'name#discriminator'."""
        member = NotFoundMember("TestUser#1234")
        assert str(member) == "TestUser#1234"

    def test_str_formatting_no_discriminator(self) -> None:
        """__str__ with missing discriminator should show dashes."""
        member = NotFoundMember("TestUser")
        assert str(member) == "TestUser#----"


class TestPlayerChannelName:
    """Tests for the _player_channel_name static method."""

    def test_simple_name(self) -> None:
        """Simple name should be formatted correctly."""
        member = MagicMock(spec=discord.Member)
        member.name = "TestUser"
        member.discriminator = 1234
        result = HostBot._player_channel_name(member)
        assert result == "TestUser-1234"

    def test_name_with_spaces(self) -> None:
        """Spaces should be removed (not replaced with hyphens)."""
        member = MagicMock(spec=discord.Member)
        member.name = "Test User"
        member.discriminator = 5678
        result = HostBot._player_channel_name(member)
        # Spaces are removed by the first regex, not replaced
        assert result == "TestUser-5678"

    def test_name_with_special_chars(self) -> None:
        """Special characters should be removed."""
        member = MagicMock(spec=discord.Member)
        member.name = "Test@User!#$%"
        member.discriminator = 1111
        result = HostBot._player_channel_name(member)
        assert result == "TestUser-1111"

    def test_name_with_underscores(self) -> None:
        """Underscores should be removed."""
        member = MagicMock(spec=discord.Member)
        member.name = "Test_User"
        member.discriminator = 2222
        result = HostBot._player_channel_name(member)
        assert result == "TestUser-2222"

    def test_discriminator_padding(self) -> None:
        """Discriminator should be zero-padded to 4 digits."""
        member = MagicMock(spec=discord.Member)
        member.name = "User"
        member.discriminator = 1
        result = HostBot._player_channel_name(member)
        assert result == "User-0001"

    def test_unicode_name(self) -> None:
        """Unicode characters are preserved (regex only strips ASCII special chars)."""
        member = MagicMock(spec=discord.Member)
        member.name = "用户Test"
        member.discriminator = 3333
        result = HostBot._player_channel_name(member)
        # Unicode word characters are preserved by \W regex
        assert result == "用户Test-3333"


class TestIncCooldown:
    """Tests for the _inc_cooldown method."""

    def setup_method(self) -> None:
        """Set up a fresh HostBot instance for each test."""
        # Create a minimal mock that bypasses __init__
        self.hostbot = object.__new__(HostBot)
        self.hostbot.confessional_cooldowns = {}

    def test_first_usage_allowed(self) -> None:
        """First usage should be allowed."""
        user = MagicMock(spec=discord.Member)
        user.id = 12345
        result = self.hostbot._inc_cooldown(user)
        assert result is True
        assert user.id in self.hostbot.confessional_cooldowns

    def test_within_limit_allowed(self) -> None:
        """Usage within limit (3 per 30 min) should be allowed."""
        user = MagicMock(spec=discord.Member)
        user.id = 12345
        # First two usages
        assert self.hostbot._inc_cooldown(user) is True
        assert self.hostbot._inc_cooldown(user) is True
        # Third usage (at limit)
        assert self.hostbot._inc_cooldown(user) is True
        assert len(self.hostbot.confessional_cooldowns[user.id]) == 3

    def test_exceeds_limit_within_window_blocked(self) -> None:
        """Fourth usage within 30 min window should be blocked."""
        user = MagicMock(spec=discord.Member)
        user.id = 12345
        # Use up all 3 slots
        self.hostbot._inc_cooldown(user)
        self.hostbot._inc_cooldown(user)
        self.hostbot._inc_cooldown(user)
        # Fourth should be blocked
        result = self.hostbot._inc_cooldown(user)
        assert result is False

    def test_after_window_resets(self) -> None:
        """Usage after window expires should be allowed."""
        user = MagicMock(spec=discord.Member)
        user.id = 12345
        # Set up 3 usages from 31 minutes ago
        old_time = datetime.utcnow() - timedelta(minutes=31)
        self.hostbot.confessional_cooldowns[user.id] = [old_time, old_time, old_time]
        # New usage should be allowed (oldest drops off)
        result = self.hostbot._inc_cooldown(user)
        assert result is True
        assert len(self.hostbot.confessional_cooldowns[user.id]) == 3

    def test_partial_window_expiry(self) -> None:
        """Only oldest timestamp should be checked."""
        user = MagicMock(spec=discord.Member)
        user.id = 12345
        # First usage 31 min ago, others recent
        old_time = datetime.utcnow() - timedelta(minutes=31)
        recent_time = datetime.utcnow() - timedelta(minutes=5)
        self.hostbot.confessional_cooldowns[user.id] = [old_time, recent_time, recent_time]
        # Should be allowed since oldest is expired
        result = self.hostbot._inc_cooldown(user)
        assert result is True
