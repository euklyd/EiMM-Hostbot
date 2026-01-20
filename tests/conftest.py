"""Shared pytest fixtures for EiMM-Hostbot tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from cogs.emoji_schema import Base as EmojiBase
from cogs.hostbot_schema import Base as HostbotBase
from db.base import Base as InterviewBase
from schemas.scryfall_schema import Base as ScryfallBase


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
    ctx.channel.permissions_for = MagicMock(return_value=MagicMock(manage_messages=True))
    return ctx


# =============================================================================
# Database fixtures (in-memory SQLite, works identically with PostgreSQL)
# =============================================================================


@pytest.fixture
def hostbot_engine() -> Generator[Engine, None, None]:
    """Create an in-memory SQLite engine for hostbot schema."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    HostbotBase.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def hostbot_session(hostbot_engine: Engine) -> Generator[Session, None, None]:
    """Create a session for hostbot schema tests."""
    session_factory = sessionmaker(bind=hostbot_engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def emoji_engine() -> Generator[Engine, None, None]:
    """Create an in-memory SQLite engine for emoji schema."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    EmojiBase.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def emoji_session(emoji_engine: Engine) -> Generator[Session, None, None]:
    """Create a session for emoji schema tests."""
    session_factory = sessionmaker(bind=emoji_engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def scryfall_engine() -> Generator[Engine, None, None]:
    """Create an in-memory SQLite engine for scryfall schema."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    ScryfallBase.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def scryfall_session(scryfall_engine: Engine) -> Generator[Session, None, None]:
    """Create a session for scryfall schema tests."""
    session_factory = sessionmaker(bind=scryfall_engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def interview_engine() -> Generator[Engine, None, None]:
    """Create an in-memory SQLite engine for interview schema."""
    # Import models to register them with the Base
    from cogs.interview.models import (  # noqa: F401
        Interview,
        InterviewServer,
        OptOut,
        Question,
        Vote,
    )

    engine = create_engine("sqlite:///:memory:", echo=False)
    InterviewBase.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def interview_session(interview_engine: Engine) -> Generator[Session, None, None]:
    """Create a session for interview schema tests."""
    session_factory = sessionmaker(bind=interview_engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
