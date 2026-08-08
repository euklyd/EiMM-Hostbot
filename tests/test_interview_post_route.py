"""Tests for the POST /api/interviews/{id}/post route.

Covers the bug where a Q&A too long to embed was silently marked posted
even though no Discord message was ever sent.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cogs.interview import service
from cogs.interview.models import Interview, InterviewServer
from db.base import Base
from web.routes.interviews import post_answers
from web.schemas import DiscordUser


@pytest.fixture
async def async_session() -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
async def server_with_interview(async_session: AsyncSession) -> tuple[InterviewServer, Interview]:
    server = InterviewServer(id=1, name="Test Server", answer_channel_id=999)
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


def make_mock_bot(sent_message_id: int = 555) -> MagicMock:
    """A mock bot whose channel.send() succeeds and records calls."""
    channel = MagicMock(spec=discord.TextChannel)
    sent_message = MagicMock()
    sent_message.id = sent_message_id
    channel.send = AsyncMock(return_value=sent_message)

    bot = MagicMock()
    bot.get_channel = MagicMock(return_value=channel)
    bot.get_guild = MagicMock(return_value=None)
    return bot


class TestPostAnswersSkippedQuestions:
    """A question too long to embed must not be marked posted or reported as success."""

    async def test_oversized_answer_does_not_get_marked_posted(
        self,
        async_session: AsyncSession,
        server_with_interview: tuple[InterviewServer, Interview],
    ) -> None:
        _server, interview = server_with_interview
        # An answer with an unreasonable safety-valve-triggering length
        # (see MAX_SPLIT_EMBEDS in cogs/interview/embeds.py) - genuinely
        # unpostable, not just "long".
        question = await service.add_question(
            async_session,
            interview_id=interview.id,
            asker_id=1,
            asker_name="Asker",
            question_text="Q?",
            source_guild_id=1,
            source_channel_id=1,
            source_message_id=1,
        )
        await service.answer_question(async_session, question.id, "word " * 60000)
        await async_session.commit()

        bot = make_mock_bot()
        user = DiscordUser(id=12345, username="Test User")

        # Nothing postable is a real failure, not a silent 200 OK.
        with pytest.raises(HTTPException) as exc_info:
            await post_answers(interview.id, user, async_session, bot)
        assert exc_info.value.status_code == 422

        # Nothing was actually sent to Discord, so nothing should be marked posted.
        bot_channel = bot.get_channel.return_value
        bot_channel.send.assert_not_called()

        refreshed = await service.get_question(async_session, question.id)
        assert refreshed is not None
        assert refreshed.is_posted is False

    async def test_skipped_answer_mixed_with_valid_reports_skip_count(
        self,
        async_session: AsyncSession,
        server_with_interview: tuple[InterviewServer, Interview],
    ) -> None:
        """A postable question and an unpostable one: the postable one is
        posted and marked, the unpostable one is left alone and counted."""
        _server, interview = server_with_interview

        good_question = await service.add_question(
            async_session,
            interview_id=interview.id,
            asker_id=1,
            asker_name="Asker",
            question_text="Q1?",
            source_guild_id=1,
            source_channel_id=1,
            source_message_id=1,
        )
        await service.answer_question(async_session, good_question.id, "A short answer")

        bad_question = await service.add_question(
            async_session,
            interview_id=interview.id,
            asker_id=1,
            asker_name="Asker",
            question_text="Q2?",
            source_guild_id=1,
            source_channel_id=1,
            source_message_id=2,
        )
        await service.answer_question(async_session, bad_question.id, "word " * 60000)
        await async_session.commit()

        bot = make_mock_bot()
        user = DiscordUser(id=12345, username="Test User")

        response = await post_answers(interview.id, user, async_session, bot)

        assert response.success is True
        assert response.posted_count == 1
        assert response.skipped_count == 1

        good_refreshed = await service.get_question(async_session, good_question.id)
        bad_refreshed = await service.get_question(async_session, bad_question.id)
        assert good_refreshed is not None and good_refreshed.is_posted is True
        assert bad_refreshed is not None and bad_refreshed.is_posted is False
