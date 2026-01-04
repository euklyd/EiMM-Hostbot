"""Authentication routes for Discord OAuth2."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse

from ..auth import build_oauth_url, exchange_code, fetch_user_info
from ..dependencies import OptionalUser
from ..schemas import DiscordUser

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


@router.get("/login")
async def login(
    request: Request,
    redirect: str = Query(default="/", description="URL to redirect to after login"),
) -> RedirectResponse:
    """Redirect to Discord OAuth2 login.

    Query Parameters:
        redirect: URL to redirect to after successful login (default: /)
    """
    # Store redirect URL in session for after callback
    request.session["login_redirect"] = redirect

    try:
        oauth_url = build_oauth_url()
    except ValueError as e:
        logger.error(f"OAuth configuration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth not configured",
        ) from e

    return RedirectResponse(oauth_url, status_code=status.HTTP_302_FOUND)


@router.get("/callback")
async def callback(
    request: Request,
    code: str = Query(..., description="Authorization code from Discord"),
    error: str | None = Query(default=None, description="Error from Discord"),
    error_description: str | None = Query(default=None),
) -> RedirectResponse:
    """Handle OAuth2 callback from Discord.

    Exchanges the authorization code for an access token, fetches user info,
    and stores it in the session.
    """
    logger.debug(f"OAuth callback received, code length: {len(code)}")
    logger.debug(f"Session contents: {dict(request.session)}")

    # Handle OAuth errors
    if error:
        logger.warning(f"OAuth error: {error} - {error_description}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_description or error,
        )

    try:
        # Exchange code for token
        logger.debug("Exchanging authorization code for token...")
        token_data = await exchange_code(code)
        access_token = token_data["access_token"]
        logger.debug("Token exchange successful")

        # Fetch user info
        logger.debug("Fetching user info from Discord...")
        user_info = await fetch_user_info(access_token)
        logger.debug(f"Got user info for: {user_info.get('username')}")

        # Build user data for session - MINIMAL to avoid cookie overflow
        # Don't store guild IDs - we'll fetch them on demand using the access token
        user_data = {
            "id": int(user_info["id"]),
            "username": user_info["username"],
            "discriminator": user_info.get("discriminator", "0"),
            "avatar": user_info.get("avatar"),
        }

        guild_count = len(user_info.get("guilds", []))

        # Store in session - only essential user data + access token for guild fetches
        request.session["user"] = user_data
        request.session["access_token"] = access_token

        logger.info(f"User logged in: {user_data['username']} (ID: {user_data['id']}, {guild_count} guilds)")

    except httpx.HTTPStatusError as e:
        # Log the full response for debugging
        response_text = e.response.text if hasattr(e.response, "text") else "No response body"
        logger.error(f"Discord API error during login: {e}")
        logger.error(f"Response status: {e.response.status_code}")
        logger.error(f"Response body: {response_text}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to authenticate with Discord: {response_text}",
        ) from e
    except ValueError as e:
        logger.error(f"OAuth configuration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth not configured",
        ) from e
    except Exception as e:
        # Catch-all for unexpected errors
        logger.exception(f"Unexpected error during OAuth callback: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {type(e).__name__}: {e}",
        ) from e

    # Redirect to original destination or home
    redirect_url = request.session.pop("login_redirect", "/")
    return RedirectResponse(redirect_url, status_code=status.HTTP_302_FOUND)


@router.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    """Log out by clearing the session."""
    user = request.session.get("user")
    if user:
        logger.info(f"User logged out: {user.get('username')} (ID: {user.get('id')})")

    request.session.clear()
    return RedirectResponse("/", status_code=status.HTTP_302_FOUND)


@router.get("/me", response_model=DiscordUser | None)
async def get_current_user(user: OptionalUser) -> DiscordUser | None:
    """Get the current authenticated user.

    Returns null if not authenticated.
    """
    logger.info(f"/auth/me returning user: {user.username if user else None}")
    return user
