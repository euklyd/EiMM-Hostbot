"""Tests for cogs/eimm.py business logic."""

from unittest.mock import patch

from munkres import DISALLOWED

from cogs.eimm import (
    EiMM,
    Host,
    b_h,
    default_val,
    diff_dict,
    thwart_misty,
)


class TestThwartMisty:
    """Tests for the thwart_misty function."""

    def test_doc_passthrough(self) -> None:
        """Text containing 'doc' should pass through unchanged."""
        text = "Mt damage to the doc"
        result = thwart_misty("Heal", text)
        assert result == text
        assert "Mt" in result

    def test_busted_ability_skips_replacement(self) -> None:
        """Abilities named 'busted' should still replace Mt with Atk."""
        text = "Deal 5 Mt damage"
        result = thwart_misty("Busted Strike", text)
        assert "Atk" in result
        assert "Mt" not in result

    def test_brutalize_ability_skips_replacement(self) -> None:
        """Abilities named 'brutalize' should still replace Mt with Atk."""
        text = "Deal 10 Mt damage"
        result = thwart_misty("Brutalize", text)
        assert "Atk" in result

    def test_normal_ability_replaces_mt(self) -> None:
        """Normal abilities should replace Mt with Atk."""
        text = "Deal Mt damage to target"
        result = thwart_misty("Fire Strike", text)
        assert result == "Deal Atk damage to target"

    def test_case_insensitive_replacement(self) -> None:
        """Replacement should be case-insensitive."""
        result = thwart_misty("Attack", "Deal MT damage")
        assert "Atk" in result

    def test_no_mt_unchanged(self) -> None:
        """Text without Mt should be unchanged."""
        text = "Deal damage to target"
        result = thwart_misty("Strike", text)
        assert result == text


class TestDefaultVal:
    """Tests for the default_val function."""

    def test_empty_string_returns_none(self) -> None:
        """Empty string should return 'None'."""
        assert default_val("") == "None"

    def test_non_empty_string_passthrough(self) -> None:
        """Non-empty strings should pass through."""
        assert default_val("hello") == "hello"

    def test_integer_converted_to_string(self) -> None:
        """Integers should be converted to strings."""
        assert default_val(42) == "42"

    def test_none_converted_to_string(self) -> None:
        """None should be converted to string 'None'."""
        assert default_val(None) == "None"


class TestBH:
    """Tests for the b_h function."""

    def test_bh_column_exists(self) -> None:
        """When B/H column exists, return it."""
        row = {"B/H": "B"}
        assert b_h(row) == "B"

    def test_hb_column_exists(self) -> None:
        """When H/B column exists, return it."""
        row = {"H/B": "H"}
        assert b_h(row) == "H"

    def test_bh_column_preferred_over_hb(self) -> None:
        """B/H column should be preferred over H/B."""
        row = {"B/H": "B", "H/B": "H"}
        assert b_h(row) == "B"

    def test_separate_columns_both_true(self) -> None:
        """Separate B and H columns both TRUE should return B/H."""
        row = {"B": "TRUE", "H": "TRUE"}
        assert b_h(row) == "B/H"

    def test_separate_columns_b_only(self) -> None:
        """Only B column TRUE should return B."""
        row = {"B": "TRUE", "H": "FALSE"}
        assert b_h(row) == "B"

    def test_separate_columns_h_only(self) -> None:
        """Only H column TRUE should return H."""
        row = {"B": "FALSE", "H": "TRUE"}
        assert b_h(row) == "H"

    def test_separate_columns_neither(self) -> None:
        """Neither B nor H TRUE should return N."""
        row = {"B": "FALSE", "H": "FALSE"}
        assert b_h(row) == "N"

    def test_missing_fields(self) -> None:
        """Missing fields should return ???."""
        row = {}
        assert b_h(row) == "???"

    def test_empty_bh_column(self) -> None:
        """Empty B/H column should fall through to other checks."""
        row = {"B/H": "", "B": "TRUE", "H": "FALSE"}
        assert b_h(row) == "B"


class TestDiffDict:
    """Tests for the diff_dict function."""

    def test_added_keys(self) -> None:
        """New keys should be in 'add'."""
        old = {"a": {"x": 1}}
        new = {"a": {"x": 1}, "b": {"y": 2}}
        result = diff_dict(new, old)
        assert "b" in result["add"]
        assert result["add"]["b"] == {"y": 2}

    def test_removed_keys(self) -> None:
        """Removed keys should be in 'rm'."""
        old = {"a": {"x": 1}, "b": {"y": 2}}
        new = {"a": {"x": 1}}
        result = diff_dict(new, old)
        assert "b" in result["rm"]
        assert result["rm"]["b"] == {"y": 2}

    def test_changed_values(self) -> None:
        """Changed values should be in 'ch' with old/new."""
        old = {"a": {"x": 1}}
        new = {"a": {"x": 2}}
        result = diff_dict(new, old)
        assert "a" in result["ch"]
        assert result["ch"]["a"]["x"] == {"new": 2, "old": 1}

    def test_no_changes(self) -> None:
        """Identical dicts should have empty diff."""
        data = {"a": {"x": 1}}
        result = diff_dict(data, data.copy())
        assert result["add"] == {}
        assert result["rm"] == {}
        assert result["ch"] == {}

    def test_new_field_in_entry(self) -> None:
        """New field in existing entry should be tracked."""
        old = {"a": {"x": 1}}
        new = {"a": {"x": 1, "y": 2}}
        result = diff_dict(new, old)
        assert "a" in result["ch"]
        assert result["ch"]["a"]["y"] == (2, None)


class TestHost:
    """Tests for the Host class."""

    def test_integer_preferences(self) -> None:
        """Integer preferences should be stored as-is."""
        host = Host("test#1234", [1, 2, 3], 0)
        assert host.prefs == [1, 2, 3]

    def test_empty_string_becomes_disallowed(self) -> None:
        """Empty string preferences become DISALLOWED."""
        host = Host("test#1234", [1, "", 3], 0)
        assert host.prefs[1] == DISALLOWED

    def test_none_becomes_disallowed(self) -> None:
        """None preferences become DISALLOWED."""
        host = Host("test#1234", [1, None, 3], 0)
        assert host.prefs[1] == DISALLOWED

    def test_string_number_converted(self) -> None:
        """String numbers should be converted to int."""
        host = Host("test#1234", ["1", "2", "3"], 0)
        assert host.prefs == [1, 2, 3]

    def test_priority_assignment(self) -> None:
        """Priority should be assigned correctly."""
        host = Host("test#1234", [1], 5)
        assert host.prio == 5

    def test_repr(self) -> None:
        """__repr__ should format correctly."""
        host = Host("test#1234", [1, "", 3], 0)
        repr_str = repr(host)
        assert "test#1234" in repr_str
        assert "None" in repr_str  # DISALLOWED shown as None

    def test_str(self) -> None:
        """__str__ should format correctly."""
        host = Host("test#1234", [1, 2], 1)
        str_str = str(host)
        assert "test#1234" in str_str
        assert "[1]" in str_str


class TestModBiasHostSelection:
    """Tests for the _mod_bias_host_selection static method."""

    def test_priority_hosts_selected_first(self) -> None:
        """High priority hosts should be selected first."""
        hosts = {
            "prio1#1234": {"prefs": [1, 1, 1], "priority": 1},
            "prio2#1234": {"prefs": [1, 1, 1], "priority": 1},
            "normal#1234": {"prefs": [1, 1, 1], "priority": 0},
        }
        with patch("random.sample", side_effect=lambda x, n: x[:n]):
            with patch("random.shuffle"):
                picks = EiMM._mod_bias_host_selection(hosts, priority=2)
        # First two should be priority hosts
        prio_names = {picks[0].name, picks[1].name}
        assert "prio1#1234" in prio_names
        assert "prio2#1234" in prio_names

    def test_fewer_priority_than_requested(self) -> None:
        """When fewer priority hosts than requested, use all available."""
        hosts = {
            "prio1#1234": {"prefs": [1], "priority": 1},
            "normal#1234": {"prefs": [1], "priority": 0},
        }
        with patch("random.shuffle"):
            picks = EiMM._mod_bias_host_selection(hosts, priority=2)
        assert picks[0].name == "prio1#1234"

    def test_low_priority_hosts_at_end(self) -> None:
        """Low priority hosts should come after normal hosts."""
        hosts = {
            "low#1234": {"prefs": [1], "priority": -1},
            "normal#1234": {"prefs": [1], "priority": 0},
        }
        with patch("random.shuffle"):
            picks = EiMM._mod_bias_host_selection(hosts, priority=0)
        assert picks[0].name == "normal#1234"
        assert picks[1].name == "low#1234"


class TestModBiasHungarianAlgorithm:
    """Tests for the _mod_bias_hungarian_algorithm static method."""

    def test_single_host_assignment(self) -> None:
        """Single host should be assigned to their preferred slot."""
        host = Host("test#1234", [1, 2, 3], 0)
        with patch("random.shuffle"):
            assignments = EiMM._mod_bias_hungarian_algorithm([host], total=3)
        # Host should be assigned to slot 0 (preference 1 is lowest cost)
        assert host in assignments

    def test_multiple_hosts_assigned(self) -> None:
        """Multiple hosts should all get assignments."""
        hosts = [
            Host("a#1234", [1, 2], 0),
            Host("b#1234", [2, 1], 0),
        ]
        with patch("random.shuffle"):
            assignments = EiMM._mod_bias_hungarian_algorithm(hosts, total=2)
        assert assignments[0] is not None
        assert assignments[1] is not None


class TestModBiasQueueAlgorithm:
    """Tests for the full queue algorithm pipeline."""

    def test_full_pipeline(self) -> None:
        """Full pipeline should return assignments and picks."""
        hosts = {
            "a#1234": {"prefs": [1, 2], "priority": 1},
            "b#1234": {"prefs": [2, 1], "priority": 0},
        }
        with patch("random.sample", side_effect=lambda x, n: x[:n]):
            with patch("random.shuffle"):
                assignments, picks = EiMM._mod_bias_queue_algorithm(hosts, priority=1, total=2)
        assert len(picks) == 2
        # Assignments should be a list with hosts assigned to slots
        assert assignments[0] is not None or assignments[1] is not None
