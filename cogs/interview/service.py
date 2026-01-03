"""Interview service layer.

Business logic shared between Discord commands and web routes.
All methods are async and accept an AsyncSession from the caller.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum, auto

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Interview, InterviewServer, OptOut, Question, Vote


class QuestionFilter(Enum):
    """Filter options for get_questions."""

    ALL = auto()
    UNANSWERED = auto()
    ANSWERED_UNPOSTED = auto()
    POSTED = auto()


# =============================================================================
# Interview Lifecycle
# =============================================================================


async def start_interview(
    session: AsyncSession,
    server_id: int,
    interviewee_id: int,
    interviewee_name: str,
    op_channel_id: int | None = None,
    op_message_id: int | None = None,
) -> Interview:
    """Start a new interview.

    Ends any existing current interview for the server first.
    """
    # End current interview if exists
    current = await get_current_interview(session, server_id)
    if current is not None:
        await end_interview(session, current.id)

    # Get next interview number for this server
    result = await session.execute(
        select(func.coalesce(func.max(Interview.interview_number), 0)).where(
            Interview.server_id == server_id
        )
    )
    max_num = result.scalar() or 0
    next_num = max_num + 1

    interview = Interview(
        server_id=server_id,
        interview_number=next_num,
        interviewee_id=interviewee_id,
        interviewee_name=interviewee_name,
        op_channel_id=op_channel_id,
        op_message_id=op_message_id,
    )
    session.add(interview)
    await session.flush()  # Populate interview.id
    return interview


async def end_interview(session: AsyncSession, interview_id: int) -> Interview | None:
    """End an interview by setting ended_at.

    Returns the interview if found, None otherwise.
    """
    result = await session.execute(
        select(Interview).where(Interview.id == interview_id)
    )
    interview = result.scalar_one_or_none()
    if interview is None:
        return None

    interview.ended_at = datetime.now(UTC)
    return interview


async def get_current_interview(
    session: AsyncSession, server_id: int
) -> Interview | None:
    """Get the current (non-ended) interview for a server."""
    result = await session.execute(
        select(Interview).where(
            Interview.server_id == server_id,
            Interview.ended_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def get_interview(session: AsyncSession, interview_id: int) -> Interview | None:
    """Get an interview by ID."""
    result = await session.execute(
        select(Interview).where(Interview.id == interview_id)
    )
    return result.scalar_one_or_none()


async def get_interview_archive(
    session: AsyncSession,
    server_id: int,
    limit: int = 20,
    offset: int = 0,
) -> list[Interview]:
    """Get past interviews for a server, most recent first."""
    result = await session.execute(
        select(Interview)
        .where(Interview.server_id == server_id)
        .order_by(Interview.started_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


# =============================================================================
# Questions
# =============================================================================


async def add_question(
    session: AsyncSession,
    interview_id: int,
    asker_id: int,
    asker_name: str,
    question_text: str,
    source_guild_id: int,
    source_channel_id: int,
    source_message_id: int,
) -> Question:
    """Add a question to an interview.

    Automatically assigns the next question number.
    """
    # Get next question number
    result = await session.execute(
        select(func.coalesce(func.max(Question.question_number), 0)).where(
            Question.interview_id == interview_id
        )
    )
    max_num = result.scalar() or 0
    next_num = max_num + 1

    question = Question(
        interview_id=interview_id,
        question_number=next_num,
        asker_id=asker_id,
        asker_name=asker_name,
        question_text=question_text,
        source_guild_id=source_guild_id,
        source_channel_id=source_channel_id,
        source_message_id=source_message_id,
    )
    session.add(question)
    await session.flush()
    return question


async def get_questions(
    session: AsyncSession,
    interview_id: int,
    filter_by: QuestionFilter = QuestionFilter.ALL,
    include_deleted: bool = False,
) -> list[Question]:
    """Get questions for an interview with optional filtering."""
    query = select(Question).where(Question.interview_id == interview_id)

    if not include_deleted:
        query = query.where(Question.deleted_at.is_(None))

    match filter_by:
        case QuestionFilter.UNANSWERED:
            query = query.where(Question.answer_text.is_(None))
        case QuestionFilter.ANSWERED_UNPOSTED:
            query = query.where(
                Question.answer_text.isnot(None),
                Question.is_posted == False,  # noqa: E712
            )
        case QuestionFilter.POSTED:
            query = query.where(Question.is_posted == True)  # noqa: E712
        case QuestionFilter.ALL:
            pass

    query = query.order_by(Question.question_number)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_question(session: AsyncSession, question_id: int) -> Question | None:
    """Get a question by ID."""
    result = await session.execute(
        select(Question).where(Question.id == question_id)
    )
    return result.scalar_one_or_none()


async def answer_question(
    session: AsyncSession,
    question_id: int,
    answer_text: str,
) -> Question | None:
    """Answer a question.

    Returns the question if found, None otherwise.
    """
    question = await get_question(session, question_id)
    if question is None:
        return None

    question.answer_text = answer_text
    question.answered_at = datetime.now(UTC)
    return question


async def delete_question(
    session: AsyncSession,
    question_id: int,
    deleted_by_id: int,
) -> Question | None:
    """Soft delete a question.

    Returns the question if found, None otherwise.
    """
    question = await get_question(session, question_id)
    if question is None:
        return None

    question.deleted_at = datetime.now(UTC)
    question.deleted_by_id = deleted_by_id
    return question


async def mark_posted(
    session: AsyncSession,
    question_ids: list[int],
    posted_message_id: int,
) -> int:
    """Mark questions as posted.

    Returns the number of questions updated.
    """
    result = await session.execute(
        select(Question).where(Question.id.in_(question_ids))
    )
    questions = result.scalars().all()

    count = 0
    for question in questions:
        question.is_posted = True
        question.posted_message_id = posted_message_id
        count += 1

    return count


# =============================================================================
# Voting
# =============================================================================


async def cast_vote(
    session: AsyncSession,
    server_id: int,
    voter_id: int,
    candidate_id: int,
    interview_id: int | None = None,
) -> Vote:
    """Cast a vote for a candidate.

    Args:
        server_id: The server where the vote is cast
        voter_id: The user casting the vote
        candidate_id: The user being voted for
        interview_id: Optional - the current interview (for historical tracking)

    Note: Does not check for existing votes - caller should handle that.
    UniqueConstraint will raise IntegrityError if duplicate.
    """
    vote = Vote(
        server_id=server_id,
        interview_id=interview_id,
        voter_id=voter_id,
        candidate_id=candidate_id,
    )
    session.add(vote)
    await session.flush()
    return vote


async def remove_vote(
    session: AsyncSession,
    server_id: int,
    voter_id: int,
) -> bool:
    """Remove all of a user's votes for a server.

    Returns True if any votes were removed, False otherwise.
    """
    result = await session.execute(
        select(Vote).where(
            Vote.server_id == server_id,
            Vote.voter_id == voter_id,
        )
    )
    votes = result.scalars().all()

    if not votes:
        return False

    for vote in votes:
        await session.delete(vote)
    # Flush to ensure deletes happen before any subsequent inserts
    await session.flush()
    return True


async def get_user_votes(
    session: AsyncSession,
    server_id: int,
    voter_id: int,
) -> list[Vote]:
    """Get all of a user's votes in a server."""
    result = await session.execute(
        select(Vote).where(
            Vote.server_id == server_id,
            Vote.voter_id == voter_id,
        )
    )
    return list(result.scalars().all())


async def get_votals(
    session: AsyncSession,
    server_id: int,
) -> list[tuple[int, int]]:
    """Get vote counts per candidate for a server.

    Returns list of (candidate_id, vote_count) tuples, ordered by count desc.
    """
    result = await session.execute(
        select(Vote.candidate_id, func.count(Vote.id).label("vote_count"))
        .where(Vote.server_id == server_id)
        .group_by(Vote.candidate_id)
        .order_by(func.count(Vote.id).desc())
    )
    return [(int(row[0]), int(row[1])) for row in result.all()]


# =============================================================================
# Server Config
# =============================================================================


async def get_server(session: AsyncSession, server_id: int) -> InterviewServer | None:
    """Get a server by ID."""
    result = await session.execute(
        select(InterviewServer).where(InterviewServer.id == server_id)
    )
    return result.scalar_one_or_none()


async def get_or_create_server(
    session: AsyncSession,
    server_id: int,
    name: str,
) -> tuple[InterviewServer, bool]:
    """Get or create a server.

    Returns (server, created) tuple.
    """
    server = await get_server(session, server_id)
    if server is not None:
        return server, False

    server = InterviewServer(id=server_id, name=name)
    session.add(server)
    await session.flush()
    return server, True


async def update_server_config(
    session: AsyncSession,
    server_id: int,
    *,
    name: str | None = None,
    answer_channel_id: int | None = None,
    backstage_channel_id: int | None = None,
    voting_channel_id: int | None = None,
    manager_role_id: int | None = None,
    audience_role_id: int | None = None,
    default_question: str | None = None,
    reinterview_days: int | None = None,
    reinterviews_allowed: bool | None = None,
    active: bool | None = None,
) -> InterviewServer | None:
    """Update server configuration fields.

    Only updates fields that are explicitly provided (not None).
    Returns the updated server, or None if not found.
    """
    server = await get_server(session, server_id)
    if server is None:
        return None

    if name is not None:
        server.name = name
    if answer_channel_id is not None:
        server.answer_channel_id = answer_channel_id
    if backstage_channel_id is not None:
        server.backstage_channel_id = backstage_channel_id
    if voting_channel_id is not None:
        server.voting_channel_id = voting_channel_id
    if manager_role_id is not None:
        server.manager_role_id = manager_role_id
    if audience_role_id is not None:
        server.audience_role_id = audience_role_id
    if default_question is not None:
        server.default_question = default_question
    if reinterview_days is not None:
        server.reinterview_days = reinterview_days
    if reinterviews_allowed is not None:
        server.reinterviews_allowed = reinterviews_allowed
    if active is not None:
        server.active = active

    return server


# =============================================================================
# Opt-outs
# =============================================================================


async def opt_out(
    session: AsyncSession,
    server_id: int,
    user_id: int,
) -> OptOut:
    """Opt a user out of being interviewed.

    Returns the OptOut record (creates if doesn't exist).
    """
    result = await session.execute(
        select(OptOut).where(
            OptOut.server_id == server_id,
            OptOut.user_id == user_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    opt_out_record = OptOut(server_id=server_id, user_id=user_id)
    session.add(opt_out_record)
    await session.flush()
    return opt_out_record


async def opt_in(
    session: AsyncSession,
    server_id: int,
    user_id: int,
) -> bool:
    """Opt a user back in (remove opt-out).

    Returns True if opt-out was removed, False if user wasn't opted out.
    """
    result = await session.execute(
        select(OptOut).where(
            OptOut.server_id == server_id,
            OptOut.user_id == user_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is None:
        return False

    await session.delete(existing)
    return True


async def is_opted_out(
    session: AsyncSession,
    server_id: int,
    user_id: int,
) -> bool:
    """Check if a user is opted out."""
    result = await session.execute(
        select(OptOut).where(
            OptOut.server_id == server_id,
            OptOut.user_id == user_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def get_opt_outs(
    session: AsyncSession,
    server_id: int,
) -> list[int]:
    """Get list of user IDs who have opted out."""
    result = await session.execute(
        select(OptOut.user_id).where(OptOut.server_id == server_id)
    )
    return [int(row[0]) for row in result.all()]


# =============================================================================
# Stats Queries
# =============================================================================


async def count_questions(
    session: AsyncSession,
    interview_id: int,
    answered_only: bool = False,
) -> int:
    """Count questions for an interview.

    If answered_only is True, only counts answered (non-deleted) questions.
    """
    query = select(func.count(Question.id)).where(
        Question.interview_id == interview_id,
        Question.deleted_at.is_(None),
    )
    if answered_only:
        query = query.where(Question.answer_text.isnot(None))

    result = await session.execute(query)
    return result.scalar() or 0


async def get_avg_answer_time(
    session: AsyncSession,
    interview_id: int,
) -> float | None:
    """Get average time between question and answer (in seconds).

    Returns None if no answered questions.
    """
    # For SQLite, we need to calculate this differently since it doesn't have
    # native timestamp arithmetic. PostgreSQL would use EXTRACT(EPOCH FROM ...).
    # For now, we'll fetch the data and calculate in Python.
    result = await session.execute(
        select(Question.asked_at, Question.answered_at).where(
            Question.interview_id == interview_id,
            Question.deleted_at.is_(None),
            Question.answered_at.isnot(None),
        )
    )
    rows = result.all()

    if not rows:
        return None

    total_seconds = sum(
        (row.answered_at - row.asked_at).total_seconds()
        for row in rows
    )
    return total_seconds / len(rows)


async def get_top_askers(
    session: AsyncSession,
    server_id: int,
    limit: int = 10,
) -> list[tuple[int, str, int]]:
    """Get users who have asked the most questions.

    Returns list of (user_id, user_name, question_count) tuples.
    """
    result = await session.execute(
        select(
            Question.asker_id,
            Question.asker_name,
            func.count(Question.id).label("count"),
        )
        .join(Interview, Question.interview_id == Interview.id)
        .where(
            Interview.server_id == server_id,
            Question.deleted_at.is_(None),
        )
        .group_by(Question.asker_id, Question.asker_name)
        .order_by(func.count(Question.id).desc())
        .limit(limit)
    )
    return [(int(row[0]), str(row[1]), int(row[2])) for row in result.all()]


async def get_server_stats(
    session: AsyncSession,
    server_id: int,
) -> dict:
    """Get aggregate statistics for a server.

    Returns dict with keys:
    - total_interviews: int
    - total_questions: int
    - total_answered: int
    - avg_questions_per_interview: float
    - avg_answer_time_seconds: float | None
    """
    # Count interviews
    interview_result = await session.execute(
        select(func.count(Interview.id)).where(Interview.server_id == server_id)
    )
    total_interviews = interview_result.scalar() or 0

    # Count questions (need to join to filter by server)
    question_result = await session.execute(
        select(func.count(Question.id))
        .join(Interview, Question.interview_id == Interview.id)
        .where(
            Interview.server_id == server_id,
            Question.deleted_at.is_(None),
        )
    )
    total_questions = question_result.scalar() or 0

    # Count answered questions
    answered_result = await session.execute(
        select(func.count(Question.id))
        .join(Interview, Question.interview_id == Interview.id)
        .where(
            Interview.server_id == server_id,
            Question.deleted_at.is_(None),
            Question.answer_text.isnot(None),
        )
    )
    total_answered = answered_result.scalar() or 0

    # Calculate averages
    avg_questions = total_questions / total_interviews if total_interviews > 0 else 0.0

    # Average answer time across all server interviews
    time_result = await session.execute(
        select(Question.asked_at, Question.answered_at)
        .join(Interview, Question.interview_id == Interview.id)
        .where(
            Interview.server_id == server_id,
            Question.deleted_at.is_(None),
            Question.answered_at.isnot(None),
        )
    )
    time_rows = time_result.all()
    if time_rows:
        total_seconds = sum(
            (row.answered_at - row.asked_at).total_seconds()
            for row in time_rows
        )
        avg_answer_time = total_seconds / len(time_rows)
    else:
        avg_answer_time = None

    return {
        "total_interviews": total_interviews,
        "total_questions": total_questions,
        "total_answered": total_answered,
        "avg_questions_per_interview": avg_questions,
        "avg_answer_time_seconds": avg_answer_time,
    }


# =============================================================================
# Authorization Helpers (stubs - full implementation with web auth)
# =============================================================================
#
# These functions check permissions for web routes. They need Discord API access
# to verify server membership and roles, which will be implemented when we build
# the web interface with OAuth2.
#
# For now, they're stubs that raise NotImplementedError to indicate they need
# the Discord bot or API client to function.


async def can_view_interview(
    session: AsyncSession,
    user_id: int,
    interview_id: int,
    *,
    discord_client: object | None = None,
) -> bool:
    """Check if user can view an interview.

    User must be a member of the server where the interview took place.

    Args:
        session: Database session
        user_id: Discord user ID
        interview_id: Interview to check access for
        discord_client: Discord client for API calls (required for full check)

    Returns:
        True if user can view, False otherwise
    """
    if discord_client is None:
        raise NotImplementedError(
            "can_view_interview requires discord_client for membership check"
        )

    # Get interview to find server_id
    interview = await get_interview(session, interview_id)
    if interview is None:
        return False

    # TODO: Check if user is member of interview.server_id via Discord API
    # For now, raise NotImplementedError
    raise NotImplementedError("Discord membership check not yet implemented")


async def can_view_unanswered(
    session: AsyncSession,
    user_id: int,
    interview_id: int,
    *,
    discord_client: object | None = None,
) -> bool:
    """Check if user can view unanswered questions.

    User must be either:
    - The current interviewee
    - A manager for the server

    Args:
        session: Database session
        user_id: Discord user ID
        interview_id: Interview to check access for
        discord_client: Discord client for API calls (required for role check)
    """
    interview = await get_interview(session, interview_id)
    if interview is None:
        return False

    # Interviewee can always view their own unanswered questions
    if interview.interviewee_id == user_id:
        return True

    # Check if user is manager
    return await can_manage_interview(
        session, user_id, interview.server_id, discord_client=discord_client
    )


async def can_manage_interview(
    session: AsyncSession,
    user_id: int,
    server_id: int,
    *,
    discord_client: object | None = None,
) -> bool:
    """Check if user can manage interviews (start/end, delete questions, etc.).

    User must have the manager role for the server.

    Args:
        session: Database session
        user_id: Discord user ID
        server_id: Server to check permissions for
        discord_client: Discord client for API calls (required for role check)
    """
    if discord_client is None:
        raise NotImplementedError(
            "can_manage_interview requires discord_client for role check"
        )

    server = await get_server(session, server_id)
    if server is None:
        return False

    if server.manager_role_id is None:
        # No manager role configured - only server admins can manage
        raise NotImplementedError("Server admin check not yet implemented")

    # TODO: Check if user has manager_role_id via Discord API
    raise NotImplementedError("Discord role check not yet implemented")


async def can_configure_server(
    session: AsyncSession,
    user_id: int,
    server_id: int,
    *,
    discord_client: object | None = None,
) -> bool:
    """Check if user can configure server settings.

    User must be a server administrator.

    Args:
        session: Database session
        user_id: Discord user ID
        server_id: Server to check permissions for
        discord_client: Discord client for API calls (required for admin check)
    """
    if discord_client is None:
        raise NotImplementedError(
            "can_configure_server requires discord_client for admin check"
        )

    # TODO: Check if user is server admin via Discord API
    raise NotImplementedError("Discord admin check not yet implemented")
