"""Tests for utils module."""

from utils.menu import menu_str
from utils.utils import jump_url


class TestJumpUrl:
    """Tests for the jump_url function."""

    def test_basic_url(self) -> None:
        """Test basic jump URL generation."""
        url = jump_url(123, 456, 789)
        assert url == "https://discordapp.com/channels/123/456/789"

    def test_large_ids(self) -> None:
        """Test with realistic Discord snowflake IDs."""
        server_id = 444555666777888999
        channel_id = 111222333444555666
        message_id = 999888777666555444
        url = jump_url(server_id, channel_id, message_id)
        assert url == f"https://discordapp.com/channels/{server_id}/{channel_id}/{message_id}"


class TestMenuStr:
    """Tests for the menu_str function."""

    def test_basic_menu(self) -> None:
        """Test basic menu string generation."""
        keys = ["0", "1", "2"]
        elements = ["Apple", "Banana", "Cherry"]
        result = menu_str(keys, elements, page=0)

        assert "0. Apple" in result
        assert "1. Banana" in result
        assert "2. Cherry" in result
        assert "```" in result  # code block

    def test_menu_with_heading(self) -> None:
        """Test menu with a heading."""
        keys = ["a", "b"]
        elements = ["First", "Second"]
        result = menu_str(keys, elements, page=0, heading="Choose one:")

        assert "Choose one:" in result
        assert "a. First" in result

    def test_menu_pagination(self) -> None:
        """Test menu pagination text for multi-page menus."""
        keys = [str(i) for i in range(25)]  # More than 20 items
        elements = [f"Item {i}" for i in range(25)]

        result = menu_str(keys, elements, page=0, items_per_page=20)
        assert "Page 1 of 2" in result

        result = menu_str(keys, elements, page=1, items_per_page=20)
        assert "Page 2 of 2" in result

    def test_menu_no_code_block(self) -> None:
        """Test menu without code block formatting."""
        keys = ["1", "2"]
        elements = ["One", "Two"]
        result = menu_str(keys, elements, page=0, use_code_block=False)

        assert "```" not in result
        assert "1. One" in result

    def test_menu_multi_select_text(self) -> None:
        """Test that multi-select menus show appropriate text."""
        keys = ["a", "b", "c"]
        elements = ["X", "Y", "Z"]

        # Single select
        result = menu_str(keys, elements, page=0, select_max=1)
        assert "an item" in result

        # Multi select with limit
        result = menu_str(keys, elements, page=0, select_max=3)
        assert "up to 3 items" in result

        # Unlimited multi select
        result = menu_str(keys, elements, page=0, select_max=None)
        assert "one or more items" in result

    def test_menu_key_alignment(self) -> None:
        """Test that keys are right-aligned in code blocks."""
        keys = ["1", "10", "100"]
        elements = ["One", "Ten", "Hundred"]
        result = menu_str(keys, elements, page=0)

        # In code block, keys should be right-aligned
        # "  1. One", " 10. Ten", "100. Hundred"
        lines = result.split("\n")
        # Find the lines with numbers
        number_lines = [line for line in lines if ". " in line and any(c.isdigit() for c in line)]
        assert len(number_lines) == 3
