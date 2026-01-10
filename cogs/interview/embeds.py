"""Embed generation logic for interview Q&A posts.

This module handles the complex task of fitting questions and answers into
Discord embeds while respecting various character limits.

Discord Embed Limits (as of 2024):
- Total embed: 6000 characters
- Field name: 256 characters
- Field value: 1024 characters
- Fields per embed: 25
- Description: 4096 characters
- Title: 256 characters
"""

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import NamedTuple

import discord

# Bare image URL pattern: URL on its own line ending in common image extensions
# Matches URLs like https://example.com/image.png or https://imgur.com/abc.jpg?1
IMAGE_URL_PATTERN = re.compile(
    r'^\s*(https?://\S+\.(?:png|jpe?g|gif|webp|bmp|svg)(?:\?\S*)?)\s*$',
    re.IGNORECASE | re.MULTILINE,
)

# Discord embed character limits
EMBED_TOTAL_LIMIT = 6000
EMBED_FIELD_NAME_LIMIT = 256
EMBED_FIELD_VALUE_LIMIT = 1024
EMBED_FIELDS_LIMIT = 25
EMBED_DESCRIPTION_LIMIT = 4096
EMBED_TITLE_LIMIT = 256

# Safety margins - leave room for formatting, links, etc.
# We use 4800 as the "safe" total to leave room for author, footer, etc.
SAFE_EMBED_TOTAL = 4800
# Leave room for markdown link syntax: "> [text](url)" adds ~100 chars for URLs
SAFE_FIELD_VALUE = 900
# Leave room for answer field name text when chunking
SAFE_ANSWER_CHUNK = 950
# Maximum fields before we need a new embed (leave 2 as buffer for edge cases)
SAFE_FIELDS_PER_EMBED = 23


class AddQuestionResult(Enum):
    """Result of attempting to add a question to an embed."""

    SUCCESS = auto()
    EMBED_FULL = auto()  # Total embed length exceeded, try new embed
    QUESTION_TOO_LONG = auto()  # Single Q&A too long for any embed


@dataclass
class QuestionData:
    """Data needed to format a question in an embed.

    This is decoupled from the SQLAlchemy Question model and Discord types
    to make the embed logic independently testable.
    """

    question_number: int
    asker_name: str
    asker_avatar_url: str
    question_text: str
    answer_text: str
    jump_url: str


@dataclass
class IntervieweeData:
    """Data about the interviewee for embed headers."""

    name: str
    color: int  # Discord color as int
    avatar_url: str


class EmbedLength(NamedTuple):
    """Track embed length for limit checking."""

    current: int
    added: int

    @property
    def total(self) -> int:
        return self.current + self.added


def escape_markdown_links(text: str) -> str:
    """Escape square brackets to prevent markdown link interference."""
    return text.replace("[", "\\[").replace("]", "\\]")


@dataclass
class ImageData:
    """An image extracted from answer text."""

    alt: str
    url: str


def extract_images_from_text(text: str) -> tuple[str, list[ImageData]]:
    """Extract image URLs from text.

    Finds bare image URLs on their own lines and returns the text with
    those lines removed, plus a list of extracted images.

    Args:
        text: The answer text potentially containing image URLs

    Returns:
        Tuple of (cleaned_text, list of ImageData)
    """
    images: list[ImageData] = []

    def replace_image(match: re.Match[str]) -> str:
        url = match.group(1)
        images.append(ImageData(alt="", url=url))
        return ""  # Remove image URL line from text

    cleaned = IMAGE_URL_PATTERN.sub(replace_image, text)
    # Clean up extra whitespace/blank lines left behind
    cleaned = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned).strip()

    return cleaned, images


def split_text_into_chunks(text: str, max_chunk_size: int) -> list[str]:
    """Split text into chunks that fit within a size limit.

    Splits on word boundaries when possible. Words longer than max_chunk_size
    are forcibly split.

    Args:
        text: The text to split
        max_chunk_size: Maximum characters per chunk

    Returns:
        List of text chunks, each <= max_chunk_size characters
    """
    if not text:
        return [""]

    # Escape markdown before splitting
    escaped = escape_markdown_links(text)
    words = escaped.split(" ")
    chunks: list[str] = []
    current_chunk = ""

    for word in words:
        # Handle words longer than max size by force-splitting them
        while len(word) > max_chunk_size:
            if current_chunk:
                chunks.append(current_chunk.rstrip())
                current_chunk = ""
            chunks.append(word[:max_chunk_size])
            word = word[max_chunk_size:]

        # Check if adding this word would exceed limit
        test_chunk = f"{current_chunk}{word} " if current_chunk else f"{word} "
        if len(test_chunk.rstrip()) > max_chunk_size:
            # Start new chunk
            if current_chunk:
                chunks.append(current_chunk.rstrip())
            current_chunk = f"{word} "
        else:
            current_chunk = test_chunk

    # Don't forget the last chunk
    if current_chunk:
        chunks.append(current_chunk.rstrip())

    return chunks if chunks else [""]


def format_question_as_quote(text: str, jump_url: str) -> str:
    """Format question text as a quoted block with jump link.

    Each line gets "> " prefix, and the whole thing becomes a markdown link.
    """
    escaped = escape_markdown_links(text)
    lines = [line.strip() for line in escaped.split("\n")]
    quote_block = "\n> ".join(lines)
    return f"> [{quote_block}]({jump_url})"


def create_blank_embed(
    interviewee: IntervieweeData,
    asker_name: str,
    asker_avatar_url: str,
) -> discord.Embed:
    """Create a blank interview embed template.

    Args:
        interviewee: Data about the person being interviewed
        asker_name: Display name of the person asking questions
        asker_avatar_url: Avatar URL for the asker

    Returns:
        A discord.Embed with title, description, thumbnail, and author set
    """
    embed = discord.Embed(
        title=f"**{interviewee.name}**'s interview",
        description=" ",  # Non-empty to avoid display issues
        color=interviewee.color,
    )
    embed.set_thumbnail(url=interviewee.avatar_url)
    embed.set_author(name=f"Asked by {asker_name}", icon_url=asker_avatar_url)
    return embed


def calculate_base_embed_length(
    interviewee: IntervieweeData,
    asker_name: str,
) -> int:
    """Calculate the character length used by embed metadata.

    This helps track how much room is left for fields.
    """
    title_len = len(f"**{interviewee.name}**'s interview")
    desc_len = 1  # Single space
    author_len = len(f"Asked by {asker_name}")
    # Add buffer for footer, URLs, etc.
    return title_len + desc_len + author_len + 100


def can_fit_simple_qa(
    question: QuestionData,
    current_length: int,
) -> bool:
    """Check if a Q&A pair can fit in a single field without chunking."""
    question_text = escape_markdown_links(question.question_text)
    lines = [line.strip() for line in question_text.split("\n")]
    # Account for "> " prefix and "\n" between lines, plus link syntax
    text_length = sum(len(line) for line in lines) + len(lines) * 3
    total_qa_length = text_length + len(question.answer_text) + len(question.jump_url) + 10

    if total_qa_length > SAFE_FIELD_VALUE:
        return False

    field_name = f"Question #{question.question_number}"
    field_value_estimate = total_qa_length + 20  # formatting overhead
    total_addition = len(field_name) + field_value_estimate

    return current_length + total_addition <= SAFE_EMBED_TOTAL


@dataclass
class AddQuestionOutput:
    """Result of adding a question to an embed."""

    result: AddQuestionResult
    chars_added: int
    images: list[ImageData]  # Images found in answer (for gallery embeds)


def add_question_to_embed(
    embed: discord.Embed,
    question: QuestionData,
    current_length: int,
) -> AddQuestionOutput:
    """Add a question and answer to an embed.

    Handles both simple (single-field) and complex (multi-field) cases.
    Extracts images from answer text and sets the first one on the embed.

    Args:
        embed: The embed to add fields to
        question: The question data to add
        current_length: Current character count of embed content

    Returns:
        AddQuestionOutput with result status, characters added, and extracted images.
        If result is EMBED_FULL, no fields were added and caller should try new embed.
        If result is QUESTION_TOO_LONG, the Q&A cannot fit in any embed.
    """
    # Extract images from answer before processing
    answer_text, images = extract_images_from_text(question.answer_text)

    # Check if this Q&A is too long for any embed (using cleaned text)
    total_qa_length = len(question.question_text) + len(answer_text)
    if total_qa_length > SAFE_EMBED_TOTAL - 200:  # Leave room for formatting
        return AddQuestionOutput(AddQuestionResult.QUESTION_TOO_LONG, 0, [])

    # Check if it would exceed current embed's remaining space
    if current_length + total_qa_length > SAFE_EMBED_TOTAL - 100:
        return AddQuestionOutput(AddQuestionResult.EMBED_FULL, 0, [])

    # Create modified question with cleaned answer text
    cleaned_question = QuestionData(
        question_number=question.question_number,
        asker_name=question.asker_name,
        asker_avatar_url=question.asker_avatar_url,
        question_text=question.question_text,
        answer_text=answer_text if answer_text else "(image)",
        jump_url=question.jump_url,
    )

    # Try simple case first: everything fits in one field
    if can_fit_simple_qa(cleaned_question, current_length):
        result, chars = _add_simple_qa(embed, cleaned_question)
    else:
        # Complex case: need to chunk across multiple fields
        result, chars = _add_chunked_qa(embed, cleaned_question, current_length)

    # Set first image on embed if present
    if result == AddQuestionResult.SUCCESS and images:
        embed.set_image(url=images[0].url)

    return AddQuestionOutput(result, chars, images)


def _add_simple_qa(
    embed: discord.Embed,
    question: QuestionData,
) -> tuple[AddQuestionResult, int]:
    """Add a Q&A that fits in a single field."""
    formatted_question = format_question_as_quote(question.question_text, question.jump_url)
    field_name = f"Question #{question.question_number}"
    field_value = f"{formatted_question}\n{question.answer_text}"

    embed.add_field(name=field_name, value=field_value, inline=False)
    return (AddQuestionResult.SUCCESS, len(field_name) + len(field_value))


def _add_chunked_qa(
    embed: discord.Embed,
    question: QuestionData,
    current_length: int,
) -> tuple[AddQuestionResult, int]:
    """Add a Q&A that needs to be split across multiple fields."""
    added_length = 0

    # Chunk the question with link in each chunk
    question_chunks = split_text_into_chunks(question.question_text, SAFE_FIELD_VALUE - 100)

    for i, chunk in enumerate(question_chunks):
        # Format as quote with link
        lines = [line.strip() for line in chunk.split("\n")]
        quote_block = "\n> ".join(lines)
        formatted_chunk = f"> [{quote_block}]({question.jump_url})"

        if len(question_chunks) > 1:
            name = f"Question #{question.question_number} [{i + 1}/{len(question_chunks)}]"
        else:
            name = f"Question #{question.question_number}"

        embed.add_field(name=name, value=formatted_chunk, inline=False)
        added_length += len(name) + len(formatted_chunk)

    # Chunk the answer
    answer_chunks = split_text_into_chunks(question.answer_text, SAFE_ANSWER_CHUNK)

    for i, chunk in enumerate(answer_chunks):
        if len(answer_chunks) > 1:
            name = f"Answer #{question.question_number} [{i + 1}/{len(answer_chunks)}]"
        else:
            name = f"Answer #{question.question_number}"

        embed.add_field(name=name, value=chunk, inline=False)
        added_length += len(name) + len(chunk)

    return (AddQuestionResult.SUCCESS, added_length)


def set_embed_footer(
    embed: discord.Embed,
    answered_count: int,
    total_count: int,
) -> None:
    """Set the footer showing question progress."""
    embed.set_footer(text=f"{answered_count} questions answered (of {total_count})")


@dataclass
class EmbedGenerationResult:
    """Result of generating embeds from a list of questions.

    embed_groups contains lists of embeds that should be sent together in
    a single message. This is required for Discord image galleries to work -
    multiple embeds with the same url field display as a gallery only when
    sent in the same message.
    """

    embed_groups: list[list[discord.Embed]]  # Groups of embeds to send together
    skipped_questions: list[QuestionData]  # Questions too long to embed


def create_gallery_embed(
    main_embed: discord.Embed,
    image: ImageData,
) -> discord.Embed:
    """Create an embed for additional images in a gallery.

    Discord shows multiple embeds as a gallery when they share the same `url` field.
    This creates a minimal embed with just an image and matching url.

    Args:
        main_embed: The main embed that this gallery image accompanies
        image: The image to display

    Returns:
        A minimal embed with the image set
    """
    embed = discord.Embed(
        # Use the same url as main embed to trigger gallery display
        url=main_embed.url if main_embed.url else "https://discord.com",
        color=main_embed.color,
    )
    embed.set_image(url=image.url)
    return embed


def generate_answer_embeds(
    interviewee: IntervieweeData,
    questions: list[QuestionData],
    prior_answered: int,
    total_asked: int,
) -> EmbedGenerationResult:
    """Generate a list of embeds from answered questions.

    Groups questions by asker and respects all Discord embed limits.
    Handles images in answers:
    - First image is displayed on the main embed
    - Additional images create gallery embeds (in same message for gallery display)
    - Answers with images force a new embed for subsequent questions

    Args:
        interviewee: Data about the person being interviewed
        questions: List of questions with answers to format
        prior_answered: Number of questions already answered before this batch
        total_asked: Total questions asked in the interview

    Returns:
        EmbedGenerationResult with embed_groups (lists of embeds to send together)
        and any skipped questions
    """
    if not questions:
        return EmbedGenerationResult(embed_groups=[], skipped_questions=[])

    embed_groups: list[list[discord.Embed]] = []
    skipped: list[QuestionData] = []
    current_embed: discord.Embed | None = None
    current_length = 0
    current_asker: str | None = None
    answered_in_batch = 0
    force_new_embed = False  # Set after image answers

    def finalize_embed(embed: discord.Embed, gallery_images: list[ImageData] | None = None) -> None:
        """Add footer, append to results as a group with any gallery embeds."""
        set_embed_footer(
            embed,
            prior_answered + answered_in_batch,
            total_asked,
        )

        # Create a group: main embed + any gallery embeds (must be sent together)
        group: list[discord.Embed] = [embed]

        # Create additional embeds for gallery images (beyond the first)
        if gallery_images and len(gallery_images) > 1:
            for img in gallery_images[1:]:
                gallery_embed = create_gallery_embed(embed, img)
                group.append(gallery_embed)

        embed_groups.append(group)

    def start_new_embed(question: QuestionData) -> discord.Embed:
        """Create a fresh embed for a new asker."""
        nonlocal current_length
        embed = create_blank_embed(
            interviewee,
            question.asker_name,
            question.asker_avatar_url,
        )
        # Set a url so gallery embeds can match it
        embed.url = "https://discord.com"
        current_length = calculate_base_embed_length(interviewee, question.asker_name)
        return embed

    pending_images: list[ImageData] = []

    for question in questions:
        # New embed needed if: different asker, too many fields, or after an image answer
        needs_new_embed = (
            current_asker != question.asker_name
            or current_embed is None
            or len(current_embed.fields) >= SAFE_FIELDS_PER_EMBED
            or force_new_embed
        )

        if needs_new_embed:
            if current_embed is not None and len(current_embed.fields) > 0:
                finalize_embed(current_embed, pending_images)
                pending_images = []
            current_embed = start_new_embed(question)
            current_asker = question.asker_name
            force_new_embed = False

        # Try to add the question
        output = add_question_to_embed(current_embed, question, current_length)

        if output.result == AddQuestionResult.EMBED_FULL:
            # Finalize current and start fresh
            if len(current_embed.fields) > 0:
                finalize_embed(current_embed, pending_images)
                pending_images = []
            current_embed = start_new_embed(question)
            output = add_question_to_embed(current_embed, question, current_length)

        if output.result == AddQuestionResult.QUESTION_TOO_LONG:
            skipped.append(question)
        else:
            current_length += output.chars_added
            answered_in_batch += 1
            current_asker = question.asker_name

            # If this answer had images, track them and force new embed for next Q&A
            if output.images:
                pending_images = output.images
                force_new_embed = True

    # Don't forget the last embed
    if current_embed is not None and len(current_embed.fields) > 0:
        finalize_embed(current_embed, pending_images)

    return EmbedGenerationResult(embed_groups=embed_groups, skipped_questions=skipped)
