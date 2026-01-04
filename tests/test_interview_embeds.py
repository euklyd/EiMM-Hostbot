"""Tests for interview embed generation logic.

These tests are independent of Discord - they test the pure logic
of text processing and embed generation.
"""

from cogs.interview.embeds import (
    SAFE_EMBED_TOTAL,
    SAFE_FIELDS_PER_EMBED,
    AddQuestionResult,
    IntervieweeData,
    QuestionData,
    add_question_to_embed,
    calculate_base_embed_length,
    can_fit_simple_qa,
    create_blank_embed,
    escape_markdown_links,
    format_question_as_quote,
    generate_answer_embeds,
    set_embed_footer,
    split_text_into_chunks,
)


class TestEscapeMarkdownLinks:
    """Tests for escape_markdown_links()."""

    def test_escapes_brackets(self) -> None:
        """Square brackets should be escaped."""
        assert escape_markdown_links("[test]") == "\\[test\\]"

    def test_multiple_brackets(self) -> None:
        """Multiple brackets are all escaped."""
        assert escape_markdown_links("[a][b]") == "\\[a\\]\\[b\\]"

    def test_no_brackets(self) -> None:
        """Text without brackets passes through unchanged."""
        assert escape_markdown_links("hello world") == "hello world"

    def test_nested_brackets(self) -> None:
        """Nested brackets are handled."""
        assert escape_markdown_links("[[test]]") == "\\[\\[test\\]\\]"


class TestSplitTextIntoChunks:
    """Tests for split_text_into_chunks()."""

    def test_short_text_single_chunk(self) -> None:
        """Short text returns as single chunk."""
        result = split_text_into_chunks("hello world", 100)
        assert result == ["hello world"]

    def test_empty_text(self) -> None:
        """Empty text returns single empty chunk."""
        result = split_text_into_chunks("", 100)
        assert result == [""]

    def test_splits_on_word_boundary(self) -> None:
        """Text splits on word boundaries."""
        result = split_text_into_chunks("hello world foo", 10)
        # "hello" = 5, "world" = 5, "foo" = 3
        assert len(result) >= 2
        # First chunk should not cut mid-word
        assert "hell" not in result[0] or result[0].endswith("hello")

    def test_long_word_force_split(self) -> None:
        """Words longer than max are force-split."""
        long_word = "a" * 150
        result = split_text_into_chunks(long_word, 100)
        assert len(result) == 2
        assert result[0] == "a" * 100
        assert result[1] == "a" * 50

    def test_preserves_all_content(self) -> None:
        """Splitting preserves all original content."""
        text = "the quick brown fox jumps over the lazy dog"
        result = split_text_into_chunks(text, 15)
        rejoined = " ".join(result)
        assert rejoined == text

    def test_escapes_brackets_in_chunks(self) -> None:
        """Brackets are escaped before chunking."""
        text = "[test] message"
        result = split_text_into_chunks(text, 100)
        assert "\\[test\\]" in result[0]


class TestFormatQuestionAsQuote:
    """Tests for format_question_as_quote()."""

    def test_single_line(self) -> None:
        """Single line question formats correctly."""
        result = format_question_as_quote("What is your favorite color?", "http://example.com")
        assert result.startswith("> [")
        assert "](http://example.com)" in result

    def test_multi_line(self) -> None:
        """Multi-line question has quote prefix on each line."""
        result = format_question_as_quote("Line one\nLine two", "http://example.com")
        assert "> " in result
        assert "\n> " in result  # Second line gets prefix

    def test_escapes_brackets_in_question(self) -> None:
        """Brackets in question text are escaped."""
        result = format_question_as_quote("What [thing] do you like?", "http://example.com")
        assert "\\[thing\\]" in result


class TestCreateBlankEmbed:
    """Tests for create_blank_embed()."""

    def test_creates_embed_with_title(self) -> None:
        """Embed has correct title."""
        interviewee = IntervieweeData(name="TestUser", color=0xFF0000, avatar_url="http://avatar.url")
        embed = create_blank_embed(interviewee, "AskerName", "http://asker.url")
        assert "TestUser" in embed.title
        assert "interview" in embed.title.lower()

    def test_embed_has_author(self) -> None:
        """Embed has author set to asker."""
        interviewee = IntervieweeData(name="TestUser", color=0xFF0000, avatar_url="http://avatar.url")
        embed = create_blank_embed(interviewee, "AskerName", "http://asker.url")
        assert embed.author is not None
        assert "AskerName" in embed.author.name

    def test_embed_has_color(self) -> None:
        """Embed uses interviewee's color."""
        interviewee = IntervieweeData(name="TestUser", color=0xFF0000, avatar_url="http://avatar.url")
        embed = create_blank_embed(interviewee, "AskerName", "http://asker.url")
        assert embed.color.value == 0xFF0000

    def test_embed_has_thumbnail(self) -> None:
        """Embed has interviewee's avatar as thumbnail."""
        interviewee = IntervieweeData(name="TestUser", color=0xFF0000, avatar_url="http://avatar.url")
        embed = create_blank_embed(interviewee, "AskerName", "http://asker.url")
        assert embed.thumbnail is not None
        assert embed.thumbnail.url == "http://avatar.url"


class TestCalculateBaseEmbedLength:
    """Tests for calculate_base_embed_length()."""

    def test_returns_positive_int(self) -> None:
        """Returns a positive integer."""
        interviewee = IntervieweeData(name="TestUser", color=0, avatar_url="")
        length = calculate_base_embed_length(interviewee, "Asker")
        assert length > 0
        assert isinstance(length, int)

    def test_longer_names_increase_length(self) -> None:
        """Longer names result in larger length calculation."""
        short = IntervieweeData(name="A", color=0, avatar_url="")
        long = IntervieweeData(name="A" * 50, color=0, avatar_url="")
        short_len = calculate_base_embed_length(short, "B")
        long_len = calculate_base_embed_length(long, "B")
        assert long_len > short_len


class TestCanFitSimpleQA:
    """Tests for can_fit_simple_qa()."""

    def test_short_qa_fits(self) -> None:
        """Short Q&A fits in a single field."""
        question = QuestionData(
            question_number=1,
            asker_name="Asker",
            asker_avatar_url="http://example.com",
            question_text="What's your favorite color?",
            answer_text="Blue!",
            jump_url="http://discord.com/channels/1/2/3",
        )
        assert can_fit_simple_qa(question, current_length=0) is True

    def test_long_answer_does_not_fit(self) -> None:
        """Long answer doesn't fit in single field."""
        question = QuestionData(
            question_number=1,
            asker_name="Asker",
            asker_avatar_url="http://example.com",
            question_text="Question?",
            answer_text="A" * 2000,  # Very long answer
            jump_url="http://discord.com/channels/1/2/3",
        )
        assert can_fit_simple_qa(question, current_length=0) is False

    def test_already_full_embed_returns_false(self) -> None:
        """When embed is nearly full, returns False."""
        question = QuestionData(
            question_number=1,
            asker_name="Asker",
            asker_avatar_url="http://example.com",
            question_text="Question?",
            answer_text="Answer!",
            jump_url="http://discord.com/channels/1/2/3",
        )
        # Embed is almost at limit
        assert can_fit_simple_qa(question, current_length=SAFE_EMBED_TOTAL - 10) is False


class TestAddQuestionToEmbed:
    """Tests for add_question_to_embed()."""

    def test_adds_simple_question(self) -> None:
        """Simple Q&A is added successfully."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        embed = create_blank_embed(interviewee, "Asker", "http://asker.url")
        question = QuestionData(
            question_number=1,
            asker_name="Asker",
            asker_avatar_url="http://asker.url",
            question_text="What's your name?",
            answer_text="Test!",
            jump_url="http://discord.com/channels/1/2/3",
        )
        result, added = add_question_to_embed(embed, question, current_length=0)
        assert result == AddQuestionResult.SUCCESS
        assert added > 0
        assert len(embed.fields) >= 1

    def test_returns_embed_full_when_no_space(self) -> None:
        """Returns EMBED_FULL when content won't fit."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        embed = create_blank_embed(interviewee, "Asker", "http://asker.url")
        question = QuestionData(
            question_number=1,
            asker_name="Asker",
            asker_avatar_url="http://asker.url",
            question_text="Question?",
            answer_text="Answer",
            jump_url="http://discord.com/channels/1/2/3",
        )
        # Pretend embed is almost full
        result, added = add_question_to_embed(embed, question, current_length=SAFE_EMBED_TOTAL - 50)
        assert result == AddQuestionResult.EMBED_FULL
        assert added == 0

    def test_returns_too_long_for_massive_qa(self) -> None:
        """Returns QUESTION_TOO_LONG for impossibly large Q&A."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        embed = create_blank_embed(interviewee, "Asker", "http://asker.url")
        question = QuestionData(
            question_number=1,
            asker_name="Asker",
            asker_avatar_url="http://asker.url",
            question_text="Q" * 3000,
            answer_text="A" * 3000,  # Total > safe limit
            jump_url="http://discord.com/channels/1/2/3",
        )
        result, added = add_question_to_embed(embed, question, current_length=0)
        assert result == AddQuestionResult.QUESTION_TOO_LONG
        assert added == 0

    def test_chunks_long_question(self) -> None:
        """Long question is split across multiple fields."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        embed = create_blank_embed(interviewee, "Asker", "http://asker.url")
        question = QuestionData(
            question_number=1,
            asker_name="Asker",
            asker_avatar_url="http://asker.url",
            question_text="Q " * 500,  # Long question
            answer_text="Short answer",
            jump_url="http://discord.com/channels/1/2/3",
        )
        result, added = add_question_to_embed(embed, question, current_length=0)
        assert result == AddQuestionResult.SUCCESS
        # Should have multiple fields due to chunking
        assert len(embed.fields) > 1


class TestSetEmbedFooter:
    """Tests for set_embed_footer()."""

    def test_sets_footer_text(self) -> None:
        """Footer contains answered and total counts."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        embed = create_blank_embed(interviewee, "Asker", "http://asker.url")
        set_embed_footer(embed, answered_count=5, total_count=10)
        assert embed.footer is not None
        assert "5" in embed.footer.text
        assert "10" in embed.footer.text


class TestGenerateAnswerEmbeds:
    """Tests for generate_answer_embeds()."""

    def test_empty_questions_returns_empty(self) -> None:
        """No questions returns empty result."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        result = generate_answer_embeds(interviewee, [], prior_answered=0, total_asked=0)
        assert result.embeds == []
        assert result.skipped_questions == []

    def test_single_question_single_embed(self) -> None:
        """Single question produces single embed."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        questions = [
            QuestionData(
                question_number=1,
                asker_name="Asker",
                asker_avatar_url="http://asker.url",
                question_text="Question?",
                answer_text="Answer!",
                jump_url="http://discord.com/channels/1/2/3",
            )
        ]
        result = generate_answer_embeds(interviewee, questions, prior_answered=0, total_asked=1)
        assert len(result.embeds) == 1
        assert len(result.skipped_questions) == 0

    def test_new_asker_starts_new_embed(self) -> None:
        """Different asker triggers new embed."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        questions = [
            QuestionData(
                question_number=1,
                asker_name="Asker1",
                asker_avatar_url="http://asker1.url",
                question_text="Q1?",
                answer_text="A1!",
                jump_url="http://discord.com/channels/1/2/3",
            ),
            QuestionData(
                question_number=2,
                asker_name="Asker2",  # Different asker
                asker_avatar_url="http://asker2.url",
                question_text="Q2?",
                answer_text="A2!",
                jump_url="http://discord.com/channels/1/2/4",
            ),
        ]
        result = generate_answer_embeds(interviewee, questions, prior_answered=0, total_asked=2)
        assert len(result.embeds) == 2
        # First embed should be from Asker1, second from Asker2
        assert "Asker1" in result.embeds[0].author.name
        assert "Asker2" in result.embeds[1].author.name

    def test_same_asker_same_embed(self) -> None:
        """Same asker's questions go in same embed."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        questions = [
            QuestionData(
                question_number=1,
                asker_name="Asker",
                asker_avatar_url="http://asker.url",
                question_text="Q1?",
                answer_text="A1!",
                jump_url="http://discord.com/channels/1/2/3",
            ),
            QuestionData(
                question_number=2,
                asker_name="Asker",  # Same asker
                asker_avatar_url="http://asker.url",
                question_text="Q2?",
                answer_text="A2!",
                jump_url="http://discord.com/channels/1/2/4",
            ),
        ]
        result = generate_answer_embeds(interviewee, questions, prior_answered=0, total_asked=2)
        # Both questions should be in same embed (same asker)
        assert len(result.embeds) == 1
        assert len(result.embeds[0].fields) >= 2

    def test_too_long_question_is_skipped(self) -> None:
        """Questions too long to embed are added to skipped list."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        questions = [
            QuestionData(
                question_number=1,
                asker_name="Asker",
                asker_avatar_url="http://asker.url",
                question_text="Q" * 3000,
                answer_text="A" * 3000,  # Way too long
                jump_url="http://discord.com/channels/1/2/3",
            ),
        ]
        result = generate_answer_embeds(interviewee, questions, prior_answered=0, total_asked=1)
        assert len(result.embeds) == 0
        assert len(result.skipped_questions) == 1

    def test_footer_shows_correct_counts(self) -> None:
        """Embed footers show correct answered/total counts."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        questions = [
            QuestionData(
                question_number=1,
                asker_name="Asker",
                asker_avatar_url="http://asker.url",
                question_text="Question?",
                answer_text="Answer!",
                jump_url="http://discord.com/channels/1/2/3",
            )
        ]
        result = generate_answer_embeds(interviewee, questions, prior_answered=5, total_asked=10)
        # Should show 6 answered (5 prior + 1 in batch) of 10
        assert "6" in result.embeds[0].footer.text
        assert "10" in result.embeds[0].footer.text

    def test_many_fields_triggers_new_embed(self) -> None:
        """Exceeding field limit starts new embed."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        # Create enough questions to exceed SAFE_FIELDS_PER_EMBED
        questions = [
            QuestionData(
                question_number=i,
                asker_name="Asker",
                asker_avatar_url="http://asker.url",
                question_text=f"Q{i}?",
                answer_text=f"A{i}!",
                jump_url=f"http://discord.com/channels/1/2/{i}",
            )
            for i in range(1, SAFE_FIELDS_PER_EMBED + 5)
        ]
        result = generate_answer_embeds(interviewee, questions, prior_answered=0, total_asked=len(questions))
        # Should have more than one embed due to field limit
        assert len(result.embeds) > 1
