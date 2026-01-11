"""Tests for interview embed generation logic.

These tests are independent of Discord - they test the pure logic
of text processing and embed generation.
"""

from cogs.interview.embeds import (
    EMBED_FIELD_VALUE_LIMIT,
    SAFE_ANSWER_CHUNK,
    SAFE_EMBED_TOTAL,
    SAFE_FIELD_VALUE,
    SAFE_FIELDS_PER_EMBED,
    AddQuestionResult,
    ImageData,
    IntervieweeData,
    QuestionData,
    add_question_to_embed,
    calculate_base_embed_length,
    can_fit_simple_qa,
    create_blank_embed,
    create_gallery_embed,
    escape_markdown_links,
    extract_images_from_text,
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
        output = add_question_to_embed(embed, question, current_length=0)
        assert output.result == AddQuestionResult.SUCCESS
        assert output.chars_added > 0
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
        output = add_question_to_embed(embed, question, current_length=SAFE_EMBED_TOTAL - 50)
        assert output.result == AddQuestionResult.EMBED_FULL
        assert output.chars_added == 0

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
        output = add_question_to_embed(embed, question, current_length=0)
        assert output.result == AddQuestionResult.QUESTION_TOO_LONG
        assert output.chars_added == 0

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
        output = add_question_to_embed(embed, question, current_length=0)
        assert output.result == AddQuestionResult.SUCCESS
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
        assert result.embed_groups == []
        assert result.skipped_questions == []

    def test_single_question_single_embed(self) -> None:
        """Single question produces single embed group."""
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
        assert len(result.embed_groups) == 1
        assert len(result.embed_groups[0]) == 1  # Single embed in the group
        assert len(result.skipped_questions) == 0

    def test_new_asker_starts_new_embed(self) -> None:
        """Different asker triggers new embed group."""
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
        assert len(result.embed_groups) == 2
        # First embed should be from Asker1, second from Asker2
        assert "Asker1" in result.embed_groups[0][0].author.name
        assert "Asker2" in result.embed_groups[1][0].author.name

    def test_same_asker_same_embed(self) -> None:
        """Same asker's questions go in same embed group."""
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
        # Both questions should be in same embed group (same asker)
        assert len(result.embed_groups) == 1
        assert len(result.embed_groups[0][0].fields) >= 2

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
        assert len(result.embed_groups) == 0
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
        assert "6" in result.embed_groups[0][0].footer.text
        assert "10" in result.embed_groups[0][0].footer.text

    def test_many_fields_triggers_new_embed(self) -> None:
        """Exceeding field limit starts new embed group."""
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
        # Should have more than one embed group due to field limit
        assert len(result.embed_groups) > 1


# =============================================================================
# Image Extraction Tests
# =============================================================================


class TestExtractImagesFromText:
    """Tests for extract_images_from_text()."""

    def test_no_images(self) -> None:
        """Text without images returns unchanged."""
        text = "Just some regular text with no images."
        cleaned, images = extract_images_from_text(text)
        assert cleaned == text
        assert images == []

    def test_single_image_url(self) -> None:
        """Single image URL on its own line is extracted."""
        text = "Here's my answer!\n\nhttps://example.com/image.png"
        cleaned, images = extract_images_from_text(text)
        assert "https://example.com/image.png" not in cleaned
        assert len(images) == 1
        assert images[0].url == "https://example.com/image.png"

    def test_multiple_image_urls(self) -> None:
        """Multiple image URLs are all extracted."""
        text = "Answer text\n\nhttps://example.com/a.png\nhttps://example.com/b.jpg"
        cleaned, images = extract_images_from_text(text)
        assert len(images) == 2
        assert images[0].url == "https://example.com/a.png"
        assert images[1].url == "https://example.com/b.jpg"

    def test_image_with_query_string(self) -> None:
        """Image URLs with query strings are extracted."""
        text = "https://imgur.com/abc123.png?1"
        cleaned, images = extract_images_from_text(text)
        assert len(images) == 1
        assert images[0].url == "https://imgur.com/abc123.png?1"

    def test_various_image_extensions(self) -> None:
        """Different image extensions are recognized."""
        extensions = ["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"]
        for ext in extensions:
            text = f"https://example.com/image.{ext}"
            _, images = extract_images_from_text(text)
            assert len(images) == 1, f"Failed for .{ext}"

    def test_case_insensitive_extension(self) -> None:
        """Image extensions are case-insensitive."""
        text = "https://example.com/IMAGE.PNG"
        _, images = extract_images_from_text(text)
        assert len(images) == 1

    def test_inline_url_not_extracted(self) -> None:
        """URLs inline with other text are NOT extracted."""
        text = "Check out https://example.com/image.png for more"
        cleaned, images = extract_images_from_text(text)
        assert len(images) == 0
        assert "https://example.com/image.png" in cleaned

    def test_only_images_returns_empty_text(self) -> None:
        """Answer with only images returns empty cleaned text."""
        text = "https://example.com/a.png\nhttps://example.com/b.png"
        cleaned, images = extract_images_from_text(text)
        assert cleaned == ""
        assert len(images) == 2

    def test_preserves_text_around_images(self) -> None:
        """Text before and after images is preserved."""
        text = "Before text\n\nhttps://example.com/img.png\n\nAfter text"
        cleaned, images = extract_images_from_text(text)
        assert "Before text" in cleaned
        assert "After text" in cleaned
        assert len(images) == 1

    def test_cleans_extra_whitespace(self) -> None:
        """Extra blank lines from removed images are cleaned up."""
        text = "Text\n\n\nhttps://example.com/img.png\n\n\nMore text"
        cleaned, images = extract_images_from_text(text)
        # Should not have triple newlines
        assert "\n\n\n" not in cleaned


class TestCreateGalleryEmbed:
    """Tests for create_gallery_embed()."""

    def test_gallery_embed_has_same_url(self) -> None:
        """Gallery embed matches main embed's URL for gallery display."""
        interviewee = IntervieweeData(name="Test", color=0xFF0000, avatar_url="http://avatar.url")
        main_embed = create_blank_embed(interviewee, "Asker", "http://asker.url")
        main_embed.url = "https://discord.com"

        image = ImageData(alt="", url="https://example.com/image.png")
        gallery_embed = create_gallery_embed(main_embed, image)

        assert gallery_embed.url == main_embed.url

    def test_gallery_embed_has_same_color(self) -> None:
        """Gallery embed inherits main embed's color."""
        interviewee = IntervieweeData(name="Test", color=0xFF0000, avatar_url="http://avatar.url")
        main_embed = create_blank_embed(interviewee, "Asker", "http://asker.url")

        image = ImageData(alt="", url="https://example.com/image.png")
        gallery_embed = create_gallery_embed(main_embed, image)

        assert gallery_embed.color == main_embed.color

    def test_gallery_embed_has_image(self) -> None:
        """Gallery embed has the image set."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        main_embed = create_blank_embed(interviewee, "Asker", "http://asker.url")

        image = ImageData(alt="", url="https://example.com/image.png")
        gallery_embed = create_gallery_embed(main_embed, image)

        assert gallery_embed.image is not None
        assert gallery_embed.image.url == "https://example.com/image.png"


# =============================================================================
# Image Gallery Integration Tests
# =============================================================================


class TestImageGalleryEmbeds:
    """Tests for image handling in embed generation."""

    def _make_question_with_images(self, num_images: int, text: str = "Answer") -> QuestionData:
        """Helper to create a question with N image URLs in the answer."""
        image_urls = "\n".join(
            f"https://example.com/img{i}.png" for i in range(1, num_images + 1)
        )
        answer = f"{text}\n\n{image_urls}" if text else image_urls
        return QuestionData(
            question_number=1,
            asker_name="Asker",
            asker_avatar_url="http://asker.url",
            question_text="Question?",
            answer_text=answer,
            jump_url="http://discord.com/channels/1/2/3",
        )

    def test_single_image_on_main_embed(self) -> None:
        """Single image is set on the main embed."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        questions = [self._make_question_with_images(1)]

        result = generate_answer_embeds(interviewee, questions, prior_answered=0, total_asked=1)

        assert len(result.embed_groups) == 1
        assert len(result.embed_groups[0]) == 1  # Just main embed, no gallery
        assert result.embed_groups[0][0].image is not None

    def test_two_images_creates_gallery(self) -> None:
        """Two images creates main embed + 1 gallery embed."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        questions = [self._make_question_with_images(2)]

        result = generate_answer_embeds(interviewee, questions, prior_answered=0, total_asked=1)

        assert len(result.embed_groups) == 1
        assert len(result.embed_groups[0]) == 2  # Main + 1 gallery

    def test_four_images_creates_gallery(self) -> None:
        """Four images creates main embed + 3 gallery embeds."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        questions = [self._make_question_with_images(4)]

        result = generate_answer_embeds(interviewee, questions, prior_answered=0, total_asked=1)

        assert len(result.embed_groups) == 1
        assert len(result.embed_groups[0]) == 4  # Main + 3 gallery

    def test_ten_images_max_gallery(self) -> None:
        """Ten images creates full gallery (main + 9 gallery embeds)."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        questions = [self._make_question_with_images(10)]

        result = generate_answer_embeds(interviewee, questions, prior_answered=0, total_asked=1)

        assert len(result.embed_groups) == 1
        assert len(result.embed_groups[0]) == 10  # Main + 9 gallery

    def test_eleven_images_limited_to_ten(self) -> None:
        """More than 10 images are limited to 10 embeds."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        questions = [self._make_question_with_images(15)]

        result = generate_answer_embeds(interviewee, questions, prior_answered=0, total_asked=1)

        assert len(result.embed_groups) == 1
        # Should be capped at 10 total embeds
        assert len(result.embed_groups[0]) == 10

    def test_image_answer_forces_new_embed(self) -> None:
        """Answer with images forces next Q&A into new embed."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        questions = [
            self._make_question_with_images(1),
            QuestionData(
                question_number=2,
                asker_name="Asker",  # Same asker
                asker_avatar_url="http://asker.url",
                question_text="Q2?",
                answer_text="A2 without images",
                jump_url="http://discord.com/channels/1/2/4",
            ),
        ]

        result = generate_answer_embeds(interviewee, questions, prior_answered=0, total_asked=2)

        # Should be 2 embed groups even though same asker
        assert len(result.embed_groups) == 2

    def test_only_image_answer_shows_placeholder(self) -> None:
        """Answer with only images shows (image) placeholder."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        embed = create_blank_embed(interviewee, "Asker", "http://asker.url")

        question = QuestionData(
            question_number=1,
            asker_name="Asker",
            asker_avatar_url="http://asker.url",
            question_text="Question?",
            answer_text="https://example.com/img.png",  # Only an image
            jump_url="http://discord.com/channels/1/2/3",
        )

        output = add_question_to_embed(embed, question, current_length=0)

        assert output.result == AddQuestionResult.SUCCESS
        # The field should contain "(image)" as placeholder
        field_values = [f.value for f in embed.fields]
        assert any("(image)" in v for v in field_values)


# =============================================================================
# Footer Tests with Images
# =============================================================================


class TestEmbedFooterWithImages:
    """Tests for embed footer with image counts."""

    def test_footer_no_extra_images(self) -> None:
        """Footer with <=4 images shows no extra message."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        embed = create_blank_embed(interviewee, "Asker", "http://asker.url")

        set_embed_footer(embed, answered_count=1, total_count=5, extra_images=0)

        assert "more" not in embed.footer.text.lower()
        assert "click" not in embed.footer.text.lower()

    def test_footer_with_extra_preview_images(self) -> None:
        """Footer shows click message when 5-10 images."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        embed = create_blank_embed(interviewee, "Asker", "http://asker.url")

        set_embed_footer(embed, answered_count=1, total_count=5, extra_images=3)

        assert "+3 more" in embed.footer.text
        assert "click images to view all" in embed.footer.text

    def test_footer_with_dropped_images(self) -> None:
        """Footer shows warning when images exceed limit."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        embed = create_blank_embed(interviewee, "Asker", "http://asker.url")

        set_embed_footer(embed, answered_count=1, total_count=5, extra_images=6, dropped_images=2)

        assert "2 images not shown" in embed.footer.text
        assert "limit 10" in embed.footer.text

    def test_footer_with_single_dropped_image(self) -> None:
        """Footer uses singular 'image' for 1 dropped."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        embed = create_blank_embed(interviewee, "Asker", "http://asker.url")

        set_embed_footer(embed, answered_count=1, total_count=5, extra_images=6, dropped_images=1)

        assert "1 image not shown" in embed.footer.text
        assert "1 images" not in embed.footer.text  # Should be singular


# =============================================================================
# Field and Character Limit Edge Cases
# =============================================================================


class TestFieldLimitEdgeCases:
    """Tests for embed field character limit edge cases."""

    def test_answer_at_field_value_limit(self) -> None:
        """Answer exactly at field value limit fits in single field."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        embed = create_blank_embed(interviewee, "Asker", "http://asker.url")

        # Create answer close to but under SAFE_FIELD_VALUE
        answer_text = "A" * (SAFE_FIELD_VALUE - 100)  # Leave room for question formatting

        question = QuestionData(
            question_number=1,
            asker_name="Asker",
            asker_avatar_url="http://asker.url",
            question_text="Q?",
            answer_text=answer_text,
            jump_url="http://discord.com/channels/1/2/3",
        )

        output = add_question_to_embed(embed, question, current_length=0)

        assert output.result == AddQuestionResult.SUCCESS

    def test_answer_over_field_limit_chunks(self) -> None:
        """Answer over field limit is chunked into multiple fields."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        embed = create_blank_embed(interviewee, "Asker", "http://asker.url")

        # Create answer that definitely needs chunking
        answer_text = "Word " * 300  # ~1500 chars

        question = QuestionData(
            question_number=1,
            asker_name="Asker",
            asker_avatar_url="http://asker.url",
            question_text="Q?",
            answer_text=answer_text,
            jump_url="http://discord.com/channels/1/2/3",
        )

        output = add_question_to_embed(embed, question, current_length=0)

        assert output.result == AddQuestionResult.SUCCESS
        # Should have multiple fields due to chunking
        assert len(embed.fields) > 1

    def test_long_question_chunks(self) -> None:
        """Long question is chunked across multiple fields."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        embed = create_blank_embed(interviewee, "Asker", "http://asker.url")

        # Long question that needs chunking
        question_text = "Word " * 250  # ~1250 chars

        question = QuestionData(
            question_number=1,
            asker_name="Asker",
            asker_avatar_url="http://asker.url",
            question_text=question_text,
            answer_text="Short answer",
            jump_url="http://discord.com/channels/1/2/3",
        )

        output = add_question_to_embed(embed, question, current_length=0)

        assert output.result == AddQuestionResult.SUCCESS
        # Check for chunked field names like "Question #1 [1/2]"
        field_names = [f.name for f in embed.fields]
        assert any("[1/" in name for name in field_names)

    def test_both_question_and_answer_long(self) -> None:
        """Both long question and answer are properly chunked."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        embed = create_blank_embed(interviewee, "Asker", "http://asker.url")

        question = QuestionData(
            question_number=1,
            asker_name="Asker",
            asker_avatar_url="http://asker.url",
            question_text="Q " * 200,  # ~400 chars
            answer_text="A " * 600,  # ~1200 chars
            jump_url="http://discord.com/channels/1/2/3",
        )

        output = add_question_to_embed(embed, question, current_length=0)

        assert output.result == AddQuestionResult.SUCCESS
        # Should have question and answer fields
        field_names = [f.name for f in embed.fields]
        assert any("Question" in name for name in field_names)
        assert any("Answer" in name for name in field_names)


class TestTotalEmbedLimitEdgeCases:
    """Tests for total embed character limit edge cases."""

    def test_embed_fills_to_capacity(self) -> None:
        """Multiple Q&As fill embed until capacity."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")

        # Create several medium-length questions
        questions = [
            QuestionData(
                question_number=i,
                asker_name="Asker",
                asker_avatar_url="http://asker.url",
                question_text=f"Question number {i} with some content?",
                answer_text=f"Answer {i} " * 50,  # ~300 chars each
                jump_url=f"http://discord.com/channels/1/2/{i}",
            )
            for i in range(1, 20)
        ]

        result = generate_answer_embeds(interviewee, questions, prior_answered=0, total_asked=20)

        # Should need multiple embeds due to total char limit
        assert len(result.embed_groups) >= 2

    def test_qa_exactly_at_remaining_space(self) -> None:
        """Q&A that exactly fits remaining space succeeds."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        embed = create_blank_embed(interviewee, "Asker", "http://asker.url")

        # Small question that should fit even with limited remaining space
        question = QuestionData(
            question_number=1,
            asker_name="Asker",
            asker_avatar_url="http://asker.url",
            question_text="Q?",
            answer_text="A!",
            jump_url="http://discord.com/channels/1/2/3",
        )

        # Set current_length to leave just enough room
        output = add_question_to_embed(embed, question, current_length=SAFE_EMBED_TOTAL - 500)

        assert output.result == AddQuestionResult.SUCCESS

    def test_qa_just_over_remaining_space(self) -> None:
        """Q&A just over remaining space returns EMBED_FULL."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")
        embed = create_blank_embed(interviewee, "Asker", "http://asker.url")

        question = QuestionData(
            question_number=1,
            asker_name="Asker",
            asker_avatar_url="http://asker.url",
            question_text="Question with some content?",
            answer_text="Answer with content!",
            jump_url="http://discord.com/channels/1/2/3",
        )

        # Set current_length to leave very little room
        output = add_question_to_embed(embed, question, current_length=SAFE_EMBED_TOTAL - 20)

        assert output.result == AddQuestionResult.EMBED_FULL


# =============================================================================
# Mixed Scenario Tests
# =============================================================================


class TestMixedScenarios:
    """Tests for complex mixed scenarios."""

    def test_images_long_text_multiple_askers(self) -> None:
        """Complex scenario with images, long text, and asker changes."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")

        questions = [
            # Asker1 with image
            QuestionData(
                question_number=1,
                asker_name="Asker1",
                asker_avatar_url="http://asker1.url",
                question_text="Q1?",
                answer_text="Answer 1\n\nhttps://example.com/img1.png",
                jump_url="http://discord.com/channels/1/2/1",
            ),
            # Asker1 again (but should be new embed due to image)
            QuestionData(
                question_number=2,
                asker_name="Asker1",
                asker_avatar_url="http://asker1.url",
                question_text="Q2?",
                answer_text="Answer 2 without image",
                jump_url="http://discord.com/channels/1/2/2",
            ),
            # Asker2 with long answer
            QuestionData(
                question_number=3,
                asker_name="Asker2",
                asker_avatar_url="http://asker2.url",
                question_text="Q3?",
                answer_text="Long " * 300,
                jump_url="http://discord.com/channels/1/2/3",
            ),
        ]

        result = generate_answer_embeds(interviewee, questions, prior_answered=0, total_asked=3)

        # Should have 3 embed groups:
        # 1. Asker1 Q1 with image
        # 2. Asker1 Q2 (forced new due to previous image)
        # 3. Asker2 Q3
        assert len(result.embed_groups) == 3
        assert len(result.skipped_questions) == 0

    def test_alternating_askers_with_images(self) -> None:
        """Alternating askers each with images."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")

        questions = [
            QuestionData(
                question_number=1,
                asker_name="Asker1",
                asker_avatar_url="http://asker1.url",
                question_text="Q1?",
                answer_text="A1\n\nhttps://example.com/a.png\nhttps://example.com/b.png",
                jump_url="http://discord.com/channels/1/2/1",
            ),
            QuestionData(
                question_number=2,
                asker_name="Asker2",
                asker_avatar_url="http://asker2.url",
                question_text="Q2?",
                answer_text="A2\n\nhttps://example.com/c.png",
                jump_url="http://discord.com/channels/1/2/2",
            ),
        ]

        result = generate_answer_embeds(interviewee, questions, prior_answered=0, total_asked=2)

        assert len(result.embed_groups) == 2
        # First group should have 2 embeds (main + 1 gallery)
        assert len(result.embed_groups[0]) == 2
        # Second group should have 1 embed (main with image)
        assert len(result.embed_groups[1]) == 1

    def test_skipped_question_mixed_with_valid(self) -> None:
        """Oversized question is skipped while others succeed."""
        interviewee = IntervieweeData(name="Test", color=0, avatar_url="http://avatar.url")

        questions = [
            QuestionData(
                question_number=1,
                asker_name="Asker",
                asker_avatar_url="http://asker.url",
                question_text="Q1?",
                answer_text="A1!",
                jump_url="http://discord.com/channels/1/2/1",
            ),
            QuestionData(
                question_number=2,
                asker_name="Asker",
                asker_avatar_url="http://asker.url",
                question_text="X" * 3000,  # Way too long
                answer_text="Y" * 3000,
                jump_url="http://discord.com/channels/1/2/2",
            ),
            QuestionData(
                question_number=3,
                asker_name="Asker",
                asker_avatar_url="http://asker.url",
                question_text="Q3?",
                answer_text="A3!",
                jump_url="http://discord.com/channels/1/2/3",
            ),
        ]

        result = generate_answer_embeds(interviewee, questions, prior_answered=0, total_asked=3)

        # Q1 and Q3 should succeed, Q2 skipped
        assert len(result.skipped_questions) == 1
        assert result.skipped_questions[0].question_number == 2
        # Should have embed(s) for Q1 and Q3
        assert len(result.embed_groups) >= 1
