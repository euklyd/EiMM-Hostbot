"""Interview API routes."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from fastapi import APIRouter, HTTPException, Query, WebSocket, status

from cogs.interview import service
from cogs.interview.embeds import IntervieweeData, QuestionData, generate_answer_embeds
from cogs.interview.service import QuestionFilter

from ..dependencies import BotInstance, CurrentUser, DbSession, check_manager_role
from ..schemas import (
    AnswerRequest,
    InterviewResponse,
    InterviewSummary,
    PostAnswersResponse,
    QuestionResponse,
    ServerResponse,
    ServerStatsResponse,
    ServerWithInterviewResponse,
    TopAskerResponse,
)

if TYPE_CHECKING:
    pass

router = APIRouter(prefix="/api", tags=["interviews"])
logger = logging.getLogger(__name__)


# =============================================================================
# Server Endpoints
# =============================================================================


@router.get("/servers", response_model=list[ServerWithInterviewResponse])
async def list_servers(
    user: CurrentUser,
    db: DbSession,
) -> list[ServerWithInterviewResponse]:
    """List servers the user is a member of that have interview configuration.

    Returns servers with their current interview status.
    """
    results = []

    # Use guild_ids (from session) since guilds list may be empty
    for guild_id in user.guild_ids:
        server = await service.get_server(db, guild_id)

        if server is None:
            continue  # Skip servers without interview setup

        current = await service.get_current_interview(db, guild_id)

        results.append(
            ServerWithInterviewResponse(
                server=ServerResponse.model_validate(server),
                current_interview=InterviewSummary.model_validate(current) if current else None,
            )
        )

    return results


@router.get("/servers/{server_id}", response_model=ServerWithInterviewResponse)
async def get_server(
    server_id: int,
    user: CurrentUser,
    db: DbSession,
    bot: BotInstance,
) -> ServerWithInterviewResponse:
    """Get server details with current interview info."""
    logger.debug(f"get_server: checking membership for {user.username} in {server_id}")
    logger.debug(f"get_server: user has {len(user.guild_ids)} guild_ids")
    if not user.is_member_of(server_id):
        logger.warning(f"get_server: {user.username} not a member of {server_id}, guild_ids={user.guild_ids[:5]}...")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this server")

    server = await service.get_server(db, server_id)
    if server is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Server not found")

    current = await service.get_current_interview(db, server_id)
    is_manager = await check_manager_role(server_id, user, bot, db)

    return ServerWithInterviewResponse(
        server=ServerResponse.model_validate(server),
        current_interview=InterviewSummary.model_validate(current) if current else None,
        is_manager=is_manager,
    )


@router.get("/servers/{server_id}/stats", response_model=ServerStatsResponse)
async def get_server_stats(
    server_id: int,
    user: CurrentUser,
    db: DbSession,
) -> ServerStatsResponse:
    """Get server statistics for dashboard."""
    if not user.is_member_of(server_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this server")

    stats = await service.get_server_stats(db, server_id)
    return ServerStatsResponse(**stats)


@router.get("/servers/{server_id}/top-askers", response_model=list[TopAskerResponse])
async def get_top_askers(
    server_id: int,
    user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=10, ge=1, le=100),
) -> list[TopAskerResponse]:
    """Get top question askers for a server."""
    if not user.is_member_of(server_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this server")

    askers = await service.get_top_askers(db, server_id, limit=limit)
    return [
        TopAskerResponse(user_id=str(user_id), user_name=user_name, question_count=count)
        for user_id, user_name, count in askers
    ]


# =============================================================================
# Interview Endpoints
# =============================================================================


@router.get("/servers/{server_id}/interviews", response_model=list[InterviewSummary])
async def list_interviews(
    server_id: int,
    user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[InterviewSummary]:
    """List past interviews for a server."""
    if not user.is_member_of(server_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this server")

    interviews = await service.get_interview_archive(db, server_id, limit=limit, offset=offset)
    return [InterviewSummary.model_validate(i) for i in interviews]


@router.get("/interviews/{interview_id}", response_model=InterviewResponse)
async def get_interview(
    interview_id: int,
    user: CurrentUser,
    db: DbSession,
) -> InterviewResponse:
    """Get interview details."""
    interview = await service.get_interview(db, interview_id)
    if interview is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview not found")

    if not user.is_member_of(interview.server_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this server")

    # Compute counts separately to avoid async lazy-loading issues
    questions_asked = await service.count_questions(db, interview_id)
    questions_answered = await service.count_questions(db, interview_id, posted_only=True)

    return InterviewResponse(
        id=interview.id,
        interview_number=interview.interview_number,
        server_id=str(interview.server_id),
        interviewee_id=str(interview.interviewee_id),
        interviewee_name=interview.interviewee_name,
        started_at=interview.started_at,
        ended_at=interview.ended_at,
        is_current=interview.is_current,
        questions_asked=questions_asked,
        questions_answered=questions_answered,
    )


# =============================================================================
# Question Endpoints
# =============================================================================


@router.get("/interviews/{interview_id}/questions", response_model=list[QuestionResponse])
async def list_questions(
    interview_id: int,
    user: CurrentUser,
    db: DbSession,
    bot: BotInstance,
    filter_by: str = Query(default="all", pattern="^(all|unanswered|answered|posted)$"),
) -> list[QuestionResponse]:
    """List questions for an interview.

    Query Parameters:
        filter_by: Filter questions - all, unanswered, answered (unposted), posted

    Access Control:
        - Managers and interviewee can see all questions
        - Other members can only see posted questions
    """
    interview = await service.get_interview(db, interview_id)
    if interview is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview not found")

    if not user.is_member_of(interview.server_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this server")

    # Check permissions
    is_interviewee = interview.interviewee_id == user.id
    is_manager = await check_manager_role(interview.server_id, user, bot, db)

    # Determine filter based on permissions
    if is_interviewee or is_manager:
        # Can see all questions, respect filter
        filter_enum = {
            "all": QuestionFilter.ALL,
            "unanswered": QuestionFilter.UNANSWERED,
            "answered": QuestionFilter.ANSWERED_UNPOSTED,
            "posted": QuestionFilter.POSTED,
        }.get(filter_by, QuestionFilter.ALL)
    else:
        # Can only see posted questions
        filter_enum = QuestionFilter.POSTED

    questions = await service.get_questions(db, interview_id, filter_by=filter_enum)
    return [QuestionResponse.model_validate(q) for q in questions]


@router.put("/questions/{question_id}/answer", response_model=QuestionResponse)
async def answer_question(
    question_id: int,
    body: AnswerRequest,
    user: CurrentUser,
    db: DbSession,
) -> QuestionResponse:
    """Answer a question.

    Only the interviewee can answer questions.
    """
    question = await service.get_question(db, question_id)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")

    interview = await service.get_interview(db, question.interview_id)
    if interview is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview not found")

    # Only interviewee can answer
    if interview.interviewee_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the interviewee can answer questions")

    # Update the answer
    updated = await service.answer_question(db, question_id, body.answer_text)
    await db.commit()

    logger.info(f"Question {question_id} answered by {user.username}")

    # Broadcast update via WebSocket
    try:
        from ..websocket import manager

        await manager.broadcast(
            interview.server_id,
            "question_answered",
            {"question_id": question_id},
        )
    except Exception:
        pass  # WebSocket not available or broadcast failed

    return QuestionResponse.model_validate(updated)


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(
    question_id: int,
    user: CurrentUser,
    db: DbSession,
    bot: BotInstance,
) -> None:
    """Soft-delete a question.

    Only managers can delete questions.
    """
    question = await service.get_question(db, question_id)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")

    interview = await service.get_interview(db, question.interview_id)
    if interview is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview not found")

    # Check manager permission
    is_manager = await check_manager_role(interview.server_id, user, bot, db)
    if not is_manager:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Manager role required")

    await service.delete_question(db, question_id, user.id)
    await db.commit()

    logger.info(f"Question {question_id} deleted by {user.username}")


# =============================================================================
# Post to Discord
# =============================================================================


@router.post("/interviews/{interview_id}/post", response_model=PostAnswersResponse)
async def post_answers(
    interview_id: int,
    user: CurrentUser,
    db: DbSession,
    bot: BotInstance,
) -> PostAnswersResponse:
    """Post answered questions to Discord.

    Only the interviewee can post answers.
    """
    interview = await service.get_interview(db, interview_id)
    if interview is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview not found")

    # Only interviewee can post
    if interview.interviewee_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the interviewee can post answers")

    server = await service.get_server(db, interview.server_id)
    if server is None or server.answer_channel_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No answer channel configured")

    # Get the Discord channel
    channel = bot.get_channel(server.answer_channel_id)
    if channel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Answer channel not found")
    if not isinstance(channel, discord.abc.Messageable):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Answer channel is not a text channel")

    # Get unposted answered questions
    questions = await service.get_questions(db, interview_id, filter_by=QuestionFilter.ANSWERED_UNPOSTED)
    if not questions:
        return PostAnswersResponse(success=True, posted_count=0, message="No answers to post")

    # Get interviewee info for embeds
    guild = bot.get_guild(interview.server_id)
    interviewee = guild.get_member(interview.interviewee_id) if guild else None

    interviewee_data = IntervieweeData(
        name=interview.interviewee_name,
        color=interviewee.color.value if interviewee else 0x5865F2,
        avatar_url=str(interviewee.display_avatar.url) if interviewee else "",
    )

    # Build question data for embeds
    question_data = [
        QuestionData(
            question_number=q.question_number,
            asker_name=q.asker_name,
            asker_avatar_url="",  # Could fetch from bot if needed
            question_text=q.question_text,
            answer_text=q.answer_text or "",
            jump_url=q.jump_url,
        )
        for q in questions
    ]

    # Count prior answered for embed numbering
    prior_answered = await service.count_questions(db, interview_id, answered_only=True) - len(questions)
    total_asked = await service.count_questions(db, interview_id)

    # Generate embeds
    result = generate_answer_embeds(interviewee_data, question_data, prior_answered, total_asked)

    # Post embeds to Discord
    question_ids = [q.id for q in questions]
    posted_count = 0

    for embed in result.embeds:
        try:
            msg = await channel.send(embed=embed)
            posted_count += 1
        except Exception as e:
            logger.error(f"Failed to post embed: {e}")
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Failed to post to Discord") from e

    # Mark questions as posted
    await service.mark_posted(db, question_ids, msg.id if result.embeds else 0)
    await db.commit()

    logger.info(f"Posted {posted_count} embeds with {len(questions)} answers for interview {interview_id}")

    return PostAnswersResponse(
        success=True,
        posted_count=len(questions),
        message=f"Posted {len(questions)} answers in {posted_count} embeds",
    )


# =============================================================================
# WebSocket
# =============================================================================


@router.websocket("/ws/{server_id}")
async def websocket_route(
    websocket: WebSocket,
    server_id: int,
) -> None:
    """WebSocket endpoint for real-time interview updates.

    Requires authentication via session cookie.
    """
    from ..dependencies import get_user_with_guilds

    # Authenticate from session cookie
    # Starlette's SessionMiddleware populates the session in scope
    session = websocket.scope.get("session", {})

    user_data = session.get("user")
    access_token = session.get("access_token")
    if not user_data:
        # Must accept before closing with a reason
        await websocket.accept()
        await websocket.close(code=4001, reason="Not authenticated")
        return

    try:
        user = await get_user_with_guilds(user_data, access_token)
    except Exception:
        await websocket.accept()
        await websocket.close(code=4001, reason="Invalid session")
        return

    # Check server membership
    if not user.is_member_of(server_id):
        await websocket.accept()
        await websocket.close(code=4003, reason="Not a member of this server")
        return

    # Handle the connection
    from ..websocket import websocket_endpoint

    await websocket_endpoint(websocket, server_id, user.id)
