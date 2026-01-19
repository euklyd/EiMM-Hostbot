"""Tests for the interview search query parser."""

import pytest

from cogs.interview.search import (
    AndNode,
    FilterNode,
    NotNode,
    OrNode,
    ParseError,
    TextNode,
    parse_query,
)
from cogs.interview.search.ast import FilterType, MatchMode


class TestParseQuery:
    """Tests for the parse_query function."""

    def test_empty_query(self) -> None:
        """Empty query returns None."""
        assert parse_query("") is None
        assert parse_query("   ") is None

    def test_single_word(self) -> None:
        """Single word becomes TextNode with exact match."""
        result = parse_query("hello")
        assert result == TextNode("hello", MatchMode.EXACT)

    def test_multiple_words_implicit_and(self) -> None:
        """Multiple words become AND'd TextNodes."""
        result = parse_query("hello world")
        assert isinstance(result, AndNode)
        assert len(result.children) == 2
        assert result.children[0] == TextNode("hello", MatchMode.EXACT)
        assert result.children[1] == TextNode("world", MatchMode.EXACT)

    def test_quoted_phrase(self) -> None:
        """Quoted phrase becomes single TextNode."""
        result = parse_query('"hello world"')
        assert result == TextNode("hello world", MatchMode.EXACT)

    def test_fuzzy_word(self) -> None:
        """Tilde prefix makes word fuzzy."""
        result = parse_query("~hello")
        assert result == TextNode("hello", MatchMode.FUZZY)

    def test_fuzzy_phrase(self) -> None:
        """Tilde prefix with quoted phrase."""
        result = parse_query('~"hello world"')
        assert result == TextNode("hello world", MatchMode.FUZZY)


class TestFilterParsing:
    """Tests for filter expression parsing."""

    def test_exact_filter(self) -> None:
        """Filter with colon is exact match."""
        result = parse_query("asker:alice")
        assert result == FilterNode(FilterType.ASKER, MatchMode.EXACT, "alice")

    def test_fuzzy_filter(self) -> None:
        """Filter with tilde is fuzzy match."""
        result = parse_query("asker~alice")
        assert result == FilterNode(FilterType.ASKER, MatchMode.FUZZY, "alice")

    def test_filter_with_quoted_value(self) -> None:
        """Filter with quoted multi-word value."""
        result = parse_query('interviewee:"alice bob"')
        assert result == FilterNode(FilterType.INTERVIEWEE, MatchMode.EXACT, "alice bob")

    def test_fuzzy_filter_with_quoted_value(self) -> None:
        """Fuzzy filter with quoted value."""
        result = parse_query('content~"star wars"')
        assert result == FilterNode(FilterType.CONTENT, MatchMode.FUZZY, "star wars")

    def test_all_filter_types(self) -> None:
        """All filter types are recognized."""
        filters = ["asker", "interviewee", "content", "has", "after", "before"]
        for name in filters:
            result = parse_query(f"{name}:test")
            assert isinstance(result, FilterNode)
            assert result.filter_type.value == name

    def test_case_insensitive_filter_names(self) -> None:
        """Filter names are case insensitive."""
        result = parse_query("ASKER:alice")
        assert result == FilterNode(FilterType.ASKER, MatchMode.EXACT, "alice")

        result = parse_query("Interviewee:bob")
        assert result == FilterNode(FilterType.INTERVIEWEE, MatchMode.EXACT, "bob")


class TestOrExpression:
    """Tests for OR expressions."""

    def test_simple_or(self) -> None:
        """Two terms joined by 'or'."""
        result = parse_query("alice or bob")
        assert isinstance(result, OrNode)
        assert len(result.children) == 2
        assert result.children[0] == TextNode("alice", MatchMode.EXACT)
        assert result.children[1] == TextNode("bob", MatchMode.EXACT)

    def test_or_case_insensitive(self) -> None:
        """'or' keyword is case insensitive."""
        result = parse_query("alice OR bob")
        assert isinstance(result, OrNode)

        result = parse_query("alice Or bob")
        assert isinstance(result, OrNode)

    def test_multiple_or(self) -> None:
        """Multiple OR'd terms."""
        result = parse_query("alice or bob or charlie")
        assert isinstance(result, OrNode)
        assert len(result.children) == 3

    def test_or_with_filters(self) -> None:
        """OR with filter expressions."""
        result = parse_query("asker:alice or asker:bob")
        assert isinstance(result, OrNode)
        assert result.children[0] == FilterNode(FilterType.ASKER, MatchMode.EXACT, "alice")
        assert result.children[1] == FilterNode(FilterType.ASKER, MatchMode.EXACT, "bob")


class TestNegation:
    """Tests for negation with minus."""

    def test_negated_word(self) -> None:
        """Minus negates a word."""
        result = parse_query("-spam")
        assert isinstance(result, NotNode)
        assert result.child == TextNode("spam", MatchMode.EXACT)

    def test_negated_filter(self) -> None:
        """Minus negates a filter."""
        result = parse_query("-asker:alice")
        assert isinstance(result, NotNode)
        assert result.child == FilterNode(FilterType.ASKER, MatchMode.EXACT, "alice")

    def test_negation_in_and(self) -> None:
        """Negation within implicit AND."""
        result = parse_query("hello -spam")
        assert isinstance(result, AndNode)
        assert result.children[0] == TextNode("hello", MatchMode.EXACT)
        assert isinstance(result.children[1], NotNode)


class TestParentheses:
    """Tests for parenthesized expressions."""

    def test_simple_parens(self) -> None:
        """Parentheses group expressions."""
        result = parse_query("(hello)")
        assert result == TextNode("hello", MatchMode.EXACT)

    def test_or_in_parens(self) -> None:
        """OR expression in parentheses."""
        result = parse_query("(alice or bob) charlie")
        assert isinstance(result, AndNode)
        assert len(result.children) == 2
        assert isinstance(result.children[0], OrNode)
        assert result.children[1] == TextNode("charlie", MatchMode.EXACT)

    def test_nested_parens(self) -> None:
        """Nested parentheses."""
        result = parse_query("((hello))")
        assert result == TextNode("hello", MatchMode.EXACT)

    def test_negated_parens(self) -> None:
        """Negating a parenthesized expression."""
        result = parse_query("-(alice or bob)")
        assert isinstance(result, NotNode)
        assert isinstance(result.child, OrNode)


class TestComplexQueries:
    """Tests for complex real-world queries."""

    def test_filters_with_bare_text(self) -> None:
        """Mix of filters and bare text."""
        result = parse_query('asker:alice movie "star wars"')
        assert isinstance(result, AndNode)
        assert len(result.children) == 3
        assert result.children[0] == FilterNode(FilterType.ASKER, MatchMode.EXACT, "alice")
        assert result.children[1] == TextNode("movie", MatchMode.EXACT)
        assert result.children[2] == TextNode("star wars", MatchMode.EXACT)

    def test_or_and_precedence(self) -> None:
        """OR has lower precedence than implicit AND."""
        # "a b or c d" should be "(a AND b) OR (c AND d)"
        result = parse_query("a b or c d")
        assert isinstance(result, OrNode)
        assert len(result.children) == 2
        assert isinstance(result.children[0], AndNode)
        assert isinstance(result.children[1], AndNode)

    def test_complex_scryfall_style(self) -> None:
        """Scryfall-style complex query."""
        result = parse_query("(asker:alice or asker:bob) -has:image after:2024-01")
        assert isinstance(result, AndNode)
        assert len(result.children) == 3
        # First child is OR of askers
        assert isinstance(result.children[0], OrNode)
        # Second is negated has:image
        assert isinstance(result.children[1], NotNode)
        # Third is date filter
        assert result.children[2] == FilterNode(FilterType.AFTER, MatchMode.EXACT, "2024-01")


class TestParseErrors:
    """Tests for parser error handling."""

    def test_unclosed_quote(self) -> None:
        """Unclosed quote raises ParseError."""
        with pytest.raises(ParseError) as exc_info:
            parse_query('"hello world')
        assert "Unclosed quote" in str(exc_info.value)

    def test_unclosed_paren(self) -> None:
        """Unclosed parenthesis raises ParseError."""
        with pytest.raises(ParseError):
            parse_query("(hello world")

    def test_unmatched_close_paren(self) -> None:
        """Unmatched close paren raises ParseError."""
        with pytest.raises(ParseError):
            parse_query("hello world)")

    def test_filter_without_value(self) -> None:
        """Filter without value raises ParseError."""
        with pytest.raises(ParseError):
            parse_query("asker:")

    def test_filter_without_operator(self) -> None:
        """Filter name without operator raises ParseError."""
        with pytest.raises(ParseError):
            parse_query("asker alice")  # Missing : or ~


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_escaped_quotes(self) -> None:
        """Escaped quotes in quoted string."""
        result = parse_query(r'"hello \"world\""')
        assert result == TextNode('hello "world"', MatchMode.EXACT)

    def test_consecutive_fuzzy(self) -> None:
        """Multiple fuzzy terms."""
        result = parse_query("~hello ~world")
        assert isinstance(result, AndNode)
        assert result.children[0] == TextNode("hello", MatchMode.FUZZY)
        assert result.children[1] == TextNode("world", MatchMode.FUZZY)

    def test_mixed_exact_fuzzy(self) -> None:
        """Mix of exact and fuzzy terms."""
        result = parse_query("hello ~world")
        assert isinstance(result, AndNode)
        assert result.children[0] == TextNode("hello", MatchMode.EXACT)
        assert result.children[1] == TextNode("world", MatchMode.FUZZY)

    def test_double_negation(self) -> None:
        """Double negation should work."""
        result = parse_query("--hello")
        assert isinstance(result, NotNode)
        assert isinstance(result.child, NotNode)
        assert result.child.child == TextNode("hello", MatchMode.EXACT)

    def test_date_filter_format(self) -> None:
        """Date filters accept various formats."""
        # Absolute date
        result = parse_query("after:2024-01-15")
        assert result == FilterNode(FilterType.AFTER, MatchMode.EXACT, "2024-01-15")

        # Relative date
        result = parse_query("before:7days")
        assert result == FilterNode(FilterType.BEFORE, MatchMode.EXACT, "7days")
