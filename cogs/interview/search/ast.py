"""AST node types for search query parsing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MatchMode(Enum):
    """Match mode for filters and text."""

    EXACT = ":"  # Exact match (ILIKE)
    FUZZY = "~"  # Fuzzy match (pg_trgm similarity)


class FilterType(Enum):
    """Known filter types."""

    ASKER = "asker"
    INTERVIEWEE = "interviewee"
    CONTENT = "content"
    HAS = "has"
    AFTER = "after"
    BEFORE = "before"


@dataclass(frozen=True)
class OrNode:
    """OR of multiple children."""

    children: tuple[QueryNode, ...]

    def __repr__(self) -> str:
        return f"Or({', '.join(repr(c) for c in self.children)})"


@dataclass(frozen=True)
class AndNode:
    """AND of multiple children (implicit from adjacency)."""

    children: tuple[QueryNode, ...]

    def __repr__(self) -> str:
        return f"And({', '.join(repr(c) for c in self.children)})"


@dataclass(frozen=True)
class NotNode:
    """Negation of a child node."""

    child: QueryNode

    def __repr__(self) -> str:
        return f"Not({self.child!r})"


@dataclass(frozen=True)
class FilterNode:
    """A filter expression like asker:alice or content~"star wars"."""

    filter_type: FilterType
    mode: MatchMode
    value: str

    def __repr__(self) -> str:
        return f"{self.filter_type.value}{self.mode.value}{self.value!r}"


@dataclass(frozen=True)
class TextNode:
    """Bare text search (searches content by default)."""

    value: str
    mode: MatchMode = MatchMode.EXACT

    def __repr__(self) -> str:
        if self.mode == MatchMode.FUZZY:
            return f"~{self.value!r}"
        return repr(self.value)


# Union type for all query nodes
QueryNode = OrNode | AndNode | NotNode | FilterNode | TextNode
