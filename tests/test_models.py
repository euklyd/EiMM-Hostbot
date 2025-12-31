"""Tests for SQLAlchemy models.

These tests use in-memory SQLite but are written to work identically with PostgreSQL.
Key principles:
- Use ORM operations only (no raw SQL)
- Don't rely on SQLite-specific behavior
- Test relationships and constraints as they would work in production
"""

from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cogs.emoji_schema import EmojiCount, EventEmoji
from cogs.hostbot_schema import Channel, Role, Server
from schemas.scryfall_schema import ScryfallText

# =============================================================================
# Hostbot Schema Tests
# =============================================================================


class TestServerModel:
    """Tests for the Server model."""

    def test_create_server(self, hostbot_session: Session) -> None:
        """Basic server creation."""
        server = Server(
            id=123456789,
            name="Test Server",
            sheet="test-sheet",
            addspec_on=True,
            players_can_lock=False,
        )
        hostbot_session.add(server)
        hostbot_session.commit()

        retrieved = hostbot_session.get(Server, 123456789)
        assert retrieved is not None
        assert retrieved.name == "Test Server"
        assert retrieved.sheet == "test-sheet"
        assert retrieved.addspec_on is True
        assert retrieved.players_can_lock is False

    def test_server_repr(self, hostbot_session: Session) -> None:
        """Server __repr__ should be readable."""
        server = Server(id=1, name="Test", sheet="sheet")
        hostbot_session.add(server)
        hostbot_session.commit()

        repr_str = repr(server)
        assert "id=1" in repr_str
        assert "name=Test" in repr_str

    def test_server_with_roles_relationship(self, hostbot_session: Session) -> None:
        """Server should have roles relationship."""
        server = Server(id=1, name="Test", sheet="sheet")
        Role(id=100, type="player", server=server)
        Role(id=101, type="host", server=server)

        hostbot_session.add(server)
        hostbot_session.commit()

        retrieved = hostbot_session.get(Server, 1)
        assert retrieved is not None
        assert len(retrieved.roles) == 2
        role_types = {r.type for r in retrieved.roles}
        assert role_types == {"player", "host"}

    def test_server_with_channels_relationship(self, hostbot_session: Session) -> None:
        """Server should have channels relationship."""
        server = Server(id=1, name="Test", sheet="sheet")
        Channel(id=200, type="graveyard", server=server)
        Channel(id=201, type="rolepm", server=server)

        hostbot_session.add(server)
        hostbot_session.commit()

        retrieved = hostbot_session.get(Server, 1)
        assert retrieved is not None
        assert len(retrieved.channels) == 2


class TestRoleModel:
    """Tests for the Role model."""

    def test_create_role(self, hostbot_session: Session) -> None:
        """Basic role creation with server FK."""
        server = Server(id=1, name="Test", sheet="sheet")
        role = Role(id=100, type="player", server=server)

        hostbot_session.add(role)
        hostbot_session.commit()

        retrieved = hostbot_session.get(Role, 100)
        assert retrieved is not None
        assert retrieved.type == "player"
        assert retrieved.server_id == 1

    def test_role_back_populates_server(self, hostbot_session: Session) -> None:
        """Role.server should back-populate to Server.roles."""
        server = Server(id=1, name="Test", sheet="sheet")
        role = Role(id=100, type="spec", server=server)

        hostbot_session.add(role)
        hostbot_session.commit()

        # Access relationship from role side
        assert role.server.name == "Test"
        # Access relationship from server side
        assert role in server.roles

    def test_role_repr(self, hostbot_session: Session) -> None:
        """Role __repr__ should be readable."""
        server = Server(id=1, name="Test", sheet="sheet")
        role = Role(id=100, type="player", server=server)

        repr_str = repr(role)
        assert "id=100" in repr_str
        assert "type=player" in repr_str


class TestChannelModel:
    """Tests for the Channel model."""

    def test_create_channel(self, hostbot_session: Session) -> None:
        """Basic channel creation with server FK."""
        server = Server(id=1, name="Test", sheet="sheet")
        channel = Channel(id=200, type="graveyard", server=server)

        hostbot_session.add(channel)
        hostbot_session.commit()

        retrieved = hostbot_session.get(Channel, 200)
        assert retrieved is not None
        assert retrieved.type == "graveyard"
        assert retrieved.server_id == 1

    def test_channel_back_populates_server(self, hostbot_session: Session) -> None:
        """Channel.server should back-populate to Server.channels."""
        server = Server(id=1, name="Test", sheet="sheet")
        channel = Channel(id=200, type="rolepm", server=server)

        hostbot_session.add(channel)
        hostbot_session.commit()

        assert channel.server.name == "Test"
        assert channel in server.channels


class TestHostbotQueryPatterns:
    """Test common query patterns used in hostbot.py."""

    def test_filter_roles_by_type(self, hostbot_session: Session) -> None:
        """Query roles by type (common pattern in has_role)."""
        server = Server(id=1, name="Test", sheet="sheet")
        Role(id=100, type="player", server=server)
        Role(id=101, type="host", server=server)
        Role(id=102, type="player", server=server)

        hostbot_session.add(server)
        hostbot_session.commit()

        # Pattern from has_role()
        player_roles = hostbot_session.query(Role).filter(Role.server_id == 1, Role.type == "player").all()
        assert len(player_roles) == 2

    def test_filter_roles_by_multiple_types(self, hostbot_session: Session) -> None:
        """Query roles by multiple types using in_()."""
        server = Server(id=1, name="Test", sheet="sheet")
        Role(id=100, type="player", server=server)
        Role(id=101, type="host", server=server)
        Role(id=102, type="spec", server=server)

        hostbot_session.add(server)
        hostbot_session.commit()

        # Pattern: get player OR host roles
        allowed = hostbot_session.query(Role).filter(Role.server_id == 1, Role.type.in_(["player", "host"])).all()
        assert len(allowed) == 2


# =============================================================================
# Emoji Schema Tests
# =============================================================================


class TestEmojiCountModel:
    """Tests for the EmojiCount model (composite primary key)."""

    def test_create_emoji_count(self, emoji_session: Session) -> None:
        """Basic emoji count creation."""
        count = EmojiCount(
            emoji_id=123,
            server_id=456,
            date=date(2024, 1, 15),
            user_id=789,
            count=5,
        )
        emoji_session.add(count)
        emoji_session.commit()

        # Query by composite key
        retrieved = (
            emoji_session.query(EmojiCount)
            .filter_by(emoji_id=123, server_id=456, date=date(2024, 1, 15), user_id=789)
            .one()
        )
        assert retrieved.count == 5

    def test_composite_primary_key_uniqueness(self, emoji_session: Session) -> None:
        """Composite PK should enforce uniqueness."""
        count1 = EmojiCount(
            emoji_id=123,
            server_id=456,
            date=date(2024, 1, 15),
            user_id=789,
            count=5,
        )
        emoji_session.add(count1)
        emoji_session.commit()

        # Same composite key should fail
        count2 = EmojiCount(
            emoji_id=123,
            server_id=456,
            date=date(2024, 1, 15),
            user_id=789,
            count=10,
        )
        emoji_session.add(count2)
        try:
            emoji_session.commit()
            raise AssertionError("Should have raised IntegrityError")
        except IntegrityError:
            emoji_session.rollback()

    def test_different_dates_allowed(self, emoji_session: Session) -> None:
        """Same emoji/server/user on different dates should be allowed."""
        count1 = EmojiCount(emoji_id=123, server_id=456, date=date(2024, 1, 15), user_id=789, count=5)
        count2 = EmojiCount(emoji_id=123, server_id=456, date=date(2024, 1, 16), user_id=789, count=3)
        emoji_session.add_all([count1, count2])
        emoji_session.commit()

        all_counts = emoji_session.query(EmojiCount).all()
        assert len(all_counts) == 2

    def test_aggregate_by_user(self, emoji_session: Session) -> None:
        """Test summing counts for a user (common pattern)."""
        from sqlalchemy import func

        # Multiple days of emoji usage
        emoji_session.add_all(
            [
                EmojiCount(emoji_id=123, server_id=1, date=date(2024, 1, 1), user_id=100, count=5),
                EmojiCount(emoji_id=123, server_id=1, date=date(2024, 1, 2), user_id=100, count=3),
                EmojiCount(emoji_id=123, server_id=1, date=date(2024, 1, 3), user_id=100, count=7),
            ]
        )
        emoji_session.commit()

        total = emoji_session.query(func.sum(EmojiCount.count)).filter(EmojiCount.user_id == 100).scalar()
        assert total == 15


class TestEventEmojiModel:
    """Tests for the EventEmoji model."""

    def test_create_event_emoji(self, emoji_session: Session) -> None:
        """Basic event emoji creation."""
        event = EventEmoji(
            emoji_id=123,
            server_id=456,
            date=date(2024, 1, 15),
            owner_id=789,
            event="Birthday",
            active=True,
        )
        emoji_session.add(event)
        emoji_session.commit()

        retrieved = emoji_session.query(EventEmoji).filter_by(emoji_id=123, server_id=456).one()
        assert retrieved.event == "Birthday"
        assert retrieved.active is True

    def test_filter_active_events(self, emoji_session: Session) -> None:
        """Filter for active events only."""
        emoji_session.add_all(
            [
                EventEmoji(emoji_id=1, server_id=1, owner_id=1, event="E1", active=True),
                EventEmoji(emoji_id=2, server_id=1, owner_id=1, event="E2", active=False),
                EventEmoji(emoji_id=3, server_id=1, owner_id=1, event="E3", active=True),
            ]
        )
        emoji_session.commit()

        active = (
            emoji_session.query(EventEmoji)
            .filter(
                EventEmoji.server_id == 1,
                EventEmoji.active == True,  # noqa: E712
            )
            .all()
        )
        assert len(active) == 2


# =============================================================================
# Scryfall Schema Tests
# =============================================================================


class TestScryfallTextModel:
    """Tests for the ScryfallText cache model."""

    def test_create_scryfall_text(self, scryfall_session: Session) -> None:
        """Basic cache entry creation."""
        entry = ScryfallText(
            scryfall_id="abc-123-def",
            cache_time=date(2024, 1, 15),
            text="Card rules text here",
        )
        scryfall_session.add(entry)
        scryfall_session.commit()

        retrieved = scryfall_session.get(ScryfallText, "abc-123-def")
        assert retrieved is not None
        assert retrieved.text == "Card rules text here"

    def test_update_cache(self, scryfall_session: Session) -> None:
        """Cache entries can be updated."""
        entry = ScryfallText(
            scryfall_id="abc-123",
            cache_time=date(2024, 1, 1),
            text="Old text",
        )
        scryfall_session.add(entry)
        scryfall_session.commit()

        # Update the cache
        entry.cache_time = date(2024, 1, 15)
        entry.text = "New text"
        scryfall_session.commit()

        retrieved = scryfall_session.get(ScryfallText, "abc-123")
        assert retrieved is not None
        assert retrieved.text == "New text"
        assert retrieved.cache_time == date(2024, 1, 15)
