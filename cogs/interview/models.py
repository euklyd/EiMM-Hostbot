"""SQLAlchemy models for the interview cog.

These models replace:
- The old interview_schema.py SQLite models
- Google Sheets Q&A storage

All Discord IDs use BigInteger since they can exceed 32-bit int range.
All timestamps are timezone-aware UTC.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class InterviewServer(Base):
    """Server-level interview settings.

    One row per Discord guild that has interviews enabled.
    """

    __tablename__ = "interview_servers"

    # Discord guild ID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))

    # Channel configuration
    answer_channel_id: Mapped[int | None] = mapped_column(BigInteger)
    backstage_channel_id: Mapped[int | None] = mapped_column(BigInteger)
    voting_channel_id: Mapped[int | None] = mapped_column(BigInteger)  # Restrict voting to channel

    # Role configuration
    manager_role_id: Mapped[int | None] = mapped_column(BigInteger)
    audience_role_id: Mapped[int | None] = mapped_column(BigInteger)

    # Interview settings
    default_question: Mapped[str] = mapped_column(Text, default="What's your favorite card?")
    reinterview_days: Mapped[int] = mapped_column(default=0)  # 0 = no limit
    reinterviews_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships (no ORM cascade - we don't delete servers)
    # DB-level CASCADE on FKs handles integrity if rows are deleted directly
    interviews: Mapped[list["Interview"]] = relationship(back_populates="server")
    opt_outs: Mapped[list["OptOut"]] = relationship(back_populates="server")

    def __repr__(self) -> str:
        return f"<InterviewServer id={self.id} name={self.name!r} active={self.active}>"


class Interview(Base):
    """A single interview session (typically one week).

    Tracks metadata about an interview. Questions are stored separately.
    """

    __tablename__ = "interviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    server_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("interview_servers.id", ondelete="CASCADE"))

    # Interview number within this server (1, 2, 3, ...)
    interview_number: Mapped[int]

    # Interviewee info (cached for display even if user leaves)
    interviewee_id: Mapped[int] = mapped_column(BigInteger)
    interviewee_name: Mapped[str] = mapped_column(String(100))

    # Timing
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # OP message for votals display
    op_channel_id: Mapped[int | None] = mapped_column(BigInteger)
    op_message_id: Mapped[int | None] = mapped_column(BigInteger)

    # Relationships (no ORM cascade - we don't delete interviews)
    server: Mapped["InterviewServer"] = relationship(back_populates="interviews")
    questions: Mapped[list["Question"]] = relationship(back_populates="interview")
    votes: Mapped[list["Vote"]] = relationship(back_populates="interview")

    def __repr__(self) -> str:
        return f"<Interview id={self.id} interviewee={self.interviewee_name!r} is_current={self.is_current}>"

    @property
    def is_current(self) -> bool:
        """Interview is current if it hasn't ended."""
        return self.ended_at is None

    @property
    def questions_asked(self) -> int:
        """Count of non-deleted questions asked."""
        return sum(1 for q in self.questions if not q.is_deleted)

    @property
    def questions_answered(self) -> int:
        """Count of questions that have been answered and posted (excludes deleted)."""
        return sum(1 for q in self.questions if q.is_posted and not q.is_deleted)


class Question(Base):
    """A question asked during an interview.

    This replaces the Google Sheets storage. Each row is one question.
    """

    __tablename__ = "interview_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    interview_id: Mapped[int] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"))

    # Question ordering
    question_number: Mapped[int]

    # Asker info (cached for display even if user leaves)
    asker_id: Mapped[int] = mapped_column(BigInteger)
    asker_name: Mapped[str] = mapped_column(String(100))

    # Content
    question_text: Mapped[str] = mapped_column(Text)
    answer_text: Mapped[str | None] = mapped_column(Text)

    # Status
    is_posted: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Source message (for jump_url reconstruction)
    source_guild_id: Mapped[int] = mapped_column(BigInteger)
    source_channel_id: Mapped[int] = mapped_column(BigInteger)
    source_message_id: Mapped[int] = mapped_column(BigInteger)

    # Posted message reference (if posted)
    posted_message_id: Mapped[int | None] = mapped_column(BigInteger)

    # Soft delete for moderation
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by_id: Mapped[int | None] = mapped_column(BigInteger)

    # Relationship
    interview: Mapped["Interview"] = relationship(back_populates="questions")

    def __repr__(self) -> str:
        return f"<Question id={self.id} #{self.question_number} from={self.asker_name!r} posted={self.is_posted}>"

    @property
    def is_deleted(self) -> bool:
        """Question has been soft-deleted by a moderator."""
        return self.deleted_at is not None

    @property
    def jump_url(self) -> str:
        """Discord jump URL to the original question message."""
        return f"https://discord.com/channels/{self.source_guild_id}/{self.source_channel_id}/{self.source_message_id}"


class Vote(Base):
    """A vote for the next interviewee.

    Votes are per-server. The interview_id is optional and used for historical
    tracking (which interview was active when the vote was cast).
    Unique constraint prevents voting for the same candidate twice per server.
    """

    __tablename__ = "interview_votes"
    __table_args__ = (
        # Can't vote for the same person twice in the same server
        UniqueConstraint("server_id", "voter_id", "candidate_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # Server this vote belongs to (required)
    server_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("interview_servers.id", ondelete="CASCADE"))

    # Interview active when vote was cast (optional, for history)
    interview_id: Mapped[int | None] = mapped_column(ForeignKey("interviews.id", ondelete="SET NULL"))

    # Voter and candidate
    voter_id: Mapped[int] = mapped_column(BigInteger)
    candidate_id: Mapped[int] = mapped_column(BigInteger)

    # When they voted
    voted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    server: Mapped["InterviewServer"] = relationship()
    interview: Mapped["Interview | None"] = relationship(back_populates="votes")

    def __repr__(self) -> str:
        return f"<Vote server={self.server_id} voter={self.voter_id} candidate={self.candidate_id}>"


class OptOut(Base):
    """Users who have opted out of being interviewed.

    Composite primary key: (server_id, user_id).
    """

    __tablename__ = "interview_opt_outs"

    server_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("interview_servers.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # Relationship
    server: Mapped["InterviewServer"] = relationship(back_populates="opt_outs")

    def __repr__(self) -> str:
        return f"<OptOut server={self.server_id} user={self.user_id}>"
