"""Tests for interview cog SQLAlchemy models.

These tests use in-memory SQLite but are written to work identically with PostgreSQL.
"""

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cogs.interview.models import Interview, InterviewServer, OptOut, Question, Vote


class TestInterviewServerModel:
    """Tests for the InterviewServer model."""

    def test_create_server(self, interview_session: Session) -> None:
        """Basic server creation."""
        server = InterviewServer(
            id=123456789012345678,  # Discord snowflake
            name="Test Server",
            answer_channel_id=111111111111111111,
            backstage_channel_id=222222222222222222,
            active=True,
        )
        interview_session.add(server)
        interview_session.commit()

        retrieved = interview_session.get(InterviewServer, 123456789012345678)
        assert retrieved is not None
        assert retrieved.name == "Test Server"
        assert retrieved.active is True
        assert retrieved.default_question == "What's your favorite card?"

    def test_server_defaults(self, interview_session: Session) -> None:
        """Server should have sensible defaults."""
        server = InterviewServer(id=1, name="Test")
        interview_session.add(server)
        interview_session.commit()

        assert server.active is False
        assert server.reinterviews_allowed is True
        assert server.reinterview_days == 0

    def test_server_repr(self, interview_session: Session) -> None:
        """Server __repr__ should be readable."""
        server = InterviewServer(id=1, name="Test Server", active=True)
        interview_session.add(server)
        interview_session.commit()

        repr_str = repr(server)
        assert "id=1" in repr_str
        assert "Test Server" in repr_str
        assert "active=True" in repr_str


class TestInterviewModel:
    """Tests for the Interview model."""

    def test_create_interview(self, interview_session: Session) -> None:
        """Basic interview creation."""
        server = InterviewServer(id=1, name="Test Server")
        interview = Interview(
            server=server,
            interview_number=1,
            interviewee_id=987654321098765432,
            interviewee_name="TestUser#1234",
        )
        interview_session.add(interview)
        interview_session.commit()

        retrieved = interview_session.get(Interview, interview.id)
        assert retrieved is not None
        assert retrieved.interviewee_name == "TestUser#1234"
        assert retrieved.is_current is True  # ended_at is None
        assert retrieved.server_id == 1

    def test_interview_server_relationship(self, interview_session: Session) -> None:
        """Interview should relate back to server."""
        server = InterviewServer(id=1, name="Test Server")
        interview = Interview(
            server=server,
            interview_number=1,
            interviewee_id=123,
            interviewee_name="User",
        )
        interview_session.add(interview)
        interview_session.commit()

        # Access from interview side
        assert interview.server.name == "Test Server"
        # Access from server side
        assert interview in server.interviews

    def test_questions_asked_property(self, interview_session: Session) -> None:
        """questions_asked should count questions."""
        server = InterviewServer(id=1, name="Test")
        interview = Interview(server=server, interview_number=1, interviewee_id=1, interviewee_name="User")

        # Add some questions
        for i in range(3):
            Question(
                interview=interview,
                question_number=i + 1,
                asker_id=100 + i,
                asker_name=f"Asker{i}",
                question_text=f"Question {i}?",
                source_guild_id=1,
                source_channel_id=1,
                source_message_id=1000 + i,
            )

        interview_session.add(interview)
        interview_session.commit()

        assert interview.questions_asked == 3

    def test_questions_answered_property(self, interview_session: Session) -> None:
        """questions_answered should count posted questions only."""
        server = InterviewServer(id=1, name="Test")
        interview = Interview(server=server, interview_number=1, interviewee_id=1, interviewee_name="User")

        # Add questions with different posted status
        for i in range(3):
            Question(
                interview=interview,
                question_number=i + 1,
                asker_id=100,
                asker_name="Asker",
                question_text=f"Question {i}?",
                is_posted=(i < 2),  # First 2 are posted
                source_guild_id=1,
                source_channel_id=1,
                source_message_id=1000 + i,
            )

        interview_session.add(interview)
        interview_session.commit()

        assert interview.questions_asked == 3
        assert interview.questions_answered == 2


class TestQuestionModel:
    """Tests for the Question model."""

    def test_create_question(self, interview_session: Session) -> None:
        """Basic question creation."""
        server = InterviewServer(id=1, name="Test")
        interview = Interview(server=server, interview_number=1, interviewee_id=1, interviewee_name="User")
        question = Question(
            interview=interview,
            question_number=1,
            asker_id=123456789,
            asker_name="Curious#1234",
            question_text="What's your favorite food?",
            source_guild_id=1,
            source_channel_id=2,
            source_message_id=3,
        )
        interview_session.add(question)
        interview_session.commit()

        retrieved = interview_session.get(Question, question.id)
        assert retrieved is not None
        assert retrieved.question_text == "What's your favorite food?"
        assert retrieved.is_posted is False
        assert retrieved.answer_text is None

    def test_question_with_answer(self, interview_session: Session) -> None:
        """Question with answer."""
        server = InterviewServer(id=1, name="Test")
        interview = Interview(server=server, interview_number=1, interviewee_id=1, interviewee_name="User")
        question = Question(
            interview=interview,
            question_number=1,
            asker_id=123,
            asker_name="Asker",
            question_text="Question?",
            answer_text="Answer!",
            is_posted=True,
            answered_at=datetime.now(UTC),
            source_guild_id=1,
            source_channel_id=2,
            source_message_id=3,
        )
        interview_session.add(question)
        interview_session.commit()

        assert question.answer_text == "Answer!"
        assert question.is_posted is True

    def test_jump_url_property(self, interview_session: Session) -> None:
        """jump_url should generate correct Discord URL."""
        server = InterviewServer(id=1, name="Test")
        interview = Interview(server=server, interview_number=1, interviewee_id=1, interviewee_name="User")
        question = Question(
            interview=interview,
            question_number=1,
            asker_id=123,
            asker_name="Asker",
            question_text="Question?",
            source_guild_id=111222333444555666,
            source_channel_id=222333444555666777,
            source_message_id=333444555666777888,
        )
        interview_session.add(question)
        interview_session.commit()

        expected = "https://discord.com/channels/111222333444555666/222333444555666777/333444555666777888"
        assert question.jump_url == expected


class TestVoteModel:
    """Tests for the Vote model."""

    def test_create_vote(self, interview_session: Session) -> None:
        """Basic vote creation."""
        server = InterviewServer(id=1, name="Test")
        interview = Interview(server=server, interview_number=1, interviewee_id=1, interviewee_name="User")
        vote = Vote(
            server_id=server.id,
            interview=interview,
            voter_id=111222333,
            candidate_id=444555666,
        )
        interview_session.add(vote)
        interview_session.commit()

        retrieved = interview_session.query(Vote).filter_by(interview_id=interview.id, voter_id=111222333).one()
        assert retrieved.candidate_id == 444555666

    def test_vote_unique_constraint(self, interview_session: Session) -> None:
        """Can't vote for the same candidate twice in same interview."""
        server = InterviewServer(id=1, name="Test")
        interview = Interview(server=server, interview_number=1, interviewee_id=1, interviewee_name="User")
        vote1 = Vote(server_id=server.id, interview=interview, voter_id=100, candidate_id=200)
        interview_session.add(vote1)
        interview_session.commit()

        # Same voter, same candidate, same server should fail
        vote2 = Vote(server_id=server.id, interview_id=interview.id, voter_id=100, candidate_id=200)
        interview_session.add(vote2)
        try:
            interview_session.commit()
            raise AssertionError("Should have raised IntegrityError")
        except IntegrityError:
            interview_session.rollback()

    def test_multiple_votes_different_candidates(self, interview_session: Session) -> None:
        """Same voter can vote for different candidates (up to limit)."""
        server = InterviewServer(id=1, name="Test")
        interview = Interview(server=server, interview_number=1, interviewee_id=1, interviewee_name="User")
        # User votes for 3 different candidates
        interview_session.add_all(
            [
                Vote(server_id=server.id, interview=interview, voter_id=100, candidate_id=201),
                Vote(server_id=server.id, interview=interview, voter_id=100, candidate_id=202),
                Vote(server_id=server.id, interview=interview, voter_id=100, candidate_id=203),
            ]
        )
        interview_session.commit()

        votes = interview_session.query(Vote).filter_by(voter_id=100).all()
        assert len(votes) == 3

    def test_multiple_voters(self, interview_session: Session) -> None:
        """Different voters can vote in same interview."""
        server = InterviewServer(id=1, name="Test")
        interview = Interview(server=server, interview_number=1, interviewee_id=1, interviewee_name="User")
        interview_session.add_all(
            [
                Vote(server_id=server.id, interview=interview, voter_id=100, candidate_id=999),
                Vote(server_id=server.id, interview=interview, voter_id=101, candidate_id=999),
                Vote(server_id=server.id, interview=interview, voter_id=102, candidate_id=888),
            ]
        )
        interview_session.commit()

        votes = interview_session.query(Vote).filter_by(interview_id=interview.id).all()
        assert len(votes) == 3

    def test_votes_across_interviews(self, interview_session: Session) -> None:
        """Same user can vote in different interviews (historical tracking)."""
        from datetime import UTC, datetime

        server = InterviewServer(id=1, name="Test")
        # Old interview (ended)
        interview1 = Interview(
            server=server, interview_number=1, interviewee_id=1, interviewee_name="User1", ended_at=datetime.now(UTC)
        )
        # Current interview (not ended)
        interview2 = Interview(server=server, interview_number=2, interviewee_id=2, interviewee_name="User2")

        # Same voter votes for different candidates in same server
        interview_session.add_all(
            [
                Vote(server_id=server.id, interview=interview1, voter_id=100, candidate_id=200),
                Vote(server_id=server.id, interview=interview2, voter_id=100, candidate_id=300),
            ]
        )
        interview_session.commit()

        all_votes = interview_session.query(Vote).filter_by(voter_id=100).all()
        assert len(all_votes) == 2


class TestOptOutModel:
    """Tests for the OptOut model."""

    def test_create_opt_out(self, interview_session: Session) -> None:
        """Basic opt-out creation."""
        server = InterviewServer(id=1, name="Test")
        opt_out = OptOut(server=server, user_id=123456789)
        interview_session.add(opt_out)
        interview_session.commit()

        retrieved = interview_session.query(OptOut).filter_by(server_id=1, user_id=123456789).one()
        assert retrieved is not None

    def test_opt_out_composite_key(self, interview_session: Session) -> None:
        """Composite key should enforce one opt-out per user per server."""
        server = InterviewServer(id=1, name="Test")
        opt1 = OptOut(server=server, user_id=100)
        interview_session.add(opt1)
        interview_session.commit()

        # Same user, same server should fail
        opt2 = OptOut(server_id=1, user_id=100)
        interview_session.add(opt2)
        try:
            interview_session.commit()
            raise AssertionError("Should have raised IntegrityError")
        except IntegrityError:
            interview_session.rollback()


class TestInterviewQueryPatterns:
    """Test common query patterns for the interview cog."""

    def test_get_current_interview(self, interview_session: Session) -> None:
        """Query for current interview (common pattern)."""
        from datetime import UTC, datetime

        server = InterviewServer(id=1, name="Test")
        # Old interview (ended)
        Interview(
            server=server, interview_number=1, interviewee_id=1, interviewee_name="Old", ended_at=datetime.now(UTC)
        )
        # Current interview (not ended)
        Interview(server=server, interview_number=2, interviewee_id=2, interviewee_name="Current")
        interview_session.add(server)
        interview_session.commit()

        # Query by ended_at IS NULL
        current = (
            interview_session.query(Interview)
            .filter(Interview.server_id == 1, Interview.ended_at.is_(None))
            .one_or_none()
        )
        assert current is not None
        assert current.interviewee_name == "Current"
        assert current.is_current is True

    def test_get_unanswered_questions(self, interview_session: Session) -> None:
        """Query for unanswered questions (for answer command)."""
        server = InterviewServer(id=1, name="Test")
        interview = Interview(server=server, interview_number=1, interviewee_id=1, interviewee_name="User")

        for i in range(5):
            Question(
                interview=interview,
                question_number=i + 1,
                asker_id=100,
                asker_name="Asker",
                question_text=f"Q{i}?",
                answer_text=f"A{i}" if i < 3 else None,  # First 3 answered
                is_posted=(i < 2),  # First 2 posted
                source_guild_id=1,
                source_channel_id=1,
                source_message_id=i,
            )

        interview_session.add(interview)
        interview_session.commit()

        # Answered but not posted (ready to post)
        ready_to_post = (
            interview_session.query(Question)
            .filter(
                Question.interview_id == interview.id,
                Question.answer_text.isnot(None),
                Question.is_posted == False,  # noqa: E712
            )
            .all()
        )
        assert len(ready_to_post) == 1
        assert ready_to_post[0].question_number == 3

    def test_count_votes_per_candidate(self, interview_session: Session) -> None:
        """Aggregate votes by candidate (for votals)."""
        from sqlalchemy import func

        server = InterviewServer(id=1, name="Test")
        interview = Interview(server=server, interview_number=1, interviewee_id=1, interviewee_name="User")
        interview_session.add_all(
            [
                Vote(server_id=server.id, interview=interview, voter_id=1, candidate_id=100),
                Vote(server_id=server.id, interview=interview, voter_id=2, candidate_id=100),
                Vote(server_id=server.id, interview=interview, voter_id=3, candidate_id=100),
                Vote(server_id=server.id, interview=interview, voter_id=4, candidate_id=200),
                Vote(server_id=server.id, interview=interview, voter_id=5, candidate_id=200),
            ]
        )
        interview_session.commit()

        # Count votes per candidate for current interview
        results = (
            interview_session.query(Vote.candidate_id, func.count(Vote.voter_id))
            .filter(Vote.interview_id == interview.id)
            .group_by(Vote.candidate_id)
            .order_by(func.count(Vote.voter_id).desc())
            .all()
        )

        assert results[0] == (100, 3)  # Candidate 100 has 3 votes
        assert results[1] == (200, 2)  # Candidate 200 has 2 votes


class TestQuestionSoftDelete:
    """Tests for the soft delete functionality on questions."""

    def test_is_deleted_property(self, interview_session: Session) -> None:
        """is_deleted returns True when deleted_at is set."""
        from datetime import UTC, datetime

        server = InterviewServer(id=1, name="Test")
        interview = Interview(server=server, interview_number=1, interviewee_id=1, interviewee_name="User")
        question = Question(
            interview=interview,
            question_number=1,
            asker_id=100,
            asker_name="Asker",
            question_text="Q?",
            source_guild_id=1,
            source_channel_id=1,
            source_message_id=1,
        )
        interview_session.add(question)
        interview_session.commit()

        # Initially not deleted
        assert question.is_deleted is False
        assert question.deleted_at is None
        assert question.deleted_by_id is None

        # Mark as deleted
        question.deleted_at = datetime.now(UTC)
        question.deleted_by_id = 999
        interview_session.commit()

        assert question.is_deleted is True

    def test_questions_asked_excludes_deleted(self, interview_session: Session) -> None:
        """Interview.questions_asked excludes soft-deleted questions."""
        from datetime import UTC, datetime

        server = InterviewServer(id=1, name="Test")
        interview = Interview(server=server, interview_number=1, interviewee_id=1, interviewee_name="User")

        for i in range(5):
            Question(
                interview=interview,
                question_number=i + 1,
                asker_id=100,
                asker_name="Asker",
                question_text=f"Q{i}?",
                source_guild_id=1,
                source_channel_id=1,
                source_message_id=i,
                # Delete questions 4 and 5
                deleted_at=datetime.now(UTC) if i >= 3 else None,
                deleted_by_id=999 if i >= 3 else None,
            )

        interview_session.add(interview)
        interview_session.commit()

        # Only non-deleted questions counted
        assert interview.questions_asked == 3

    def test_questions_answered_excludes_deleted(self, interview_session: Session) -> None:
        """Interview.questions_answered excludes soft-deleted questions."""
        from datetime import UTC, datetime

        server = InterviewServer(id=1, name="Test")
        interview = Interview(server=server, interview_number=1, interviewee_id=1, interviewee_name="User")

        for i in range(4):
            Question(
                interview=interview,
                question_number=i + 1,
                asker_id=100,
                asker_name="Asker",
                question_text=f"Q{i}?",
                answer_text=f"A{i}",
                is_posted=True,
                source_guild_id=1,
                source_channel_id=1,
                source_message_id=i,
                # Delete question 4 (which is posted)
                deleted_at=datetime.now(UTC) if i == 3 else None,
            )

        interview_session.add(interview)
        interview_session.commit()

        # Only non-deleted posted questions counted
        assert interview.questions_answered == 3
