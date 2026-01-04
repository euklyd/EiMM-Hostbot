"""Async database session factory.

Supports both PostgreSQL (production) and SQLite (testing).
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

# Global engine and session factory - initialized by init_db()
_engine = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_db(database_url: str, echo: bool = False) -> None:
    """Initialize the async database engine and session factory.

    Args:
        database_url: Database URL. Supports:
            - PostgreSQL: "postgresql+asyncpg://user:pass@host/db"
            - SQLite: "sqlite+aiosqlite:///path/to/db.sqlite"
        echo: If True, log all SQL statements.
    """
    global _engine, _async_session_factory

    _engine = create_async_engine(
        database_url,
        echo=echo,
        # PostgreSQL-specific: connection pool settings
        pool_pre_ping=True,  # Verify connections before use
    )

    _async_session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,  # Don't expire objects after commit (avoids lazy load issues)
    )


def get_engine() -> AsyncEngine:
    """Get the database engine, raising if not initialized."""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _engine


async def create_tables(base: type) -> None:
    """Create all tables for the given declarative base.

    Args:
        base: SQLAlchemy declarative base (e.g., Base from a schema module)
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(base.metadata.create_all)


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get the session factory, raising if not initialized."""
    if _async_session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _async_session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get an async database session.

    Usage:
        async with get_session() as session:
            result = await session.execute(select(User))
            ...
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Alias for dependency injection (FastAPI, etc.)
AsyncSessionLocal = get_session
