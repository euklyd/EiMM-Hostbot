"""Interview cog package.

This is a complete rewrite of the interview system using:
- PostgreSQL instead of SQLite + Google Sheets
- Async database operations
- Hybrid commands (prefix + slash)
- Web admin interface
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogs.interview.embeds import (
    AddQuestionResult,
    EmbedGenerationResult,
    IntervieweeData,
    QuestionData,
    generate_answer_embeds,
)
from cogs.interview.models import Interview, InterviewServer, OptOut, Question, Vote

if TYPE_CHECKING:
    from core.bot import Bot

__all__ = [
    # Models
    "Interview",
    "InterviewServer",
    "OptOut",
    "Question",
    "Vote",
    # Embed generation
    "AddQuestionResult",
    "EmbedGenerationResult",
    "IntervieweeData",
    "QuestionData",
    "generate_answer_embeds",
    # Setup function
    "setup",
]


async def setup(bot: Bot) -> None:
    """Load the Interview cog."""
    from cogs.interview.commands import Interview as InterviewCog

    await bot.add_cog(InterviewCog(bot))
