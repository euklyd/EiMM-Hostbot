"""Tests for spreadsheet utility functions."""

from utils.spreadsheet import find_record, find_row, vlookup_heading


class TestFindRow:
    """Tests for find_row function."""

    def test_find_existing_row(self) -> None:
        """Test finding an existing row."""
        records = [
            {"name": "Alice", "score": 100},
            {"name": "Bob", "score": 85},
            {"name": "Charlie", "score": 90},
        ]
        # Returns row number (1-indexed, +1 for header row)
        assert find_row(records, "Bob", "name") == 3  # index 1 + 2 = 3

    def test_find_first_row(self) -> None:
        """Test finding the first row."""
        records = [
            {"id": 1, "value": "first"},
            {"id": 2, "value": "second"},
        ]
        assert find_row(records, 1, "id") == 2  # index 0 + 2 = 2

    def test_find_nonexistent_row(self) -> None:
        """Test that None is returned for nonexistent values."""
        records = [{"name": "Alice"}]
        assert find_row(records, "Bob", "name") is None

    def test_find_row_empty_records(self) -> None:
        """Test with empty records list."""
        assert find_row([], "anything", "col") is None


class TestFindRecord:
    """Tests for find_record function."""

    def test_find_existing_record(self) -> None:
        """Test finding an existing record."""
        records = [
            {"name": "Alice", "score": 100, "rank": 1},
            {"name": "Bob", "score": 85, "rank": 2},
        ]
        result = find_record(records, "Bob", "name")
        assert result == {"name": "Bob", "score": 85, "rank": 2}

    def test_find_nonexistent_record(self) -> None:
        """Test that None is returned for nonexistent values."""
        records = [{"name": "Alice", "value": 1}]
        assert find_record(records, "Bob", "name") is None

    def test_find_record_by_numeric_key(self) -> None:
        """Test finding a record by numeric key."""
        records = [
            {"id": 100, "data": "first"},
            {"id": 200, "data": "second"},
        ]
        result = find_record(records, 200, "id")
        assert result == {"id": 200, "data": "second"}


class TestVlookupHeading:
    """Tests for vlookup_heading function."""

    def test_basic_vlookup(self) -> None:
        """Test basic vlookup functionality."""
        records = [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Bob", "email": "bob@example.com"},
        ]
        result = vlookup_heading(records, "Alice", "name", "email")
        assert result == "alice@example.com"

    def test_vlookup_returns_none_for_missing(self) -> None:
        """Test that None is returned for missing values."""
        records = [{"name": "Alice", "value": 1}]
        result = vlookup_heading(records, "Bob", "name", "value")
        assert result is None

    def test_vlookup_different_types(self) -> None:
        """Test vlookup with different value types."""
        records = [
            {"id": 1, "active": True, "count": 42},
            {"id": 2, "active": False, "count": 0},
        ]
        assert vlookup_heading(records, 1, "id", "active") is True
        assert vlookup_heading(records, 2, "id", "count") == 0

    def test_vlookup_first_match(self) -> None:
        """Test that vlookup returns the first matching record."""
        records = [
            {"key": "dup", "value": "first"},
            {"key": "dup", "value": "second"},
        ]
        result = vlookup_heading(records, "dup", "key", "value")
        assert result == "first"
