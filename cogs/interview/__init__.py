"""Interview cog package.

This is a complete rewrite of the interview system using:
- PostgreSQL instead of SQLite + Google Sheets
- Async database operations
- Hybrid commands (prefix + slash)
- Web admin interface
"""

from cogs.interview.embeds import (
    AddQuestionResult,
    EmbedGenerationResult,
    IntervieweeData,
    QuestionData,
    generate_answer_embeds,
)
from cogs.interview.models import Interview, InterviewServer, OptOut, Question, Vote

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
]
