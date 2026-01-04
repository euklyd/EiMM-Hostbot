"""Discord OAuth2 authentication helpers."""

from __future__ import annotations

import os
from urllib.parse import urlencode

import httpx

DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_OAUTH_AUTHORIZE = "https://discord.com/oauth2/authorize"
DISCORD_OAUTH_TOKEN = "https://discord.com/api/oauth2/token"


def get_oauth_config() -> dict[str, str]:
    """Get OAuth2 configuration from environment variables.

    Required environment variables:
    - DISCORD_CLIENT_ID
    - DISCORD_CLIENT_SECRET
    - DISCORD_REDIRECT_URI

    Returns:
        Dict with client_id, client_secret, redirect_uri keys.

    Raises:
        ValueError: If required environment variables are missing.
    """
    client_id = os.environ.get("DISCORD_CLIENT_ID")
    client_secret = os.environ.get("DISCORD_CLIENT_SECRET")
    redirect_uri = os.environ.get("DISCORD_REDIRECT_URI")

    missing = []
    if not client_id:
        missing.append("DISCORD_CLIENT_ID")
    if not client_secret:
        missing.append("DISCORD_CLIENT_SECRET")
    if not redirect_uri:
        missing.append("DISCORD_REDIRECT_URI")

    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    # After validation, we know these are not None
    assert client_id is not None
    assert client_secret is not None
    assert redirect_uri is not None

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }


def build_oauth_url(state: str | None = None) -> str:
    """Build the Discord OAuth2 authorization URL.

    Args:
        state: Optional state parameter for CSRF protection.

    Returns:
        Full authorization URL to redirect the user to.
    """
    config = get_oauth_config()

    params = {
        "client_id": config["client_id"],
        "redirect_uri": config["redirect_uri"],
        "response_type": "code",
        "scope": "identify guilds",
    }
    if state:
        params["state"] = state

    return f"{DISCORD_OAUTH_AUTHORIZE}?{urlencode(params)}"


async def exchange_code(code: str) -> dict:
    """Exchange an authorization code for an access token.

    Args:
        code: The authorization code from the callback.

    Returns:
        Token response dict with access_token, token_type, expires_in, etc.

    Raises:
        httpx.HTTPStatusError: If the token exchange fails.
    """
    config = get_oauth_config()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            DISCORD_OAUTH_TOKEN,
            data={
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": config["redirect_uri"],
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        return response.json()


async def fetch_user_info(access_token: str) -> dict:
    """Fetch user information from Discord API.

    Args:
        access_token: OAuth2 access token.

    Returns:
        Dict with user info including id, username, discriminator, avatar.

    Raises:
        httpx.HTTPStatusError: If the API request fails.
    """
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {access_token}"}

        # Fetch user info
        user_response = await client.get(f"{DISCORD_API_BASE}/users/@me", headers=headers)
        user_response.raise_for_status()
        user_data = user_response.json()

        # Fetch guilds
        guilds_response = await client.get(f"{DISCORD_API_BASE}/users/@me/guilds", headers=headers)
        guilds_response.raise_for_status()
        guilds_data = guilds_response.json()

        # Combine into single response
        user_data["guilds"] = guilds_data
        return user_data


async def refresh_token(refresh_token: str) -> dict:
    """Refresh an access token using a refresh token.

    Args:
        refresh_token: The refresh token from a previous token response.

    Returns:
        New token response dict.

    Raises:
        httpx.HTTPStatusError: If the refresh fails.
    """
    config = get_oauth_config()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            DISCORD_OAUTH_TOKEN,
            data={
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        return response.json()
