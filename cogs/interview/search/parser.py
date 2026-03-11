"""Recursive descent parser for search query syntax."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum, auto

from .ast import AndNode, FilterNode, FilterType, MatchMode, NotNode, OrNode, QueryNode, TextNode


class TokenType(Enum):
    """Token types for the lexer."""

    LPAREN = auto()
    RPAREN = auto()
    COLON = auto()
    TILDE = auto()
    MINUS = auto()
    OR = auto()
    FILTER_NAME = auto()
    QUOTED = auto()
    WORD = auto()
    EOF = auto()


@dataclass
class Token:
    """A token from the lexer."""

    type: TokenType
    value: str
    pos: int


class ParseError(Exception):
    """Error during query parsing."""

    def __init__(self, message: str, pos: int | None = None):
        self.pos = pos
        super().__init__(message)


# Filter name mapping
FILTER_NAMES = {
    "asker": FilterType.ASKER,
    "interviewee": FilterType.INTERVIEWEE,
    "content": FilterType.CONTENT,
    "has": FilterType.HAS,
    "after": FilterType.AFTER,
    "before": FilterType.BEFORE,
}


def tokenize(query: str) -> Iterator[Token]:
    """Tokenize a search query string."""
    pos = 0
    length = len(query)
    # Track if we're at a position where negation is valid (start of term)
    at_term_start = True

    while pos < length:
        # Skip whitespace
        if query[pos].isspace():
            pos += 1
            at_term_start = True
            continue

        # Single character tokens
        if query[pos] == "(":
            yield Token(TokenType.LPAREN, "(", pos)
            pos += 1
            at_term_start = True
            continue
        if query[pos] == ")":
            yield Token(TokenType.RPAREN, ")", pos)
            pos += 1
            at_term_start = False
            continue
        if query[pos] == ":":
            yield Token(TokenType.COLON, ":", pos)
            pos += 1
            at_term_start = False  # After :, we expect a value
            continue
        if query[pos] == "~":
            yield Token(TokenType.TILDE, "~", pos)
            pos += 1
            at_term_start = False  # After ~, we expect a value
            continue

        # Minus is only MINUS token at term start, otherwise part of word
        if query[pos] == "-" and at_term_start:
            yield Token(TokenType.MINUS, "-", pos)
            pos += 1
            # Stay at term start to allow --hello (double negation)
            continue

        # Quoted string
        if query[pos] == '"':
            start = pos
            pos += 1
            while pos < length and query[pos] != '"':
                if query[pos] == "\\" and pos + 1 < length:
                    pos += 2  # Skip escaped char
                else:
                    pos += 1
            if pos >= length:
                raise ParseError(f"Unclosed quote starting at position {start}", start)
            # Extract content without quotes, unescape
            content = query[start + 1 : pos].replace('\\"', '"').replace("\\\\", "\\")
            yield Token(TokenType.QUOTED, content, start)
            pos += 1  # Skip closing quote
            at_term_start = False
            continue

        # Word (including potential filter names, 'or', and embedded hyphens)
        start = pos
        while pos < length and query[pos] not in ' \t\n():~"':
            # Stop at hyphen only if it's at term start (but we already handled that above)
            pos += 1

        word = query[start:pos]
        if not word:
            raise ParseError(f"Unexpected character at position {start}: {query[start]!r}", start)

        # Check for 'or' keyword (case insensitive)
        if word.lower() == "or":
            yield Token(TokenType.OR, word, start)
            at_term_start = True  # After 'or', new term starts
        # Check for filter name
        elif word.lower() in FILTER_NAMES:
            yield Token(TokenType.FILTER_NAME, word.lower(), start)
            at_term_start = False
        else:
            yield Token(TokenType.WORD, word, start)
            at_term_start = False

    yield Token(TokenType.EOF, "", length)


class Parser:
    """Recursive descent parser for search queries."""

    def __init__(self, query: str):
        self.query = query
        self.tokens = list(tokenize(query))
        self.pos = 0

    def current(self) -> Token:
        """Get the current token."""
        return self.tokens[self.pos]

    def advance(self) -> Token:
        """Consume and return the current token."""
        token = self.current()
        if token.type != TokenType.EOF:
            self.pos += 1
        return token

    def peek(self, offset: int = 0) -> Token:
        """Look ahead at a token."""
        idx = self.pos + offset
        if idx >= len(self.tokens):
            return self.tokens[-1]  # EOF
        return self.tokens[idx]

    def match(self, *types: TokenType) -> bool:
        """Check if current token matches any of the given types."""
        return self.current().type in types

    def expect(self, token_type: TokenType) -> Token:
        """Consume a token of the expected type, or raise an error."""
        if self.current().type != token_type:
            raise ParseError(
                f"Expected {token_type.name}, got {self.current().type.name} at position {self.current().pos}",
                self.current().pos,
            )
        return self.advance()

    def parse(self) -> QueryNode | None:
        """Parse the full query."""
        if self.current().type == TokenType.EOF:
            return None
        result = self.parse_or_expr()
        if self.current().type != TokenType.EOF:
            raise ParseError(
                f"Unexpected token at position {self.current().pos}: {self.current().value!r}",
                self.current().pos,
            )
        return result

    def parse_or_expr(self) -> QueryNode:
        """OrExpr -> AndExpr ('or' AndExpr)*"""
        children = [self.parse_and_expr()]

        while self.match(TokenType.OR):
            self.advance()  # consume 'or'
            children.append(self.parse_and_expr())

        if len(children) == 1:
            return children[0]
        return OrNode(tuple(children))

    def parse_and_expr(self) -> QueryNode:
        """AndExpr -> Term (Term)*  (implicit AND)"""
        children = [self.parse_term()]

        # Keep parsing terms until we hit OR, ), or EOF
        while not self.match(TokenType.OR, TokenType.RPAREN, TokenType.EOF):
            children.append(self.parse_term())

        if len(children) == 1:
            return children[0]
        return AndNode(tuple(children))

    def parse_term(self) -> QueryNode:
        """Term -> '-'? Atom (supports double negation via recursion)"""
        if self.match(TokenType.MINUS):
            self.advance()  # consume '-'
            # Recurse to handle double negation like --hello
            return NotNode(self.parse_term())
        return self.parse_atom()

    def parse_atom(self) -> QueryNode:
        """Atom -> '(' OrExpr ')' | Filter | FuzzyText | Text"""
        # Parenthesized expression
        if self.match(TokenType.LPAREN):
            self.advance()  # consume '('
            expr = self.parse_or_expr()
            self.expect(TokenType.RPAREN)
            return expr

        # Filter: filter_name (':' | '~') value
        if self.match(TokenType.FILTER_NAME):
            filter_name = self.advance()
            filter_type = FILTER_NAMES[filter_name.value]

            if self.match(TokenType.COLON):
                self.advance()
                mode = MatchMode.EXACT
            elif self.match(TokenType.TILDE):
                self.advance()
                mode = MatchMode.FUZZY
            else:
                raise ParseError(
                    f"Expected ':' or '~' after filter name at position {self.current().pos}",
                    self.current().pos,
                )

            value = self.parse_value()
            return FilterNode(filter_type, mode, value)

        # Fuzzy bare text: '~' value
        if self.match(TokenType.TILDE):
            self.advance()  # consume '~'
            value = self.parse_value()
            return TextNode(value, MatchMode.FUZZY)

        # Exact bare text: value (word or quoted)
        if self.match(TokenType.WORD, TokenType.QUOTED):
            value = self.parse_value()
            return TextNode(value, MatchMode.EXACT)

        raise ParseError(
            f"Unexpected token at position {self.current().pos}: {self.current().value!r}",
            self.current().pos,
        )

    def parse_value(self) -> str:
        """Value -> QuotedString | Word"""
        if self.match(TokenType.QUOTED, TokenType.WORD):
            return self.advance().value
        raise ParseError(
            f"Expected value at position {self.current().pos}, got {self.current().type.name}",
            self.current().pos,
        )


def parse_query(query: str) -> QueryNode | None:
    """Parse a search query string into an AST.

    Returns None for empty queries.
    """
    return Parser(query.strip()).parse()
