"""Tests for the interview service layer."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from cogs.interview import service
from cogs.interview.models import Interview, InterviewServer, Question
from cogs.interview.service import QuestionFilter
from db.base import Base


@pytest.fixture
def sync_session() -> Session:
    """Create a sync session for setup (models require sync initially)."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
async def async_session() -> AsyncSession:
    """Create an async session for service tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
async def server_with_interview(async_session: AsyncSession) -> tuple[InterviewServer, Interview]:
    """Create a server with an active interview."""
    server = InterviewServer(id=1, name="Test Server")
    async_session.add(server)
    await async_session.flush()

    interview = await service.start_interview(
        async_session,
        server_id=1,
        interviewee_id=12345,
        interviewee_name="Test User",
    )
    await async_session.commit()
    return server, interview


class TestInterviewLifecycle:
    """Tests for interview lifecycle operations."""

    async def test_start_interview(self, async_session: AsyncSession) -> None:
        """Start a new interview."""
        server = InterviewServer(id=1, name="Test Server")
        async_session.add(server)
        await async_session.flush()

        interview = await service.start_interview(
            async_session,
            server_id=1,
            interviewee_id=12345,
            interviewee_name="Test User",
            op_channel_id=100,
            op_message_id=200,
        )
        await async_session.commit()

        assert interview.id is not None
        assert interview.interview_number == 1  # First interview for this server
        assert interview.interviewee_id == 12345
        assert interview.interviewee_name == "Test User"
        assert interview.op_channel_id == 100
        assert interview.is_current is True

    async def test_start_interview_ends_previous(self, async_session: AsyncSession) -> None:
        """Starting a new interview ends the current one."""
        server = InterviewServer(id=1, name="Test Server")
        async_session.add(server)
        await async_session.flush()

        # Start first interview
        interview1 = await service.start_interview(
            async_session, server_id=1, interviewee_id=1, interviewee_name="User1"
        )
        await async_session.commit()

        # Start second interview
        interview2 = await service.start_interview(
            async_session, server_id=1, interviewee_id=2, interviewee_name="User2"
        )
        await async_session.commit()

        # Refresh interview1 to get updated state
        await async_session.refresh(interview1)

        assert interview1.is_current is False
        assert interview1.ended_at is not None
        assert interview2.is_current is True

    async def test_interview_numbers_increment_per_server(self, async_session: AsyncSession) -> None:
        """Interview numbers increment independently per server."""
        server1 = InterviewServer(id=1, name="Server 1")
        server2 = InterviewServer(id=2, name="Server 2")
        async_session.add_all([server1, server2])
        await async_session.flush()

        # Start interviews on server 1
        iv1_s1 = await service.start_interview(async_session, 1, 100, "User A")
        iv2_s1 = await service.start_interview(async_session, 1, 101, "User B")
        iv3_s1 = await service.start_interview(async_session, 1, 102, "User C")

        # Start interviews on server 2
        iv1_s2 = await service.start_interview(async_session, 2, 200, "User X")
        iv2_s2 = await service.start_interview(async_session, 2, 201, "User Y")

        await async_session.commit()

        # Server 1 should have interviews numbered 1, 2, 3
        assert iv1_s1.interview_number == 1
        assert iv2_s1.interview_number == 2
        assert iv3_s1.interview_number == 3

        # Server 2 should have interviews numbered 1, 2 (independent)
        assert iv1_s2.interview_number == 1
        assert iv2_s2.interview_number == 2

    async def test_end_interview(
        self, async_session: AsyncSession, server_with_interview: tuple[InterviewServer, Interview]
    ) -> None:
        """End an interview."""
        _, interview = server_with_interview

        result = await service.end_interview(async_session, interview.id)
        await async_session.commit()

        assert result is not None
        assert result.ended_at is not None
        assert result.is_current is False

    async def test_end_interview_not_found(self, async_session: AsyncSession) -> None:
        """End interview returns None for non-existent ID."""
        result = await service.end_interview(async_session, 9999)
        assert result is None

    async def test_get_current_interview(
        self, async_session: AsyncSession, server_with_interview: tuple[InterviewServer, Interview]
    ) -> None:
        """Get the current interview for a server."""
        _, interview = server_with_interview

        result = await service.get_current_interview(async_session, server_id=1)
        assert result is not None
        assert result.id == interview.id

    async def test_get_current_interview_none(self, async_session: AsyncSession) -> None:
        """Returns None when no current interview."""
        result = await service.get_current_interview(async_session, server_id=1)
        assert result is None

    async def test_get_interview(
        self, async_session: AsyncSession, server_with_interview: tuple[InterviewServer, Interview]
    ) -> None:
        """Get an interview by ID."""
        _, interview = server_with_interview

        result = await service.get_interview(async_session, interview.id)
        assert result is not None
        assert result.interviewee_name == "Test User"

    async def test_get_interview_archive(self, async_session: AsyncSession) -> None:
        """Get interview archive sorted by date."""
        server = InterviewServer(id=1, name="Test Server")
        async_session.add(server)
        await async_session.flush()

        # Create several interviews
        for i in range(5):
            interview = await service.start_interview(
                async_session, server_id=1, interviewee_id=i, interviewee_name=f"User{i}"
            )
            if i < 4:  # End all but the last
                await service.end_interview(async_session, interview.id)
        await async_session.commit()

        archive = await service.get_interview_archive(async_session, server_id=1, limit=3)
        assert len(archive) == 3
        # All returned interviews should be distinct
        names = {iv.interviewee_name for iv in archive}
        assert len(names) == 3


class TestQuestions:
    """Tests for question operations."""

    async def test_add_question(
        self, async_session: AsyncSession, server_with_interview: tuple[InterviewServer, Interview]
    ) -> None:
        """Add a question to an interview."""
        _, interview = server_with_interview

        question = await service.add_question(
            async_session,
            interview_id=interview.id,
            asker_id=100,
            asker_name="Asker",
            question_text="What's your favorite color?",
            source_guild_id=1,
            source_channel_id=10,
            source_message_id=100,
        )
        await async_session.commit()

        assert question.id is not None
        assert question.question_number == 1
        assert question.question_text == "What's your favorite color?"

    async def test_add_question_auto_numbers(
        self, async_session: AsyncSession, server_with_interview: tuple[InterviewServer, Interview]
    ) -> None:
        """Questions are auto-numbered."""
        _, interview = server_with_interview

        for i in range(3):
            q = await service.add_question(
                async_session,
                interview_id=interview.id,
                asker_id=100,
                asker_name="Asker",
                question_text=f"Question {i}?",
                source_guild_id=1,
                source_channel_id=10,
                source_message_id=100 + i,
            )
            assert q.question_number == i + 1
        await async_session.commit()

    async def test_get_questions_all(
        self, async_session: AsyncSession, server_with_interview: tuple[InterviewServer, Interview]
    ) -> None:
        """Get all questions for an interview."""
        _, interview = server_with_interview

        for i in range(3):
            await service.add_question(
                async_session,
                interview_id=interview.id,
                asker_id=100,
                asker_name="Asker",
                question_text=f"Q{i}?",
                source_guild_id=1,
                source_channel_id=10,
                source_message_id=i,
            )
        await async_session.commit()

        questions = await service.get_questions(async_session, interview.id)
        assert len(questions) == 3

    async def test_get_questions_filtered(
        self, async_session: AsyncSession, server_with_interview: tuple[InterviewServer, Interview]
    ) -> None:
        """Get questions with various filters."""
        _, interview = server_with_interview

        # Create questions in different states
        q1 = await service.add_question(async_session, interview.id, 100, "A", "Q1?", 1, 10, 1)
        q2 = await service.add_question(async_session, interview.id, 100, "A", "Q2?", 1, 10, 2)
        q3 = await service.add_question(async_session, interview.id, 100, "A", "Q3?", 1, 10, 3)

        # Answer q1 and q2
        await service.answer_question(async_session, q1.id, "A1")
        await service.answer_question(async_session, q2.id, "A2")
        # Post q1
        await service.mark_posted(async_session, [q1.id], 999)
        await async_session.commit()

        unanswered = await service.get_questions(async_session, interview.id, QuestionFilter.UNANSWERED)
        assert len(unanswered) == 1
        assert unanswered[0].id == q3.id

        answered_unposted = await service.get_questions(async_session, interview.id, QuestionFilter.ANSWERED_UNPOSTED)
        assert len(answered_unposted) == 1
        assert answered_unposted[0].id == q2.id

        posted = await service.get_questions(async_session, interview.id, QuestionFilter.POSTED)
        assert len(posted) == 1
        assert posted[0].id == q1.id

    async def test_get_questions_excludes_deleted(
        self, async_session: AsyncSession, server_with_interview: tuple[InterviewServer, Interview]
    ) -> None:
        """Deleted questions are excluded by default."""
        _, interview = server_with_interview

        q1 = await service.add_question(async_session, interview.id, 100, "A", "Q1?", 1, 10, 1)
        q2 = await service.add_question(async_session, interview.id, 100, "A", "Q2?", 1, 10, 2)

        await service.delete_question(async_session, q1.id, deleted_by_id=999)
        await async_session.commit()

        questions = await service.get_questions(async_session, interview.id)
        assert len(questions) == 1
        assert questions[0].id == q2.id

        # Can include deleted if needed
        all_questions = await service.get_questions(async_session, interview.id, include_deleted=True)
        assert len(all_questions) == 2

    async def test_answer_question(
        self, async_session: AsyncSession, server_with_interview: tuple[InterviewServer, Interview]
    ) -> None:
        """Answer a question."""
        _, interview = server_with_interview

        q = await service.add_question(async_session, interview.id, 100, "A", "Q?", 1, 10, 1)
        await async_session.commit()

        result = await service.answer_question(async_session, q.id, "This is my answer")
        await async_session.commit()

        assert result is not None
        assert result.answer_text == "This is my answer"
        assert result.answered_at is not None

    async def test_delete_question(
        self, async_session: AsyncSession, server_with_interview: tuple[InterviewServer, Interview]
    ) -> None:
        """Soft delete a question."""
        _, interview = server_with_interview

        q = await service.add_question(async_session, interview.id, 100, "A", "Q?", 1, 10, 1)
        await async_session.commit()

        result = await service.delete_question(async_session, q.id, deleted_by_id=999)
        await async_session.commit()

        assert result is not None
        assert result.is_deleted is True
        assert result.deleted_by_id == 999

    async def test_mark_posted(
        self, async_session: AsyncSession, server_with_interview: tuple[InterviewServer, Interview]
    ) -> None:
        """Mark questions as posted."""
        _, interview = server_with_interview

        q1 = await service.add_question(async_session, interview.id, 100, "A", "Q1?", 1, 10, 1)
        q2 = await service.add_question(async_session, interview.id, 100, "A", "Q2?", 1, 10, 2)
        await async_session.commit()

        count = await service.mark_posted(async_session, [q1.id, q2.id], posted_message_id=12345)
        await async_session.commit()

        assert count == 2

        await async_session.refresh(q1)
        await async_session.refresh(q2)
        assert q1.is_posted is True
        assert q1.posted_message_id == 12345
        assert q2.is_posted is True


class TestVoting:
    """Tests for voting operations."""

    async def test_cast_vote(
        self, async_session: AsyncSession, server_with_interview: tuple[InterviewServer, Interview]
    ) -> None:
        """Cast a vote."""
        server, interview = server_with_interview

        vote = await service.cast_vote(
            async_session,
            server_id=server.id,
            voter_id=100,
            candidate_id=200,
            interview_id=interview.id,
        )
        await async_session.commit()

        assert vote.id is not None
        assert vote.server_id == server.id
        assert vote.voter_id == 100
        assert vote.candidate_id == 200
        assert vote.interview_id == interview.id

    async def test_cast_vote_without_interview(self, async_session: AsyncSession) -> None:
        """Cast a vote when no interview is active."""
        server = InterviewServer(id=1, name="Test Server", active=True)
        async_session.add(server)
        await async_session.flush()

        # Vote without an active interview
        vote = await service.cast_vote(
            async_session,
            server_id=server.id,
            voter_id=100,
            candidate_id=200,
            interview_id=None,
        )
        await async_session.commit()

        assert vote.id is not None
        assert vote.server_id == server.id
        assert vote.interview_id is None

    async def test_remove_vote(
        self, async_session: AsyncSession, server_with_interview: tuple[InterviewServer, Interview]
    ) -> None:
        """Remove a vote."""
        server, _ = server_with_interview

        await service.cast_vote(async_session, server.id, 100, 200)
        await async_session.commit()

        result = await service.remove_vote(async_session, server.id, voter_id=100)
        await async_session.commit()

        assert result is True

        # Verify vote is gone
        votes = await service.get_user_votes(async_session, server.id, 100)
        assert votes == []

    async def test_remove_vote_not_found(
        self, async_session: AsyncSession, server_with_interview: tuple[InterviewServer, Interview]
    ) -> None:
        """Remove vote returns False when no vote exists."""
        server, _ = server_with_interview

        result = await service.remove_vote(async_session, server.id, voter_id=999)
        assert result is False

    async def test_remove_vote_removes_all_candidates(
        self, async_session: AsyncSession, server_with_interview: tuple[InterviewServer, Interview]
    ) -> None:
        """Remove vote removes all candidates voter voted for."""
        server, _ = server_with_interview

        # Vote for multiple candidates
        await service.cast_vote(async_session, server.id, 100, 200)
        await service.cast_vote(async_session, server.id, 100, 300)
        await service.cast_vote(async_session, server.id, 100, 400)
        await async_session.commit()

        votes = await service.get_user_votes(async_session, server.id, 100)
        assert len(votes) == 3

        # Remove all votes
        result = await service.remove_vote(async_session, server.id, voter_id=100)
        await async_session.commit()

        assert result is True
        votes = await service.get_user_votes(async_session, server.id, 100)
        assert votes == []

    async def test_vote_override_same_session(
        self, async_session: AsyncSession, server_with_interview: tuple[InterviewServer, Interview]
    ) -> None:
        """Override vote in same session (tests flush after delete)."""
        server, _ = server_with_interview

        # Initial vote for candidates 200 and 300
        await service.cast_vote(async_session, server.id, 100, 200)
        await service.cast_vote(async_session, server.id, 100, 300)
        await async_session.commit()

        # Override: remove old votes and add new ones (same session, no commit between)
        await service.remove_vote(async_session, server.id, voter_id=100)
        # The flush() in remove_vote is critical here - without it, the new vote
        # would violate the unique constraint because the delete hasn't happened yet
        await service.cast_vote(async_session, server.id, 100, 200)  # Re-vote for 200
        await service.cast_vote(async_session, server.id, 100, 400)  # New vote for 400
        await async_session.commit()

        votes = await service.get_user_votes(async_session, server.id, 100)
        candidate_ids = {v.candidate_id for v in votes}
        assert candidate_ids == {200, 400}

    async def test_get_user_votes(
        self, async_session: AsyncSession, server_with_interview: tuple[InterviewServer, Interview]
    ) -> None:
        """Get a user's votes (can be multiple)."""
        server, _ = server_with_interview

        await service.cast_vote(async_session, server.id, 100, 200)
        await service.cast_vote(async_session, server.id, 100, 300)
        await async_session.commit()

        votes = await service.get_user_votes(async_session, server.id, 100)
        assert len(votes) == 2
        candidate_ids = {v.candidate_id for v in votes}
        assert candidate_ids == {200, 300}

    async def test_get_user_votes_empty(
        self, async_session: AsyncSession, server_with_interview: tuple[InterviewServer, Interview]
    ) -> None:
        """Get user votes returns empty list when no votes."""
        server, _ = server_with_interview

        votes = await service.get_user_votes(async_session, server.id, 100)
        assert votes == []

    async def test_get_votals(
        self, async_session: AsyncSession, server_with_interview: tuple[InterviewServer, Interview]
    ) -> None:
        """Get vote counts per candidate."""
        server, _ = server_with_interview

        # 3 votes for candidate 200, 2 for candidate 300
        await service.cast_vote(async_session, server.id, 1, 200)
        await service.cast_vote(async_session, server.id, 2, 200)
        await service.cast_vote(async_session, server.id, 3, 200)
        await service.cast_vote(async_session, server.id, 4, 300)
        await service.cast_vote(async_session, server.id, 5, 300)
        await async_session.commit()

        votals = await service.get_votals(async_session, server.id)
        assert len(votals) == 2
        assert votals[0] == (200, 3)  # Most votes first
        assert votals[1] == (300, 2)

    async def test_get_votals_empty(
        self, async_session: AsyncSession, server_with_interview: tuple[InterviewServer, Interview]
    ) -> None:
        """Get votals when no votes exist."""
        server, _ = server_with_interview

        votals = await service.get_votals(async_session, server.id)
        assert votals == []

    async def test_votes_persist_after_interview_ends(
        self, async_session: AsyncSession, server_with_interview: tuple[InterviewServer, Interview]
    ) -> None:
        """Votes remain after interview ends (they're per-server)."""
        server, interview = server_with_interview

        # Cast votes during interview
        await service.cast_vote(async_session, server.id, 100, 200, interview.id)
        await service.cast_vote(async_session, server.id, 101, 200, interview.id)
        await async_session.commit()

        # End interview
        await service.end_interview(async_session, interview.id)
        await async_session.commit()

        # Votes should still be queryable by server_id
        votals = await service.get_votals(async_session, server.id)
        assert len(votals) == 1
        assert votals[0] == (200, 2)


class TestServerConfig:
    """Tests for server configuration operations."""

    async def test_get_server(self, async_session: AsyncSession) -> None:
        """Get a server by ID."""
        server = InterviewServer(id=1, name="Test Server")
        async_session.add(server)
        await async_session.commit()

        result = await service.get_server(async_session, 1)
        assert result is not None
        assert result.name == "Test Server"

    async def test_get_server_not_found(self, async_session: AsyncSession) -> None:
        """Returns None when server doesn't exist."""
        result = await service.get_server(async_session, 9999)
        assert result is None

    async def test_get_or_create_server_creates(self, async_session: AsyncSession) -> None:
        """Creates server if it doesn't exist."""
        server, created = await service.get_or_create_server(async_session, 1, "New Server")
        await async_session.commit()

        assert created is True
        assert server.id == 1
        assert server.name == "New Server"

    async def test_get_or_create_server_gets_existing(self, async_session: AsyncSession) -> None:
        """Returns existing server if it exists."""
        # Create server first
        existing = InterviewServer(id=1, name="Existing Server")
        async_session.add(existing)
        await async_session.commit()

        server, created = await service.get_or_create_server(async_session, 1, "Different Name")

        assert created is False
        assert server.name == "Existing Server"  # Name not changed

    async def test_update_server_config(self, async_session: AsyncSession) -> None:
        """Update server configuration fields."""
        server = InterviewServer(id=1, name="Test Server")
        async_session.add(server)
        await async_session.commit()

        result = await service.update_server_config(
            async_session,
            server_id=1,
            answer_channel_id=100,
            manager_role_id=200,
            active=True,
        )
        await async_session.commit()

        assert result is not None
        assert result.answer_channel_id == 100
        assert result.manager_role_id == 200
        assert result.active is True
        # Unchanged fields remain
        assert result.name == "Test Server"

    async def test_update_server_config_not_found(self, async_session: AsyncSession) -> None:
        """Returns None when server doesn't exist."""
        result = await service.update_server_config(async_session, server_id=9999, active=True)
        assert result is None


class TestOptOuts:
    """Tests for opt-out operations."""

    async def test_opt_out(self, async_session: AsyncSession) -> None:
        """Opt a user out."""
        server = InterviewServer(id=1, name="Test Server")
        async_session.add(server)
        await async_session.commit()

        opt_out = await service.opt_out(async_session, server_id=1, user_id=100)
        await async_session.commit()

        assert opt_out.server_id == 1
        assert opt_out.user_id == 100

    async def test_opt_out_idempotent(self, async_session: AsyncSession) -> None:
        """Opting out twice returns existing record."""
        server = InterviewServer(id=1, name="Test Server")
        async_session.add(server)
        await async_session.commit()

        opt1 = await service.opt_out(async_session, 1, 100)
        await async_session.commit()
        opt2 = await service.opt_out(async_session, 1, 100)

        # Should be the same record
        assert opt1.server_id == opt2.server_id
        assert opt1.user_id == opt2.user_id

    async def test_opt_in(self, async_session: AsyncSession) -> None:
        """Opt a user back in."""
        server = InterviewServer(id=1, name="Test Server")
        async_session.add(server)
        await async_session.commit()

        await service.opt_out(async_session, 1, 100)
        await async_session.commit()

        result = await service.opt_in(async_session, 1, 100)
        await async_session.commit()

        assert result is True

        # Verify they're no longer opted out
        is_out = await service.is_opted_out(async_session, 1, 100)
        assert is_out is False

    async def test_opt_in_not_opted_out(self, async_session: AsyncSession) -> None:
        """Returns False when user wasn't opted out."""
        server = InterviewServer(id=1, name="Test Server")
        async_session.add(server)
        await async_session.commit()

        result = await service.opt_in(async_session, 1, 100)
        assert result is False

    async def test_is_opted_out(self, async_session: AsyncSession) -> None:
        """Check if user is opted out."""
        server = InterviewServer(id=1, name="Test Server")
        async_session.add(server)
        await async_session.commit()

        # Initially not opted out
        assert await service.is_opted_out(async_session, 1, 100) is False

        await service.opt_out(async_session, 1, 100)
        await async_session.commit()

        assert await service.is_opted_out(async_session, 1, 100) is True

    async def test_get_opt_outs(self, async_session: AsyncSession) -> None:
        """Get list of opted-out user IDs."""
        server = InterviewServer(id=1, name="Test Server")
        async_session.add(server)
        await async_session.commit()

        await service.opt_out(async_session, 1, 100)
        await service.opt_out(async_session, 1, 200)
        await service.opt_out(async_session, 1, 300)
        await async_session.commit()

        opt_outs = await service.get_opt_outs(async_session, 1)
        assert set(opt_outs) == {100, 200, 300}

    async def test_get_opt_outs_empty(self, async_session: AsyncSession) -> None:
        """Returns empty list when no opt-outs."""
        opt_outs = await service.get_opt_outs(async_session, 1)
        assert opt_outs == []


class TestStats:
    """Tests for statistics queries."""

    async def test_count_questions(
        self, async_session: AsyncSession, server_with_interview: tuple[InterviewServer, Interview]
    ) -> None:
        """Count questions for an interview."""
        _, interview = server_with_interview

        for i in range(5):
            q = await service.add_question(async_session, interview.id, 100, "A", f"Q{i}?", 1, 10, i)
            if i < 3:
                await service.answer_question(async_session, q.id, f"A{i}")
        await async_session.commit()

        total = await service.count_questions(async_session, interview.id)
        assert total == 5

        answered = await service.count_questions(async_session, interview.id, answered_only=True)
        assert answered == 3

    async def test_count_questions_excludes_deleted(
        self, async_session: AsyncSession, server_with_interview: tuple[InterviewServer, Interview]
    ) -> None:
        """Deleted questions are not counted."""
        _, interview = server_with_interview

        q1 = await service.add_question(async_session, interview.id, 100, "A", "Q1?", 1, 10, 1)
        await service.add_question(async_session, interview.id, 100, "A", "Q2?", 1, 10, 2)
        await service.delete_question(async_session, q1.id, 999)
        await async_session.commit()

        count = await service.count_questions(async_session, interview.id)
        assert count == 1

    async def test_get_avg_answer_time(
        self, async_session: AsyncSession, server_with_interview: tuple[InterviewServer, Interview]
    ) -> None:
        """Calculate average answer time."""
        from datetime import UTC, datetime, timedelta

        _, interview = server_with_interview

        # Create questions with known answer times
        now = datetime.now(UTC)
        for i in range(3):
            q = Question(
                interview_id=interview.id,
                question_number=i + 1,
                asker_id=100,
                asker_name="Asker",
                question_text=f"Q{i}?",
                answer_text=f"A{i}",
                asked_at=now,
                answered_at=now + timedelta(seconds=60 * (i + 1)),  # 60, 120, 180 seconds
                source_guild_id=1,
                source_channel_id=10,
                source_message_id=i,
            )
            async_session.add(q)
        await async_session.commit()

        avg_time = await service.get_avg_answer_time(async_session, interview.id)
        assert avg_time is not None
        assert avg_time == 120.0  # (60 + 120 + 180) / 3

    async def test_get_avg_answer_time_no_answers(
        self, async_session: AsyncSession, server_with_interview: tuple[InterviewServer, Interview]
    ) -> None:
        """Returns None when no answered questions."""
        _, interview = server_with_interview

        avg_time = await service.get_avg_answer_time(async_session, interview.id)
        assert avg_time is None

    async def test_get_top_askers(self, async_session: AsyncSession) -> None:
        """Get users who ask the most questions."""
        server = InterviewServer(id=1, name="Test Server")
        async_session.add(server)
        await async_session.flush()

        interview = await service.start_interview(async_session, 1, 1, "Interviewee")

        # User 100 asks 3, user 200 asks 2, user 300 asks 1
        for i in range(3):
            await service.add_question(async_session, interview.id, 100, "Alice", f"Q{i}?", 1, 10, i)
        for i in range(2):
            await service.add_question(async_session, interview.id, 200, "Bob", f"Q{i}?", 1, 10, 100 + i)
        await service.add_question(async_session, interview.id, 300, "Charlie", "Q?", 1, 10, 200)
        await async_session.commit()

        top = await service.get_top_askers(async_session, 1, limit=3)
        assert len(top) == 3
        assert top[0] == (100, "Alice", 3)
        assert top[1] == (200, "Bob", 2)
        assert top[2] == (300, "Charlie", 1)

    async def test_get_server_stats(self, async_session: AsyncSession) -> None:
        """Get aggregate stats for a server."""
        from datetime import UTC, datetime, timedelta

        server = InterviewServer(id=1, name="Test Server")
        async_session.add(server)
        await async_session.flush()

        # Create 2 interviews
        interview1 = await service.start_interview(async_session, 1, 1, "User1")
        await service.end_interview(async_session, interview1.id)
        interview2 = await service.start_interview(async_session, 1, 2, "User2")

        # Add questions (3 in interview1, 2 in interview2)
        now = datetime.now(UTC)
        for interview, count in [(interview1, 3), (interview2, 2)]:
            for i in range(count):
                q = Question(
                    interview_id=interview.id,
                    question_number=i + 1,
                    asker_id=100,
                    asker_name="Asker",
                    question_text=f"Q{i}?",
                    answer_text=f"A{i}" if i < 2 else None,  # Answer first 2
                    asked_at=now,
                    answered_at=now + timedelta(seconds=60) if i < 2 else None,
                    source_guild_id=1,
                    source_channel_id=10,
                    source_message_id=interview.id * 100 + i,
                )
                async_session.add(q)
        await async_session.commit()

        stats = await service.get_server_stats(async_session, 1)
        assert stats["total_interviews"] == 2
        assert stats["total_questions"] == 5
        assert stats["total_answered"] == 4  # 2 per interview
        assert stats["avg_questions_per_interview"] == 2.5
        assert stats["avg_answer_time_seconds"] == 60.0

    async def test_get_server_stats_empty(self, async_session: AsyncSession) -> None:
        """Stats for server with no interviews."""
        stats = await service.get_server_stats(async_session, 1)
        assert stats["total_interviews"] == 0
        assert stats["total_questions"] == 0
        assert stats["total_answered"] == 0
        assert stats["avg_questions_per_interview"] == 0.0
        assert stats["avg_answer_time_seconds"] is None
