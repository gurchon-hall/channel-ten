"""Tests for channel_ten._krcg_helper module.

Strategy: pre-seed the module-level caches or set kh._cards directly so tests
never touch the real VTES database, keeping them fast and deterministic.
"""

# pyright: reportPrivateUsage=false

import sys
import types
from typing import Any
from unittest.mock import MagicMock, patch

import channel_ten._krcg_helper as kh

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reset_state() -> None:
    """Restore module-level cache to its initial (unchecked) state."""
    kh._krcg_loaded = None
    kh._i18n_ensured = False
    kh._cards = None
    kh._i18n_lookup.clear()
    kh._seen_cards.clear()
    kh._cards_loaded.clear()


def _named_card(printed_name: str) -> MagicMock:
    card = MagicMock()
    card.printed_name = printed_name
    card.kind = "Library"
    return card


def _make_cards_mock(get_return_value: Any = None) -> MagicMock:
    """Return a mock CardDict.

    __getitem__ raises KeyError (card not found) when *get_return_value* is None,
    or returns *get_return_value* otherwise.  .cards() yields an empty iterator.
    """
    mock_cards = MagicMock()
    if get_return_value is None:
        mock_cards.__getitem__ = MagicMock(side_effect=KeyError)
    else:
        mock_cards.__getitem__ = MagicMock(return_value=get_return_value)
    mock_cards.cards.return_value = iter([])
    return mock_cards


def _make_krcg_mock(get_return_value: Any = None) -> tuple[MagicMock, MagicMock]:
    """Return a (mock_krcg_module, mock_cards_dict) pair.

    mock_krcg.load() returns mock_cards.
    """
    mock_cards = _make_cards_mock(get_return_value)
    mock_krcg_mod = MagicMock()
    mock_krcg_mod.load.return_value = mock_cards
    return mock_krcg_mod, mock_cards


def _make_crypt_card(
    *,
    card_id: int = 1001,
    kind: str = "Crypt",
    advanced: bool = False,
    group: object = "G6",
    capacity: int = 4,
    disciplines: list[str] | None = None,
    clan: str = "Gangrel",
    title: str | None = None,
    path: str | None = None,
    printed_name: str = "Nathan Turner",
) -> MagicMock:
    card = MagicMock()
    card.id = card_id
    card.kind = kind
    card.advanced = advanced
    card.group = group
    card.capacity = capacity
    card.disciplines = ["PRO", "ani"] if disciplines is None else disciplines
    card.clan = clan
    card.title = title
    card.path = path
    card.printed_name = printed_name
    return card


# ---------------------------------------------------------------------------
# _strip_group_suffix
# ---------------------------------------------------------------------------


class TestStripGroupSuffix:
    def test_removes_group_number(self):
        assert kh._strip_group_suffix("Nathan Turner (G6)") == "Nathan Turner"

    def test_removes_group_with_adv_keeps_adv(self):
        assert kh._strip_group_suffix("Tariq (G6 ADV)") == "Tariq (ADV)"

    def test_lone_adv_unchanged(self):
        assert kh._strip_group_suffix("Tariq (ADV)") == "Tariq (ADV)"

    def test_no_suffix_unchanged(self):
        assert kh._strip_group_suffix("Anarch Convert") == "Anarch Convert"

    def test_case_insensitive(self):
        assert kh._strip_group_suffix("Mina (g3 adv)") == "Mina (ADV)"


# ---------------------------------------------------------------------------
# _ensure_i18n_loaded
# ---------------------------------------------------------------------------


class TestEnsureI18nLoaded:
    def setup_method(self):
        _reset_state()

    def teardown_method(self):
        _reset_state()

    def test_no_op_when_krcg_not_loaded(self):
        kh._krcg_loaded = False
        kh._ensure_i18n_loaded()
        assert kh._i18n_ensured is False

    def test_no_op_when_already_ensured(self):
        kh._krcg_loaded = True
        kh._i18n_ensured = True
        mock_cards_obj = MagicMock()
        kh._cards = mock_cards_obj
        kh._ensure_i18n_loaded()
        mock_cards_obj.cards.assert_not_called()

    def test_builds_i18n_lookup_from_cards(self):
        kh._krcg_loaded = True
        mock_card = MagicMock()
        mock_card.id = 42
        mock_translation = MagicMock()
        mock_translation.name = "Sueños de la Esfinge"
        mock_card.i18n = {"es": mock_translation}
        mock_cards_obj = MagicMock()
        mock_cards_obj.cards.return_value = iter([mock_card])
        kh._cards = mock_cards_obj
        kh._ensure_i18n_loaded()
        assert kh._i18n_ensured is True
        assert kh._i18n_lookup.get("Sueños de la Esfinge") == 42

    def test_idempotent(self):
        kh._krcg_loaded = True
        mock_cards_obj = MagicMock()
        mock_cards_obj.cards.return_value = iter([])
        kh._cards = mock_cards_obj
        kh._ensure_i18n_loaded()
        kh._ensure_i18n_loaded()  # second call must be a no-op
        mock_cards_obj.cards.assert_called_once()

    def test_exception_is_swallowed(self):
        kh._krcg_loaded = True
        mock_cards_obj = MagicMock()
        mock_cards_obj.cards.side_effect = RuntimeError("boom")
        kh._cards = mock_cards_obj
        kh._ensure_i18n_loaded()  # must not raise
        assert kh._i18n_ensured is True


# ---------------------------------------------------------------------------
# is_krcg_loaded
# ---------------------------------------------------------------------------


class TestIsKrcgLoaded:
    def setup_method(self):
        _reset_state()

    def teardown_method(self):
        _reset_state()

    def test_returns_cached_true(self):
        kh._krcg_loaded = True
        assert kh.is_krcg_loaded() is True

    def test_returns_cached_false(self):
        kh._krcg_loaded = False
        assert kh.is_krcg_loaded() is False

    def test_loads_and_caches_true(self):
        mock_krcg, mock_cards = _make_krcg_mock()
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            result = kh.is_krcg_loaded()
        assert result is True
        assert kh._krcg_loaded is True
        assert kh._cards is mock_cards

    def test_import_error_caches_false(self):
        """When krcg.load cannot be imported, is_krcg_loaded returns False."""
        broken = types.ModuleType("krcg")
        # broken has no 'load' attribute → 'from krcg import load' raises ImportError
        with patch.dict(sys.modules, {"krcg": broken}):
            result = kh.is_krcg_loaded()
        assert result is False
        assert kh._krcg_loaded is False


# ---------------------------------------------------------------------------
# krcg_card_search
# ---------------------------------------------------------------------------


class TestKrcgCardSearch:
    def setup_method(self):
        _reset_state()

    def teardown_method(self):
        _reset_state()

    def test_returns_none_when_krcg_not_loaded(self):
        kh._krcg_loaded = False
        assert kh.krcg_card_search("Blood Doll") is None

    def test_returns_cached_result(self):
        mock_card = MagicMock()
        kh._krcg_loaded = True
        kh._seen_cards.add("Blood Doll")
        kh._cards_loaded["Blood Doll"] = mock_card
        assert kh.krcg_card_search("Blood Doll") is mock_card

    def test_returns_none_from_cache_when_card_missing(self):
        """Cache hit that stored None still returns None."""
        kh._krcg_loaded = True
        kh._seen_cards.add("Unknown")
        kh._cards_loaded["Unknown"] = None
        assert kh.krcg_card_search("Unknown") is None

    def test_fetches_card_from_database(self):
        mock_card = MagicMock()
        kh._krcg_loaded = True
        kh._cards = _make_cards_mock(get_return_value=mock_card)
        result = kh.krcg_card_search("Blood Doll")
        assert result is mock_card
        assert "Blood Doll" in kh._seen_cards
        assert kh._cards_loaded["Blood Doll"] is mock_card

    def test_logs_when_card_not_in_database(self):
        kh._krcg_loaded = True
        kh._cards = _make_cards_mock()  # all lookups raise KeyError
        result = kh.krcg_card_search("Nonexistent Card")
        assert result is None
        assert "Nonexistent Card" in kh._seen_cards

    def test_fetches_card_by_integer_id(self):
        mock_card = MagicMock()
        kh._krcg_loaded = True
        kh._cards = _make_cards_mock(get_return_value=mock_card)
        result = kh.krcg_card_search(1001)
        assert result is mock_card
        assert 1001 in kh._seen_cards


# ---------------------------------------------------------------------------
# get_all_vamp_variants
# ---------------------------------------------------------------------------


class TestGetAllVampVariants:
    def setup_method(self):
        _reset_state()
        # Unit tests supply explicit mock card data; skip live-data loading so
        # _ensure_i18n_loaded() is a no-op and never touches the real krcg module.
        kh._i18n_ensured = True

    def teardown_method(self):
        _reset_state()

    def _setup(self, *cards: MagicMock, search_name: str = "Nathan Turner") -> MagicMock:
        """Seed the search cache and _cards.cards() with *cards*.

        The first card in *cards* is returned by krcg_card_search(search_name).
        All cards are yielded by _cards.cards() for the iteration pass.
        """
        kh._krcg_loaded = True
        if cards:
            kh._seen_cards.add(search_name)
            kh._cards_loaded[search_name] = cards[0]
        mock_cards_obj = MagicMock()
        mock_cards_obj.cards.return_value = iter(cards)
        kh._cards = mock_cards_obj
        return mock_cards_obj

    def test_calls_ensure_i18n_before_lookup(self):
        """get_all_vamp_variants calls _ensure_i18n_loaded() so path data is loaded."""
        kh._krcg_loaded = True
        kh._i18n_ensured = False  # reset so the call is observable
        with patch.object(kh, "_ensure_i18n_loaded") as mock_ensure:
            with patch.object(kh, "krcg_card_search", return_value=None):
                kh.get_all_vamp_variants("Some Vampire")
        mock_ensure.assert_called_once()

    def test_returns_empty_when_krcg_not_loaded(self):
        kh._krcg_loaded = False
        assert kh.get_all_vamp_variants("Xaviar") == []

    def test_returns_empty_when_not_a_crypt_card(self):
        mock_card = _make_crypt_card(kind="Library")
        self._setup(mock_card)
        result = kh.get_all_vamp_variants("Blood Doll")
        assert result == []

    def test_returns_empty_when_card_not_found(self):
        kh._krcg_loaded = True
        kh._seen_cards.add("Unknown")
        kh._cards_loaded["Unknown"] = None
        kh._cards = _make_cards_mock()
        assert kh.get_all_vamp_variants("Unknown") == []

    def test_returns_variant_data_for_non_adv(self):
        mock_card = _make_crypt_card()
        self._setup(mock_card)
        result = kh.get_all_vamp_variants("Nathan Turner")
        assert len(result) == 1
        entry = result[0]
        assert entry.get("capacity") == 4
        assert "PRO" in (entry.get("disciplines") or "")
        assert entry.get("clan") == "Gangrel"
        assert entry.get("grouping") == 6
        assert entry.get("path") is None

    def test_includes_card_id(self):
        mock_card = _make_crypt_card(card_id=20013)
        self._setup(mock_card)
        result = kh.get_all_vamp_variants("Nathan Turner")
        assert len(result) == 1
        assert "id" in result[0] and result[0]["id"] == 20013

    def test_returns_path_when_present(self):
        mock_card = _make_crypt_card(path="Power and the Inner Voice")
        self._setup(mock_card, search_name="Aaradhya, The Callous Tyrant")
        result = kh.get_all_vamp_variants("Aaradhya, The Callous Tyrant")
        assert len(result) == 1
        assert result[0].get("path") == "Power and the Inner Voice"

    def test_skips_adv_when_looking_up_base(self):
        """Iteration yields both base and ADV; only base is returned."""
        base_card = _make_crypt_card(advanced=False, card_id=1001)
        adv_card = _make_crypt_card(advanced=True, card_id=1002)
        kh._krcg_loaded = True
        kh._seen_cards.add("Nathan Turner")
        kh._cards_loaded["Nathan Turner"] = base_card
        mock_cards_obj = MagicMock()
        mock_cards_obj.cards.return_value = iter([base_card, adv_card])
        kh._cards = mock_cards_obj
        result = kh.get_all_vamp_variants("Nathan Turner")
        assert len(result) == 1

    def test_handles_group_any(self):
        mock_card = _make_crypt_card(group="Any")  # krcg 5.0 uses "Any" not "ANY"
        self._setup(mock_card)
        result = kh.get_all_vamp_variants("Nathan Turner")
        assert len(result) == 1
        assert result[0].get("grouping") == "ANY"

    def test_skips_cards_with_no_group(self):
        mock_card = _make_crypt_card(group=None)
        self._setup(mock_card)
        assert kh.get_all_vamp_variants("Nathan Turner") == []

    def test_skips_variant_with_no_disciplines(self):
        mock_card = _make_crypt_card(disciplines=[])
        self._setup(mock_card)
        result = kh.get_all_vamp_variants("Nathan Turner")
        assert result[0].get("disciplines") == ""

    def test_card_with_no_clan(self):
        mock_card = _make_crypt_card(clan="")
        self._setup(mock_card)
        result = kh.get_all_vamp_variants("Nathan Turner")
        assert result[0].get("clan") == ""

    def test_bad_group_format_is_skipped(self):
        """Group string that can't be parsed as int after stripping 'G' is skipped."""
        bad_card = _make_crypt_card(group="GXXX")  # int("XXX") → ValueError
        self._setup(bad_card)
        assert kh.get_all_vamp_variants("Nathan Turner") == []

    def test_multiple_group_versions_all_returned(self):
        """All group versions of a vampire are returned when _cards has multiple."""
        g5_card = _make_crypt_card(group="G5", card_id=1001)
        g6_card = _make_crypt_card(group="G6", card_id=1002)
        kh._krcg_loaded = True
        kh._seen_cards.add("Nathan Turner")
        kh._cards_loaded["Nathan Turner"] = g5_card
        mock_cards_obj = MagicMock()
        mock_cards_obj.cards.return_value = iter([g5_card, g6_card])
        kh._cards = mock_cards_obj
        result = kh.get_all_vamp_variants("Nathan Turner")
        assert len(result) == 2
        assert {r.get("grouping") for r in result} == {5, 6}

    def test_cards_iterator_exception_propagates(self):
        """Unexpected exceptions (not KeyError/AttributeError/TypeError/ValueError) propagate."""
        main_card = _make_crypt_card()
        kh._krcg_loaded = True
        kh._seen_cards.add("Nathan Turner")
        kh._cards_loaded["Nathan Turner"] = main_card
        mock_cards_obj = MagicMock()
        mock_cards_obj.cards.side_effect = RuntimeError("unexpected!")
        kh._cards = mock_cards_obj
        import pytest

        with pytest.raises(RuntimeError, match="unexpected!"):
            kh.get_all_vamp_variants("Nathan Turner")


# ---------------------------------------------------------------------------
# canonicalize_card_name
# ---------------------------------------------------------------------------


class TestCanonicalizeCardName:
    def setup_method(self):
        _reset_state()

    def teardown_method(self):
        _reset_state()

    def test_returns_unchanged_when_krcg_not_loaded(self):
        kh._krcg_loaded = False
        assert kh.canonicalize_card_name("The Coven") == "The Coven"

    def test_direct_hit_returns_printed_name(self):
        card = _named_card("Blood Doll")
        kh._krcg_loaded = True
        kh._seen_cards.add("Blood Doll")
        kh._cards_loaded["Blood Doll"] = card
        assert kh.canonicalize_card_name("Blood Doll") == "Blood Doll"

    def test_leading_the_fallback(self):
        card = _named_card("Coven, The")
        kh._krcg_loaded = True
        # "The Coven" misses; "Coven, The" hits
        kh._seen_cards.add("The Coven")
        kh._cards_loaded["The Coven"] = None
        kh._seen_cards.add("Coven, The")
        kh._cards_loaded["Coven, The"] = card
        assert kh.canonicalize_card_name("The Coven") == "Coven, The"

    def test_trailing_the_fallback(self):
        card = _named_card("Unmasking, The")
        kh._krcg_loaded = True
        # "Unmasking" misses; "Unmasking, The" hits
        kh._seen_cards.add("Unmasking")
        kh._cards_loaded["Unmasking"] = None
        kh._seen_cards.add("Unmasking, The")
        kh._cards_loaded["Unmasking, The"] = card
        assert kh.canonicalize_card_name("Unmasking") == "Unmasking, The"

    def test_resolves_localized_name(self):
        """A Spanish name resolves via _i18n_lookup to the canonical English name."""
        card = _named_card("Dreams of the Sphinx")
        card.id = 100
        kh._krcg_loaded = True
        kh._i18n_ensured = True
        kh._i18n_lookup["Sueños de la Esfinge"] = 100
        # Name-based lookups all miss; ID lookup hits via cache
        kh._cards = _make_cards_mock()
        kh._seen_cards.add(100)
        kh._cards_loaded[100] = card
        assert kh.canonicalize_card_name("Sueños de la Esfinge") == "Dreams of the Sphinx"

    def test_i18n_fallback_triggers_i18n_load(self):
        """When name not found, _ensure_i18n_loaded() is called."""
        kh._krcg_loaded = True
        kh._i18n_ensured = False
        kh._cards = _make_cards_mock()  # all lookups miss
        result = kh.canonicalize_card_name("Totally Unknown Card")
        assert result == "Totally Unknown Card"
        assert kh._i18n_ensured is True

    def test_unresolved_name_returned_unchanged(self):
        kh._krcg_loaded = True
        kh._i18n_ensured = True
        kh._cards = _make_cards_mock()  # all lookups miss
        assert kh.canonicalize_card_name("Carna, The Princess Bitch") == (
            "Carna, The Princess Bitch"
        )


# ---------------------------------------------------------------------------
# canonical_crypt_name
# ---------------------------------------------------------------------------


def _named_crypt_card(printed_name: str, *, advanced: bool = False) -> MagicMock:
    card = MagicMock()
    card.kind = "Crypt"
    card.printed_name = printed_name
    card.advanced = advanced
    return card


class TestCanonicalCryptName:
    def setup_method(self):
        _reset_state()

    def teardown_method(self):
        _reset_state()

    def test_strips_group_suffix_when_krcg_unavailable(self):
        kh._krcg_loaded = False
        assert kh.canonical_crypt_name("Mina Grotius (G3)") == "Mina Grotius"

    def test_keeps_adv_when_krcg_unavailable(self):
        kh._krcg_loaded = False
        assert kh.canonical_crypt_name("Tariq (G6 ADV)") == "Tariq (ADV)"

    def test_lone_adv_preserved_when_krcg_unavailable(self):
        kh._krcg_loaded = False
        assert kh.canonical_crypt_name("Tariq (ADV)") == "Tariq (ADV)"

    def test_resolved_returns_bare_printed_name(self):
        card = _named_crypt_card("Mina Grotius")
        kh._krcg_loaded = True
        kh._seen_cards.add("Mina Grotius (G3)")
        kh._cards_loaded["Mina Grotius (G3)"] = card
        assert kh.canonical_crypt_name("Mina Grotius (G3)") == "Mina Grotius"

    def test_resolved_advanced_appends_adv(self):
        card = _named_crypt_card("Tariq", advanced=True)
        kh._krcg_loaded = True
        kh._seen_cards.add("Tariq (G6 ADV)")
        kh._cards_loaded["Tariq (G6 ADV)"] = card
        assert kh.canonical_crypt_name("Tariq (G6 ADV)") == "Tariq (ADV)"


# ---------------------------------------------------------------------------
# get_library_card_type
# ---------------------------------------------------------------------------


class TestGetLibraryCardType:
    def setup_method(self):
        _reset_state()

    def teardown_method(self):
        _reset_state()

    def test_returns_none_when_krcg_not_loaded(self):
        kh._krcg_loaded = False
        assert kh.get_library_card_type("Blood Doll") is None

    def test_returns_none_when_card_not_found(self):
        kh._krcg_loaded = True
        kh._seen_cards.add("Nonexistent")
        kh._cards_loaded["Nonexistent"] = None
        assert kh.get_library_card_type("Nonexistent") is None

    def test_returns_single_type(self):
        mock_card = MagicMock()
        mock_card.types = ["Master"]
        kh._krcg_loaded = True
        kh._seen_cards.add("Blood Doll")
        kh._cards_loaded["Blood Doll"] = mock_card
        assert kh.get_library_card_type("Blood Doll") == "Master"

    def test_returns_sorted_joined_types(self):
        mock_card = MagicMock()
        mock_card.types = ["Combat", "Action"]
        kh._krcg_loaded = True
        kh._seen_cards.add("Multi-type Card")
        kh._cards_loaded["Multi-type Card"] = mock_card
        assert kh.get_library_card_type("Multi-type Card") == "Action/Combat"
