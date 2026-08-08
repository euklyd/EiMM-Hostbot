"""Tests for web API schemas."""

from web.schemas import DiscordGuild, DiscordUser


class TestDiscordGuild:
    """Tests for DiscordGuild schema."""

    def test_id_coerced_from_string(self):
        """ID should be coerced from string to int internally."""
        guild = DiscordGuild(id="123456789012345678", name="Test Guild")
        assert guild.id == 123456789012345678
        assert isinstance(guild.id, int)

    def test_id_accepts_int(self):
        """ID should accept int directly."""
        guild = DiscordGuild(id=123456789012345678, name="Test Guild")
        assert guild.id == 123456789012345678

    def test_id_serializes_as_string(self):
        """ID should serialize to string in JSON for JS safety."""
        guild = DiscordGuild(id=123456789012345678, name="Test Guild")
        data = guild.model_dump(mode="json")
        assert data["id"] == "123456789012345678"
        assert isinstance(data["id"], str)

    def test_permissions_int_property(self):
        """permissions_int should convert permissions string to int."""
        guild = DiscordGuild(id=1, name="Test", permissions="8")
        assert guild.permissions_int == 8

    def test_is_admin_with_admin_permission(self):
        """is_admin should return True when admin bit is set."""
        guild = DiscordGuild(id=1, name="Test", permissions="8")  # 0x8 = admin
        assert guild.is_admin() is True

    def test_is_admin_without_admin_permission(self):
        """is_admin should return False when admin bit is not set."""
        guild = DiscordGuild(id=1, name="Test", permissions="0")
        assert guild.is_admin() is False

    def test_is_admin_with_other_permissions(self):
        """is_admin should return True even with other permissions set."""
        guild = DiscordGuild(id=1, name="Test", permissions="2147483656")  # admin + others
        assert guild.is_admin() is True


class TestDiscordUser:
    """Tests for DiscordUser schema."""

    def test_id_coerced_from_string(self):
        """ID should be coerced from string to int internally."""
        user = DiscordUser(id="123456789012345678", username="testuser")
        assert user.id == 123456789012345678
        assert isinstance(user.id, int)

    def test_id_accepts_int(self):
        """ID should accept int directly."""
        user = DiscordUser(id=123456789012345678, username="testuser")
        assert user.id == 123456789012345678

    def test_id_serializes_as_string(self):
        """ID should serialize to string in JSON for JS safety."""
        user = DiscordUser(id=123456789012345678, username="testuser")
        data = user.model_dump(mode="json")
        assert data["id"] == "123456789012345678"
        assert isinstance(data["id"], str)

    def test_guild_ids_coerced_from_strings(self):
        """guild_ids should be coerced from strings to ints internally."""
        user = DiscordUser(
            id=1,
            username="testuser",
            guild_ids=["111111111111111111", "222222222222222222"],
        )
        assert user.guild_ids == [111111111111111111, 222222222222222222]
        assert all(isinstance(gid, int) for gid in user.guild_ids)

    def test_guild_ids_accepts_ints(self):
        """guild_ids should accept ints directly."""
        user = DiscordUser(
            id=1,
            username="testuser",
            guild_ids=[111111111111111111, 222222222222222222],
        )
        assert user.guild_ids == [111111111111111111, 222222222222222222]

    def test_guild_ids_serialize_as_strings(self):
        """guild_ids should serialize to strings in JSON for JS safety."""
        user = DiscordUser(
            id=1,
            username="testuser",
            guild_ids=[111111111111111111, 222222222222222222],
        )
        data = user.model_dump(mode="json")
        assert data["guild_ids"] == ["111111111111111111", "222222222222222222"]
        assert all(isinstance(gid, str) for gid in data["guild_ids"])

    def test_guild_ids_defaults_to_empty_list(self):
        """guild_ids should default to empty list."""
        user = DiscordUser(id=1, username="testuser")
        assert user.guild_ids == []

    def test_guild_ids_none_becomes_empty_list(self):
        """guild_ids=None should become empty list."""
        user = DiscordUser(id=1, username="testuser", guild_ids=None)
        assert user.guild_ids == []


class TestDiscordUserIsMemberOf:
    """Tests for DiscordUser.is_member_of() method."""

    def test_is_member_of_with_guild_ids(self):
        """is_member_of should check guild_ids list."""
        user = DiscordUser(
            id=1,
            username="testuser",
            guild_ids=[111111111111111111, 222222222222222222],
        )
        assert user.is_member_of(111111111111111111) is True
        assert user.is_member_of(222222222222222222) is True
        assert user.is_member_of(333333333333333333) is False

    def test_is_member_of_falls_back_to_guilds(self):
        """is_member_of should fall back to guilds list when guild_ids is empty."""
        user = DiscordUser(
            id=1,
            username="testuser",
            guilds=[
                DiscordGuild(id=111111111111111111, name="Guild 1"),
                DiscordGuild(id=222222222222222222, name="Guild 2"),
            ],
        )
        assert user.is_member_of(111111111111111111) is True
        assert user.is_member_of(333333333333333333) is False

    def test_is_member_of_prefers_guild_ids(self):
        """is_member_of should prefer guild_ids over guilds list."""
        user = DiscordUser(
            id=1,
            username="testuser",
            guild_ids=[111111111111111111],
            guilds=[
                DiscordGuild(id=222222222222222222, name="Guild 2"),
            ],
        )
        # Should find in guild_ids
        assert user.is_member_of(111111111111111111) is True
        # Should NOT find 222 because guild_ids takes precedence
        assert user.is_member_of(222222222222222222) is False

    def test_is_member_of_empty_user(self):
        """is_member_of should return False for user with no guilds."""
        user = DiscordUser(id=1, username="testuser")
        assert user.is_member_of(111111111111111111) is False


class TestDiscordUserGetGuild:
    """Tests for DiscordUser.get_guild() method."""

    def test_get_guild_found(self):
        """get_guild should return guild when found."""
        guild = DiscordGuild(id=111111111111111111, name="Test Guild")
        user = DiscordUser(id=1, username="testuser", guilds=[guild])

        result = user.get_guild(111111111111111111)
        assert result is not None
        assert result.id == 111111111111111111
        assert result.name == "Test Guild"

    def test_get_guild_not_found(self):
        """get_guild should return None when guild not found."""
        user = DiscordUser(
            id=1,
            username="testuser",
            guilds=[DiscordGuild(id=111111111111111111, name="Other Guild")],
        )
        assert user.get_guild(999999999999999999) is None

    def test_get_guild_empty_guilds(self):
        """get_guild should return None when guilds list is empty."""
        user = DiscordUser(id=1, username="testuser")
        assert user.get_guild(111111111111111111) is None

    def test_get_guild_only_guild_ids(self):
        """get_guild should return None when only guild_ids are stored."""
        user = DiscordUser(
            id=1,
            username="testuser",
            guild_ids=[111111111111111111],  # Has ID but no full guild info
        )
        # Cannot get guild info when only IDs are stored
        assert user.get_guild(111111111111111111) is None


class TestDiscordUserSerialization:
    """Tests for full DiscordUser serialization."""

    def test_full_serialization(self):
        """Full user should serialize correctly."""
        user = DiscordUser(
            id=123456789012345678,
            username="testuser",
            discriminator="1234",
            avatar="abc123",
            guild_ids=[111111111111111111, 222222222222222222],
            guilds=[
                DiscordGuild(id=111111111111111111, name="Guild 1", owner=True),
            ],
        )
        data = user.model_dump(mode="json")

        assert data["id"] == "123456789012345678"
        assert data["username"] == "testuser"
        assert data["discriminator"] == "1234"
        assert data["avatar"] == "abc123"
        assert data["guild_ids"] == ["111111111111111111", "222222222222222222"]
        assert len(data["guilds"]) == 1
        assert data["guilds"][0]["id"] == "111111111111111111"
        assert data["guilds"][0]["name"] == "Guild 1"
        assert data["guilds"][0]["owner"] is True

    def test_snowflake_precision_preserved(self):
        """Large Discord snowflake IDs should preserve precision."""
        # This is a realistic Discord snowflake that exceeds JS safe integer
        snowflake = 1234567890123456789  # 19 digits, > 2^53-1

        user = DiscordUser(id=snowflake, username="testuser")

        # Internal representation should be exact
        assert user.id == snowflake

        # Serialized string should preserve all digits
        data = user.model_dump(mode="json")
        assert data["id"] == "1234567890123456789"

        # Verify we can round-trip
        user2 = DiscordUser.model_validate(data)
        assert user2.id == snowflake
