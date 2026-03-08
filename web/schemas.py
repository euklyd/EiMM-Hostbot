"""Pydantic schemas for web API request/response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator

# =============================================================================
# Discord OAuth2 User
# =============================================================================


class DiscordGuild(BaseModel):
    """Minimal guild info from Discord OAuth2.

    IDs are stored as int internally for type safety, serialized as strings for JS.
    """

    id: int  # Stored as int, serialized as string for JS safety
    name: str
    icon: str | None = None
    owner: bool = False
    permissions: str = "0"  # Permission bitfield as string

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id_to_int(cls, v: Any) -> int:
        """Coerce string ID from Discord API to int."""
        return int(v) if v is not None else 0

    @field_serializer("id")
    def serialize_id_as_str(self, v: int) -> str:
        """Serialize ID as string for JavaScript safety."""
        return str(v)

    @property
    def permissions_int(self) -> int:
        """Get permissions as integer for bitwise checks."""
        return int(self.permissions)

    def is_admin(self) -> bool:
        """Check if user has administrator permission in this guild."""
        return (self.permissions_int & 0x8) != 0


class DiscordUser(BaseModel):
    """User info from Discord OAuth2.

    IDs are stored as int internally for type safety, serialized as strings for JS.
    """

    id: int  # Stored as int, serialized as string for JS safety
    username: str
    discriminator: str = "0"
    avatar: str | None = None
    guilds: list[DiscordGuild] = []
    guild_ids: list[int] = []  # Compact storage for session (as ints internally)

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id_to_int(cls, v: Any) -> int:
        """Coerce string/int ID to int."""
        return int(v) if v is not None else 0

    @field_validator("guild_ids", mode="before")
    @classmethod
    def coerce_guild_ids_to_int(cls, v: Any) -> list[int]:
        """Coerce guild IDs to ints."""
        if v is None:
            return []
        return [int(gid) for gid in v]

    @field_serializer("id")
    def serialize_id_as_str(self, v: int) -> str:
        """Serialize ID as string for JavaScript safety."""
        return str(v)

    @field_serializer("guild_ids")
    def serialize_guild_ids_as_str(self, v: list[int]) -> list[str]:
        """Serialize guild IDs as strings for JavaScript safety."""
        return [str(gid) for gid in v]

    def is_member_of(self, guild_id: int) -> bool:
        """Check if user is a member of the given guild."""
        # Check guild_ids first (from session), then fall back to guilds
        if self.guild_ids:
            return guild_id in self.guild_ids
        return any(g.id == guild_id for g in self.guilds)

    def get_guild(self, guild_id: int) -> DiscordGuild | None:
        """Get guild info for a specific guild ID.

        Note: May return None if only guild_ids are stored (session mode).
        """
        for g in self.guilds:
            if g.id == guild_id:
                return g
        return None


# =============================================================================
# Interview Responses
# =============================================================================


class ServerResponse(BaseModel):
    """Server info for API responses.

    Discord IDs are serialized as strings to avoid JavaScript precision loss.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str  # Serialized as string for JS safety
    name: str
    active: bool
    answer_channel_id: str | None = None
    backstage_channel_id: str | None = None
    voting_channel_id: str | None = None
    manager_role_id: str | None = None
    default_question: str

    @field_validator(
        "id", "answer_channel_id", "backstage_channel_id", "voting_channel_id", "manager_role_id", mode="before"
    )
    @classmethod
    def convert_int_to_str(cls, v: Any) -> str | None:
        """Convert integer IDs to strings for JavaScript safety."""
        if v is None:
            return None
        return str(v)


class InterviewSummary(BaseModel):
    """Brief interview info for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: int  # Database ID, not Discord ID - safe as int
    interview_number: int
    interviewee_id: str  # Discord ID
    interviewee_name: str
    started_at: datetime
    ended_at: datetime | None = None
    is_current: bool

    @field_validator("interviewee_id", mode="before")
    @classmethod
    def convert_int_to_str(cls, v: Any) -> str | None:
        return str(v) if v is not None else None


class InterviewResponse(BaseModel):
    """Full interview info for detail views."""

    model_config = ConfigDict(from_attributes=True)

    id: int  # Database ID, not Discord ID - safe as int
    interview_number: int
    server_id: str  # Discord ID
    interviewee_id: str  # Discord ID
    interviewee_name: str
    started_at: datetime
    ended_at: datetime | None = None
    is_current: bool
    questions_asked: int = 0
    questions_answered: int = 0

    @field_validator("server_id", "interviewee_id", mode="before")
    @classmethod
    def convert_int_to_str(cls, v: Any) -> str | None:
        return str(v) if v is not None else None


class QuestionResponse(BaseModel):
    """Question info for API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int  # Database ID
    interview_id: int  # Database ID
    question_number: int
    asker_id: str  # Discord ID
    asker_name: str
    question_text: str
    answer_text: str | None = None
    is_posted: bool
    is_stashed: bool
    asked_at: datetime
    answered_at: datetime | None = None
    jump_url: str

    @field_validator("asker_id", mode="before")
    @classmethod
    def convert_int_to_str(cls, v: Any) -> str | None:
        return str(v) if v is not None else None


class ServerWithInterviewResponse(BaseModel):
    """Server with current interview info."""

    server: ServerResponse
    current_interview: InterviewSummary | None = None
    is_manager: bool = False


# =============================================================================
# Request Bodies
# =============================================================================


class AnswerRequest(BaseModel):
    """Request body for answering a question."""

    answer_text: str

    @field_validator("answer_text")
    @classmethod
    def validate_answer_length(cls, v: str) -> str:
        max_length = 10000  # ~11 embed fields worth of text
        if len(v) > max_length:
            raise ValueError(f"Answer too long ({len(v)}/{max_length} chars)")
        return v


class PostAnswersResponse(BaseModel):
    """Response for posting answers to Discord."""

    success: bool
    posted_count: int
    message: str | None = None


# =============================================================================
# Stats Responses
# =============================================================================


class ServerStatsResponse(BaseModel):
    """Server statistics for dashboard."""

    total_interviews: int
    total_questions: int
    total_answered: int
    avg_questions_per_interview: float
    avg_answer_time_seconds: float | None = None


class TopAskerResponse(BaseModel):
    """Top asker entry."""

    user_id: str  # Discord ID
    user_name: str
    question_count: int

    @field_validator("user_id", mode="before")
    @classmethod
    def convert_int_to_str(cls, v: Any) -> str | None:
        return str(v) if v is not None else None


# =============================================================================
# Search
# =============================================================================


class SearchRequest(BaseModel):
    """Request body for search queries."""

    query: str
    limit: int = 50
    offset: int = 0

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Query cannot be empty")
        if len(v) > 1000:
            raise ValueError("Query too long (max 1000 chars)")
        return v

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, v: int) -> int:
        if v < 1 or v > 100:
            raise ValueError("Limit must be between 1 and 100")
        return v

    @field_validator("offset")
    @classmethod
    def validate_offset(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Offset cannot be negative")
        return v


class SearchResultQuestion(BaseModel):
    """Question info for search results."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    question_number: int
    asker_id: str
    asker_name: str
    question_text: str
    answer_text: str | None = None
    asked_at: datetime

    @field_validator("asker_id", mode="before")
    @classmethod
    def convert_int_to_str(cls, v: Any) -> str | None:
        return str(v) if v is not None else None


class SearchResultInterview(BaseModel):
    """Interview context for search results."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    interview_number: int
    server_id: str
    server_name: str
    interviewee_id: str
    interviewee_name: str

    @field_validator("server_id", "interviewee_id", mode="before")
    @classmethod
    def convert_int_to_str(cls, v: Any) -> str | None:
        return str(v) if v is not None else None


class SearchResultEntry(BaseModel):
    """A single search result entry."""

    question: SearchResultQuestion
    interview: SearchResultInterview


class SearchResponse(BaseModel):
    """Response for search queries."""

    results: list[SearchResultEntry]
    total_count: int
    query: str  # Echo back the query for display
