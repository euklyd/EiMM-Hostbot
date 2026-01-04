"""FastAPI dependencies for authentication and database access."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session

from .schemas import DiscordUser

logger = logging.getLogger(__name__)

# Simple in-memory cache for user guild memberships
# Key: user_id, Value: (guild_ids, timestamp)
_guild_cache: dict[int, tuple[list[int], float]] = {}
_GUILD_CACHE_TTL = 300  # 5 minutes

if TYPE_CHECKING:
    from discord.ext.commands import Bot


# =============================================================================
# Database Session
# =============================================================================


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session."""
    async with get_session() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]


# =============================================================================
# Authentication
# =============================================================================


async def get_user_with_guilds(user_data: dict, access_token: str | None) -> DiscordUser:
    """Build a DiscordUser with guild memberships from cache or Discord API.

    Args:
        user_data: User data dict (id, username, discriminator, avatar).
        access_token: Discord OAuth access token for fetching guilds.

    Returns:
        DiscordUser with guild_ids populated.
    """
    import time

    user_id: int | None = user_data.get("id")
    guild_ids: list[int] = []

    # Check cache first
    now = time.time()
    if user_id is not None and user_id in _guild_cache:
        cached_guilds, cached_time = _guild_cache[user_id]
        if now - cached_time < _GUILD_CACHE_TTL:
            guild_ids = cached_guilds
            logger.debug(f"get_user_with_guilds: using cached guilds for {user_data.get('username')}")

    # Fetch from Discord if not cached
    if not guild_ids and access_token:
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://discord.com/api/v10/users/@me/guilds",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if response.status_code == 200:
                    guilds = response.json()
                    guild_ids = [int(g["id"]) for g in guilds]
                    if user_id is not None:
                        _guild_cache[user_id] = (guild_ids, now)
                    logger.debug(f"get_user_with_guilds: fetched {len(guild_ids)} guilds for {user_data.get('username')}")
                else:
                    logger.warning(f"Failed to fetch guilds: {response.status_code}")
        except Exception as e:
            logger.warning(f"Error fetching guilds: {e}")

    # Build user with guild_ids
    user_data_with_guilds = {**user_data, "guild_ids": guild_ids, "guilds": []}
    return DiscordUser.model_validate(user_data_with_guilds)


async def get_current_user(request: Request) -> DiscordUser | None:
    """Get the current user from session, or None if not authenticated.

    Fetches guild memberships on demand using the stored access token.
    Results are cached for 5 minutes to avoid hitting Discord rate limits.
    """
    user_data = request.session.get("user")
    if user_data is None:
        return None

    access_token = request.session.get("access_token")
    return await get_user_with_guilds(user_data, access_token)


async def require_user(request: Request) -> DiscordUser:
    """Require authentication. Raises 401 if not authenticated."""
    user = await get_current_user(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user


CurrentUser = Annotated[DiscordUser, Depends(require_user)]
OptionalUser = Annotated[DiscordUser | None, Depends(get_current_user)]


# =============================================================================
# Bot Access
# =============================================================================


def get_bot(request: Request) -> Bot:
    """Get the Discord bot instance from app state."""
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Discord bot not available",
        )
    return bot


BotInstance = Annotated["Bot", Depends(get_bot)]


# =============================================================================
# Permission Checks
# =============================================================================


async def require_member_of(
    server_id: int,
    user: CurrentUser,
) -> DiscordUser:
    """Require user to be a member of the specified server."""
    if not user.is_member_of(server_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this server",
        )
    return user


async def check_manager_role(
    server_id: int,
    user: DiscordUser,
    bot: Bot,
    db: AsyncSession,
) -> bool:
    """Check if user has manager role for a server.

    Returns True if user is a manager, False otherwise.
    Does not raise - caller decides what to do.
    """
    from cogs.interview import service

    server = await service.get_server(db, server_id)
    if server is None:
        return False

    # If no manager role configured, check for admin permission
    if server.manager_role_id is None:
        guild_info = user.get_guild(server_id)
        return guild_info is not None and guild_info.is_admin()

    # Check if user has the manager role via bot
    guild = bot.get_guild(server_id)
    if guild is None:
        return False

    member = guild.get_member(user.id)
    if member is None:
        # User might be in guild but not cached - fall back to OAuth admin check
        guild_info = user.get_guild(server_id)
        return guild_info is not None and guild_info.is_admin()

    return any(role.id == server.manager_role_id for role in member.roles)


async def require_manager(
    server_id: int,
    user: CurrentUser,
    bot: BotInstance,
    db: DbSession,
) -> DiscordUser:
    """Require user to be a manager for the specified server."""
    # First check membership
    if not user.is_member_of(server_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this server",
        )

    is_manager = await check_manager_role(server_id, user, bot, db)
    if not is_manager:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager role required",
        )
    return user
