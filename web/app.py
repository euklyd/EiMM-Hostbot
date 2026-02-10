"""FastAPI application factory."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

if TYPE_CHECKING:
    from discord.ext.commands import Bot


def create_app(bot: Bot | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        bot: Discord bot instance for API calls. Can be None for testing.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(
        title="EiMM Interview Admin",
        description="Web interface for managing Discord interview sessions",
        version="1.0.0",
    )

    # Store bot reference for routes
    app.state.bot = bot

    # Session middleware for OAuth2 (must be added before routes)
    session_secret = os.environ.get("SESSION_SECRET", "change-me-in-production")
    app.add_middleware(
        SessionMiddleware,
        secret_key=session_secret,
        session_cookie="session",
        max_age=60 * 60 * 24 * 7,  # 1 week
        same_site="lax",
        https_only=os.environ.get("HTTPS_ONLY", "false").lower() == "true",
    )

    # CORS middleware
    allowed_origins = os.environ.get("CORS_ORIGINS", "").split(",")
    allowed_origins = [o.strip() for o in allowed_origins if o.strip()]
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Include API routers
    from .routes import auth, interviews, search

    app.include_router(auth.router)
    app.include_router(interviews.router)
    app.include_router(search.router)

    # Mount static files for Vue frontend (if built)
    static_dir = Path(__file__).parent / "static"
    assets_dir = static_dir / "assets"
    index_path = static_dir / "index.html"

    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    # SPA fallback - serve index.html for frontend routes (only if built)
    if index_path.exists():

        @app.get("/{full_path:path}", response_model=None)
        async def serve_spa(request: Request, full_path: str) -> FileResponse | JSONResponse:
            """Serve Vue SPA for non-API routes."""
            # Don't serve SPA for API routes
            if full_path.startswith("api/") or full_path.startswith("auth/"):
                return JSONResponse({"detail": "Not found"}, status_code=404)
            return FileResponse(index_path)

    # Health check endpoint
    @app.get("/api/health")
    async def health_check() -> dict:
        """Health check endpoint."""
        return {
            "status": "ok",
            "bot_connected": bot is not None and bot.is_ready() if bot else False,
        }

    return app
