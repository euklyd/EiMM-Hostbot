"""Tests for cogs/scryfall.py card search logic."""

import discord

from cogs.scryfall import Cards, ScryfallResponse


class TestScryfallResponse:
    """Tests for the ScryfallResponse class."""

    def test_closest_exact_match(self) -> None:
        """Exact match should return the card."""
        cards = [{"name": "Lightning Bolt"}, {"name": "Lightning Helix"}]
        names = ["Lightning Bolt", "Lightning Helix"]
        card_map = {c["name"]: c for c in cards}
        response = ScryfallResponse(cards, names, card_map)

        result = response.closest("Lightning Bolt")
        assert result is not None
        assert result["name"] == "Lightning Bolt"

    def test_closest_fuzzy_match(self) -> None:
        """Fuzzy match should return closest card."""
        cards = [{"name": "Lightning Bolt"}, {"name": "Chain Lightning"}]
        names = ["Lightning Bolt", "Chain Lightning"]
        card_map = {c["name"]: c for c in cards}
        response = ScryfallResponse(cards, names, card_map)

        # "Bolt" should match "Lightning Bolt" better
        result = response.closest("Bolt")
        assert result is not None
        assert result["name"] == "Lightning Bolt"

    def test_closest_no_cards(self) -> None:
        """Empty card list should return None."""
        response = ScryfallResponse([], [], {})
        result = response.closest("anything")
        assert result is None


class TestYgoUrl:
    """Tests for YGO URL generation methods."""

    def test_ygo_url_simple(self) -> None:
        """Simple card name should be URL encoded."""
        card = {"name": "Dark Magician"}
        result = Cards._ygo_url(card)
        assert "Dark%20Magician" in result
        assert result.startswith("https://db.ygoprodeck.com/card/")

    def test_ygo_url_special_chars(self) -> None:
        """Special characters should be URL encoded."""
        card = {"name": "Pot of Greed"}
        result = Cards._ygo_url(card)
        assert "Pot%20of%20Greed" in result

    def test_ygo_set_url(self) -> None:
        """Set URL should be properly formatted."""
        set_info = {"set_name": "Legend of Blue Eyes"}
        result = Cards._ygo_set_url(set_info)
        assert "Legend%20of%20Blue%20Eyes" in result
        assert result.startswith("https://db.ygoprodeck.com/set/")

    def test_ygo_archetype_url_present(self) -> None:
        """Archetype URL should be generated when archetype exists."""
        card = {"archetype": "Blue-Eyes"}
        result = Cards._ygo_archetype_url(card)
        assert result is not None
        assert "Blue-Eyes" in result
        assert result.startswith("https://db.ygoprodeck.com/search/")

    def test_ygo_archetype_url_missing(self) -> None:
        """Missing archetype should return None."""
        card = {"name": "Kuriboh"}
        result = Cards._ygo_archetype_url(card)
        assert result is None


class TestYgoSupertype:
    """Tests for the _ygo_supertype method."""

    def test_monster_type(self) -> None:
        """Monster types should return 'Monster'."""
        assert Cards._ygo_supertype({"type": "Normal Monster"}) == "Monster"
        assert Cards._ygo_supertype({"type": "Effect Monster"}) == "Monster"
        assert Cards._ygo_supertype({"type": "Fusion Monster"}) == "Monster"

    def test_spell_type(self) -> None:
        """Spell types should return 'Spell'."""
        assert Cards._ygo_supertype({"type": "Spell Card"}) == "Spell"
        assert Cards._ygo_supertype({"type": "Continuous Spell"}) == "Spell"

    def test_trap_type(self) -> None:
        """Trap types should return 'Trap'."""
        assert Cards._ygo_supertype({"type": "Trap Card"}) == "Trap"
        assert Cards._ygo_supertype({"type": "Counter Trap"}) == "Trap"

    def test_unknown_type(self) -> None:
        """Unknown type should return None."""
        assert Cards._ygo_supertype({"type": "Token"}) is None

    def test_case_insensitive(self) -> None:
        """Type matching should be case-insensitive."""
        assert Cards._ygo_supertype({"type": "NORMAL MONSTER"}) == "Monster"
        assert Cards._ygo_supertype({"type": "spell card"}) == "Spell"


class TestYgoBaninfo:
    """Tests for the _ygo_baninfo method."""

    def test_no_banlist(self) -> None:
        """Card without banlist info should return None."""
        card = {"name": "Kuriboh"}
        assert Cards._ygo_baninfo(card) is None

    def test_tcg_only(self) -> None:
        """TCG-only ban should be formatted correctly."""
        card = {"banlist_info": {"ban_tcg": "Banned"}}
        result = Cards._ygo_baninfo(card)
        assert result == "TCG: Banned"

    def test_ocg_only(self) -> None:
        """OCG-only ban should be formatted correctly."""
        card = {"banlist_info": {"ban_ocg": "Limited"}}
        result = Cards._ygo_baninfo(card)
        assert result == "OCG: Limited"

    def test_multiple_bans(self) -> None:
        """Multiple bans should be joined with ' | '."""
        card = {"banlist_info": {"ban_tcg": "Banned", "ban_ocg": "Limited"}}
        result = Cards._ygo_baninfo(card)
        assert result is not None
        assert "TCG: Banned" in result
        assert "OCG: Limited" in result
        assert " | " in result

    def test_all_ban_types(self) -> None:
        """All ban types should be included."""
        card = {
            "banlist_info": {
                "ban_tcg": "Banned",
                "ban_ocg": "Limited",
                "ban_goat": "Semi-Limited",
            }
        }
        result = Cards._ygo_baninfo(card)
        assert result is not None
        assert "TCG: Banned" in result
        assert "OCG: Limited" in result
        assert "Goat: Semi-Limited" in result


class TestYgoColor:
    """Tests for the _ygocolor method."""

    def test_normal_monster(self) -> None:
        """Normal monsters should be tan/yellow."""
        card = {"type": "Normal Monster"}
        result = Cards._ygocolor(card)
        assert result is not None
        assert isinstance(result, discord.Colour)
        assert result.value == 0xC9B175

    def test_effect_monster(self) -> None:
        """Effect monsters should be orange."""
        card = {"type": "Effect Monster"}
        result = Cards._ygocolor(card)
        assert result is not None
        assert result.value == 0xC26727

    def test_synchro_monster(self) -> None:
        """Synchro monsters should be white."""
        card = {"type": "Synchro Monster"}
        result = Cards._ygocolor(card)
        assert result is not None
        assert result.value == 0xFEFEFE

    def test_xyz_monster(self) -> None:
        """XYZ monsters should be black."""
        card = {"type": "XYZ Monster"}
        result = Cards._ygocolor(card)
        assert result is not None
        assert result.value == 0x000000

    def test_spell_card(self) -> None:
        """Spell cards should be green."""
        card = {"type": "Spell Card"}
        result = Cards._ygocolor(card)
        assert result is not None
        assert result.value == 0x30AB83

    def test_trap_card(self) -> None:
        """Trap cards should be purple/magenta."""
        card = {"type": "Trap Card"}
        result = Cards._ygocolor(card)
        assert result is not None
        assert result.value == 0xB135B5

    def test_unknown_type(self) -> None:
        """Unknown type should return None."""
        card = {"type": "Divine-Beast"}
        result = Cards._ygocolor(card)
        assert result is None

    def test_case_insensitive(self) -> None:
        """Type matching should be case-insensitive."""
        card = {"type": "SPELL CARD"}
        result = Cards._ygocolor(card)
        assert result is not None
        assert result.value == 0x30AB83
