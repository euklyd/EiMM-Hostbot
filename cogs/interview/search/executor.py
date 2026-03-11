"""Execute search queries against the database.

Converts AST nodes to SQLAlchemy expressions and executes them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import ColumnElement, and_, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from cogs.interview.models import Interview, InterviewServer, Question

from .ast import AndNode, FilterNode, FilterType, MatchMode, NotNode, OrNode, QueryNode, TextNode

if TYPE_CHECKING:
    from sqlalchemy.orm import InstrumentedAttribute

# Similarity threshold for fuzzy matching
FUZZY_THRESHOLD = 0.3


@dataclass
class SearchResult:
    """A single search result."""

    question: Question
    interview: Interview
    # Snippet highlighting could be added here later


@dataclass
class SearchResponse:
    """Response from a search query."""

    results: list[SearchResult]
    total_count: int


def _parse_relative_date(value: str) -> datetime | None:
    """Parse relative date like '7days', '1month', '2weeks'.

    Returns None if format is invalid.
    """
    match = re.match(r"^(\d+)(days?|weeks?|months?|years?)$", value.lower())
    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2)

    now = datetime.now(UTC)
    if unit.startswith("day"):
        return now - timedelta(days=amount)
    elif unit.startswith("week"):
        return now - timedelta(weeks=amount)
    elif unit.startswith("month"):
        # Approximate: 30 days per month
        return now - timedelta(days=amount * 30)
    elif unit.startswith("year"):
        # Approximate: 365 days per year
        return now - timedelta(days=amount * 365)
    return None


def _parse_date(value: str) -> datetime | None:
    """Parse date in various formats.

    Supports:
    - ISO format: 2024-01-15
    - Partial: 2024-01 (first of month)
    - Relative: 7days, 1month
    """
    # Try relative first
    relative = _parse_relative_date(value)
    if relative:
        return relative

    # Try ISO formats
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue

    return None


def _exact_match(column: InstrumentedAttribute[str | None], value: str) -> ColumnElement[bool]:
    """Create an exact match clause using ILIKE for case-insensitive substring match.

    Wildcards: * -> %, ? -> _
    """
    # Escape SQL wildcards in the value, then convert our wildcards
    escaped = value.replace("%", r"\%").replace("_", r"\_")
    pattern = escaped.replace("*", "%").replace("?", "_")
    return column.ilike(f"%{pattern}%")


def _fuzzy_match(column: InstrumentedAttribute[str | None], value: str) -> ColumnElement[bool]:
    """Create a fuzzy match clause using pg_trgm similarity."""
    return func.similarity(column, value) > FUZZY_THRESHOLD


def _build_filter_clause(node: FilterNode, interview_alias: type[Interview]) -> ColumnElement[bool]:
    """Build a SQLAlchemy clause for a filter node."""
    match_fn = _fuzzy_match if node.mode == MatchMode.FUZZY else _exact_match

    if node.filter_type == FilterType.ASKER:
        return match_fn(Question.asker_name, node.value)

    elif node.filter_type == FilterType.INTERVIEWEE:
        return match_fn(interview_alias.interviewee_name, node.value)

    elif node.filter_type == FilterType.CONTENT:
        # Search both question and answer text
        q_match = match_fn(Question.question_text, node.value)
        a_match = match_fn(Question.answer_text, node.value)
        return or_(q_match, a_match)

    elif node.filter_type == FilterType.HAS:
        val = node.value.lower()
        if val == "image":
            # Check for common image URL patterns
            return or_(
                Question.question_text.op("~*")(r"https?://[^\s]+\.(png|jpe?g|gif|webp)"),
                Question.answer_text.op("~*")(r"https?://[^\s]+\.(png|jpe?g|gif|webp)"),
            )
        elif val == "link":
            # Check for any URL
            return or_(
                Question.question_text.op("~*")(r"https?://[^\s]+"),
                Question.answer_text.op("~*")(r"https?://[^\s]+"),
            )
        # Unknown has: filter - return always-true
        return Question.id.is_not(None)

    elif node.filter_type == FilterType.AFTER:
        date = _parse_date(node.value)
        if date is None:
            # Invalid date - return always-true
            return Question.id.is_not(None)
        return Question.asked_at >= date

    elif node.filter_type == FilterType.BEFORE:
        date = _parse_date(node.value)
        if date is None:
            # Invalid date - return always-true
            return Question.id.is_not(None)
        return Question.asked_at <= date

    # Fallback - shouldn't happen
    return Question.id.is_not(None)


def _build_text_clause(node: TextNode) -> ColumnElement[bool]:
    """Build a SQLAlchemy clause for a text node (bare text search)."""
    match_fn = _fuzzy_match if node.mode == MatchMode.FUZZY else _exact_match

    # Search both question and answer text
    q_match = match_fn(Question.question_text, node.value)
    a_match = match_fn(Question.answer_text, node.value)
    return or_(q_match, a_match)


def build_clause(node: QueryNode, interview_alias: type[Interview]) -> ColumnElement[bool]:
    """Recursively build a SQLAlchemy clause from an AST node."""
    if isinstance(node, OrNode):
        return or_(*[build_clause(child, interview_alias) for child in node.children])

    elif isinstance(node, AndNode):
        return and_(*[build_clause(child, interview_alias) for child in node.children])

    elif isinstance(node, NotNode):
        return not_(build_clause(node.child, interview_alias))

    elif isinstance(node, FilterNode):
        return _build_filter_clause(node, interview_alias)

    elif isinstance(node, TextNode):
        return _build_text_clause(node)

    # Shouldn't happen
    raise ValueError(f"Unknown node type: {type(node)}")


async def execute_search(
    session: AsyncSession,
    query: QueryNode,
    *,
    server_ids: list[int] | None = None,
    posted_only: bool = True,
    limit: int = 50,
    offset: int = 0,
) -> SearchResponse:
    """Execute a search query and return results.

    Args:
        session: Database session
        query: Parsed query AST
        server_ids: Limit search to these servers (None = all)
        posted_only: Only search posted answers (True for heavyweight search)
        limit: Maximum results to return
        offset: Pagination offset
    """
    # Build the base query with eager loading of server relationship
    stmt = (
        select(Question, Interview)
        .join(Interview, Question.interview_id == Interview.id)
        .join(InterviewServer, Interview.server_id == InterviewServer.id)
        .options(joinedload(Interview.server))
        .where(Question.deleted_at.is_(None))  # Exclude deleted
    )

    # Apply server filter
    if server_ids:
        stmt = stmt.where(Interview.server_id.in_(server_ids))

    # Only posted answers for heavyweight search
    if posted_only:
        stmt = stmt.where(Question.is_posted.is_(True))

    # Apply search clause
    clause = build_clause(query, Interview)
    stmt = stmt.where(clause)

    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    count_result = await session.execute(count_stmt)
    total_count = count_result.scalar() or 0

    # Apply pagination and ordering
    stmt = stmt.order_by(Question.asked_at.desc()).offset(offset).limit(limit)

    # Execute
    result = await session.execute(stmt)
    rows = result.all()

    results = [SearchResult(question=row.Question, interview=row.Interview) for row in rows]

    return SearchResponse(results=results, total_count=total_count)
