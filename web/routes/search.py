"""Search API routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from cogs.interview.search import ParseError, execute_search, parse_query

from ..dependencies import CurrentUser, DbSession
from ..schemas import (
    SearchRequest,
    SearchResponse,
    SearchResultEntry,
    SearchResultInterview,
    SearchResultQuestion,
)

router = APIRouter(prefix="/api", tags=["search"])
logger = logging.getLogger(__name__)


@router.post("/search", response_model=SearchResponse)
async def search_interviews(
    request: SearchRequest,
    user: CurrentUser,
    db: DbSession,
) -> SearchResponse:
    """Search across all interviews the user has access to.

    Searches posted Q&A from all servers the user is a member of.
    Uses Scryfall-style query syntax with filters like asker:, interviewee:, content:.
    """
    # Parse the query
    try:
        ast = parse_query(request.query)
    except ParseError as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Invalid query syntax: {e}",
        )

    if ast is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Query cannot be empty",
        )

    # Get server IDs the user is a member of
    server_ids = user.guild_ids

    if not server_ids:
        # User has no guild memberships cached
        return SearchResponse(results=[], total_count=0, query=request.query)

    # Execute the search
    search_result = await execute_search(
        db,
        ast,
        server_ids=server_ids,
        posted_only=True,  # Heavyweight search only searches posted answers
        limit=request.limit,
        offset=request.offset,
    )

    # Convert to response format
    results = []
    for result in search_result.results:
        question = result.question
        interview = result.interview

        # Get server name from interview
        server_name = interview.server.name if interview.server else "Unknown Server"

        results.append(
            SearchResultEntry(
                question=SearchResultQuestion(
                    id=question.id,
                    question_number=question.question_number,
                    asker_id=str(question.asker_id),
                    asker_name=question.asker_name,
                    question_text=question.question_text,
                    answer_text=question.answer_text,
                    asked_at=question.asked_at,
                ),
                interview=SearchResultInterview(
                    id=interview.id,
                    interview_number=interview.interview_number,
                    server_id=str(interview.server_id),
                    server_name=server_name,
                    interviewee_id=str(interview.interviewee_id),
                    interviewee_name=interview.interviewee_name,
                ),
            )
        )

    return SearchResponse(
        results=results,
        total_count=search_result.total_count,
        query=request.query,
    )
