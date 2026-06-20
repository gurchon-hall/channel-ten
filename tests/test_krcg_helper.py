"""Tests for channel_ten._krcg_helper module.

Strategy: mock the krcg module in sys.modules so tests never touch the
real VTES database, keeping them fast and deterministic.
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
    kh._seen_cards.clear()
    kh._cards_loaded.clear()


def _named_card(name: str) -> MagicMock:
    card = MagicMock()
    card.name = name
    return card


def _make_krcg_mock(get_return_value: Any = None):
    """Return a (mock_krcg_module, mock_vtes_module) pair.

    mock_krcg.vtes.VTES.get returns *get_return_value*.
    mock_krcg.vtes.VTES.load is a no-op.
    """
    mock_vtes_mod = MagicMock()
    mock_vtes_mod.VTES.get.return_value = get_return_value
    mock_krcg_mod = MagicMock()
    mock_krcg_mod.vtes = mock_vtes_mod
    return mock_krcg_mod, mock_vtes_mod


def _make_crypt_card(
    *,
    card_id: int = 1001,
    crypt: bool = True,
    adv: bool = False,
    group: object = "6",
    capacity: int = 4,
    disciplines: list[str] | None = None,
    clans: list[str] | None = None,
    title: str | None = None,
    path: str | None = None,
    variants: dict[Any, Any] | None = None,
) -> MagicMock:
    card = MagicMock()
    card.id = card_id
    card.crypt = crypt
    card.adv = adv
    card.group = group
    card.capacity = capacity
    card.disciplines = ["PRO", "ani"] if disciplines is None else disciplines
    card.clans = ["Gangrel"] if clans is None else clans
    card.title = title
    card.path = path
    card.variants = {} if variants is None else variants
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
        mock_krcg, mock_vtes = _make_krcg_mock()
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            kh._ensure_i18n_loaded()
        mock_vtes.VTES.load_from_vekn.assert_not_called()

    def test_skips_load_from_vekn_when_probe_resolves(self):
        kh._krcg_loaded = True
        mock_krcg, mock_vtes = _make_krcg_mock(get_return_value=MagicMock())
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            kh._ensure_i18n_loaded()
        mock_vtes.VTES.load_from_vekn.assert_not_called()
        assert kh._i18n_ensured is True

    def test_calls_load_from_vekn_when_probe_misses(self):
        kh._krcg_loaded = True
        mock_krcg, mock_vtes = _make_krcg_mock(get_return_value=None)
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            kh._ensure_i18n_loaded()
        mock_vtes.VTES.load_from_vekn.assert_called_once()
        assert kh._i18n_ensured is True

    def test_idempotent_load_from_vekn_called_once(self):
        kh._krcg_loaded = True
        mock_krcg, mock_vtes = _make_krcg_mock(get_return_value=None)
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            kh._ensure_i18n_loaded()
            kh._ensure_i18n_loaded()  # second call must be a no-op
        mock_vtes.VTES.load_from_vekn.assert_called_once()


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
        mock_krcg, _ = _make_krcg_mock()
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            result = kh.is_krcg_loaded()
        assert result is True
        assert kh._krcg_loaded is True

    def test_import_error_caches_false(self):
        """When krcg.vtes cannot be imported, is_krcg_loaded returns False."""
        broken = types.ModuleType("krcg")
        # broken has no 'vtes' attribute → 'from krcg import vtes' raises ImportError
        saved_vtes = sys.modules.pop("krcg.vtes", None)
        try:
            with patch.dict(sys.modules, {"krcg": broken}):
                result = kh.is_krcg_loaded()
        finally:
            if saved_vtes is not None:
                sys.modules["krcg.vtes"] = saved_vtes
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
        mock_krcg, _ = _make_krcg_mock(get_return_value=mock_card)
        kh._krcg_loaded = True
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            result = kh.krcg_card_search("Blood Doll")
        assert result is mock_card
        assert "Blood Doll" in kh._seen_cards
        assert kh._cards_loaded["Blood Doll"] is mock_card

    def test_logs_when_card_not_in_database(self):
        mock_krcg, _ = _make_krcg_mock(get_return_value=None)
        kh._krcg_loaded = True
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            result = kh.krcg_card_search("Nonexistent Card")
        assert result is None
        assert "Nonexistent Card" in kh._seen_cards

    def test_fetches_card_by_integer_id(self):
        mock_card = MagicMock()
        mock_krcg, _ = _make_krcg_mock(get_return_value=mock_card)
        kh._krcg_loaded = True
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            result = kh.krcg_card_search(1001)
        assert result is mock_card
        assert 1001 in kh._seen_cards


# ---------------------------------------------------------------------------
# get_all_vamp_variants
# ---------------------------------------------------------------------------


class TestGetAllVampVariants:
    def setup_method(self):
        _reset_state()

    def teardown_method(self):
        _reset_state()

    def test_returns_empty_when_krcg_not_loaded(self):
        kh._krcg_loaded = False
        assert kh.get_all_vamp_variants("Xaviar") == []

    def test_returns_empty_when_not_a_crypt_card(self):
        mock_card = _make_crypt_card(crypt=False)
        mock_krcg, _ = _make_krcg_mock(get_return_value=mock_card)
        kh._krcg_loaded = True
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            result = kh.get_all_vamp_variants("Blood Doll")
        assert result == []

    def test_returns_variant_data_for_non_adv(self):
        mock_card = _make_crypt_card()
        mock_krcg, mock_vtes = _make_krcg_mock(get_return_value=mock_card)
        # Also make integer-id lookups return the same card
        mock_vtes.VTES.get.return_value = mock_card
        kh._krcg_loaded = True
        kh._seen_cards.add(1001)
        kh._cards_loaded[1001] = mock_card
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            result = kh.get_all_vamp_variants("Nathan Turner")
        assert len(result) == 1
        entry = result[0]
        assert "capacity" in entry and entry["capacity"] == 4
        assert "disciplines" in entry and "PRO" in entry["disciplines"]
        assert "clan" in entry and entry["clan"] == "Gangrel"
        assert "grouping" in entry and entry["grouping"] == 6
        # Non-path vampire: path key present but None.
        assert "path" in entry and entry["path"] is None

    def test_returns_path_when_present(self):
        mock_card = _make_crypt_card(path="Power and the Inner Voice")
        mock_krcg, mock_vtes = _make_krcg_mock(get_return_value=mock_card)
        mock_vtes.VTES.get.return_value = mock_card
        kh._krcg_loaded = True
        kh._seen_cards.add(1001)
        kh._cards_loaded[1001] = mock_card
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            result = kh.get_all_vamp_variants("Aaradhya, The Callous Tyrant")
        assert len(result) == 1
        assert "path" in result[0] and result[0]["path"] == "Power and the Inner Voice"

    def test_skips_adv_when_looking_up_base(self):
        mock_adv = _make_crypt_card(adv=True)
        mock_base = _make_crypt_card(adv=False, card_id=1002, variants={})
        # Search by name returns the base card which has an ADV variant
        mock_base.variants = {"adv": 1003}
        mock_krcg, mock_vtes = _make_krcg_mock(get_return_value=mock_base)

        def _side_effect(card_id: int | str, default: Any = None):
            if card_id == "Nathan Turner":
                return mock_base
            if card_id == 1002:
                return mock_base
            if card_id == 1003:
                return mock_adv
            return default

        mock_vtes.VTES.get.side_effect = _side_effect
        kh._krcg_loaded = True
        kh._seen_cards.update([1002, 1003])
        kh._cards_loaded[1002] = mock_base
        kh._cards_loaded[1003] = mock_adv

        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            result = kh.get_all_vamp_variants("Nathan Turner")

        # Only non-ADV variants should be returned
        assert all(not r.get("adv") for r in result)

    def test_handles_group_any(self):
        mock_card = _make_crypt_card(group="ANY")
        mock_krcg, mock_vtes = _make_krcg_mock(get_return_value=mock_card)
        mock_vtes.VTES.get.return_value = mock_card
        kh._krcg_loaded = True
        kh._seen_cards.add(1001)
        kh._cards_loaded[1001] = mock_card
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            result = kh.get_all_vamp_variants("Generic Vampire")
        assert "grouping" in result[0] and result[0]["grouping"] == "ANY"

    def test_skips_cards_with_no_group(self):
        mock_card = _make_crypt_card(group="")
        mock_krcg, mock_vtes = _make_krcg_mock(get_return_value=mock_card)
        mock_vtes.VTES.get.return_value = mock_card
        kh._krcg_loaded = True
        kh._seen_cards.add(1001)
        kh._cards_loaded[1001] = mock_card
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            result = kh.get_all_vamp_variants("No Group Vamp")
        assert result == []

    def test_skips_variant_with_no_disciplines(self):
        mock_card = _make_crypt_card(disciplines=[])
        mock_krcg, mock_vtes = _make_krcg_mock(get_return_value=mock_card)
        mock_vtes.VTES.get.return_value = mock_card
        kh._krcg_loaded = True
        kh._seen_cards.add(1001)
        kh._cards_loaded[1001] = mock_card
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            result = kh.get_all_vamp_variants("Nathan Turner")
        assert "disciplines" in result[0] and result[0]["disciplines"] == ""

    def test_card_with_no_clan(self):
        mock_card = _make_crypt_card(clans=[])
        mock_krcg, mock_vtes = _make_krcg_mock(get_return_value=mock_card)
        mock_vtes.VTES.get.return_value = mock_card
        kh._krcg_loaded = True
        kh._seen_cards.add(1001)
        kh._cards_loaded[1001] = mock_card
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            result = kh.get_all_vamp_variants("Clanless")
        assert "clan" in result[0] and result[0]["clan"] == ""

    def test_variant_key_error_is_skipped(self):
        """KeyError from krcg_card_search for a variant id is caught and skipped."""
        main_card = _make_crypt_card(card_id=1001, variants={1: 2001})

        def _mock_search(key: str | int):
            if key in ("Nathan Turner", 1001):
                return main_card
            raise KeyError(key)

        kh._krcg_loaded = True
        with patch.object(kh, "krcg_card_search", side_effect=_mock_search):
            result = kh.get_all_vamp_variants("Nathan Turner")
        assert len(result) == 1  # 2001 skipped via KeyError

    def test_variant_returns_none_is_skipped(self):
        """None from krcg_card_search for a variant id is skipped."""
        main_card = _make_crypt_card(card_id=1001, variants={1: 2001})

        def _mock_search(key: str | int):
            if key in ("Nathan Turner", 1001):
                return main_card
            return None

        kh._krcg_loaded = True
        with patch.object(kh, "krcg_card_search", side_effect=_mock_search):
            result = kh.get_all_vamp_variants("Nathan Turner")
        assert len(result) == 1  # 2001 skipped (None)

    def test_variant_non_crypt_is_skipped(self):
        """Variant with crypt=False is skipped."""
        lib_card = _make_crypt_card(card_id=2001, crypt=False)
        main_card = _make_crypt_card(card_id=1001, variants={1: 2001})

        def _mock_search(key: str | int):
            if key in ("Nathan Turner", 1001):
                return main_card
            return lib_card

        kh._krcg_loaded = True
        with patch.object(kh, "krcg_card_search", side_effect=_mock_search):
            result = kh.get_all_vamp_variants("Nathan Turner")
        assert len(result) == 1  # lib_card skipped (not crypt)

    def test_variant_bad_group_type_is_skipped(self):
        """TypeError from int(raw_group) is caught and the variant is skipped."""
        bad_card = _make_crypt_card(card_id=2001, group=[1, 2])  # list → int() raises TypeError
        main_card = _make_crypt_card(card_id=1001, variants={1: 2001})

        def _mock_search(key: str | int):
            if key in ("Nathan Turner", 1001):
                return main_card
            return bad_card

        kh._krcg_loaded = True
        with patch.object(kh, "krcg_card_search", side_effect=_mock_search):
            result = kh.get_all_vamp_variants("Nathan Turner")
        assert len(result) == 1  # bad_card skipped (group not int-convertible)

    def test_outer_unexpected_exception_propagates(self):
        """Unexpected exceptions (not KeyError/AttributeError/TypeError/ValueError) propagate."""
        main_card = _make_crypt_card(card_id=1001, variants={})

        def _mock_search(key: str | int):
            if key == "Nathan Turner":
                return main_card
            raise RuntimeError("unexpected!")  # not in the caught set → propagates

        kh._krcg_loaded = True
        import pytest

        with patch.object(kh, "krcg_card_search", side_effect=_mock_search):
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

    def test_direct_hit_returns_card_name(self):
        mock_krcg, _ = _make_krcg_mock(get_return_value=_named_card("Blood Doll"))
        kh._krcg_loaded = True
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            assert kh.canonicalize_card_name("Blood Doll") == "Blood Doll"

    def test_leading_the_fallback(self):
        mock_krcg, mock_vtes = _make_krcg_mock()

        def _get(name: str, default: Any = None):
            return _named_card("Coven, The") if name == "Coven, The" else default

        mock_vtes.VTES.get.side_effect = _get
        kh._krcg_loaded = True
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            assert kh.canonicalize_card_name("The Coven") == "Coven, The"

    def test_trailing_the_fallback(self):
        mock_krcg, mock_vtes = _make_krcg_mock()

        def _get(name: str, default: Any = None):
            return _named_card("Unmasking, The") if name == "Unmasking, The" else default

        mock_vtes.VTES.get.side_effect = _get
        kh._krcg_loaded = True
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            assert kh.canonicalize_card_name("Unmasking") == "Unmasking, The"

    def test_resolves_localized_name(self):
        """A Spanish name resolves (via krcg alias) to the canonical English name."""
        mock_krcg, mock_vtes = _make_krcg_mock()

        def _get(name: str, default: Any = None):
            if name == "Sueños de la Esfinge":
                return _named_card("Dreams of the Sphinx")
            return default

        mock_vtes.VTES.get.side_effect = _get
        kh._krcg_loaded = True
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            assert kh.canonicalize_card_name("Sueños de la Esfinge") == "Dreams of the Sphinx"

    def test_i18n_fallback_loads_translations_when_probe_missing(self):
        """When the probe name does not resolve, load_from_vekn() is attempted once."""
        mock_krcg, mock_vtes = _make_krcg_mock(get_return_value=None)
        kh._krcg_loaded = True
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            result = kh.canonicalize_card_name("Totally Unknown Card")
        assert result == "Totally Unknown Card"
        assert mock_vtes.VTES.load_from_vekn.called

    def test_unresolved_name_returned_unchanged(self):
        mock_krcg, _ = _make_krcg_mock(get_return_value=None)
        kh._krcg_loaded = True
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            assert kh.canonicalize_card_name("Carna, The Princess Bitch") == (
                "Carna, The Princess Bitch"
            )


# ---------------------------------------------------------------------------
# canonical_crypt_name
# ---------------------------------------------------------------------------


def _named_crypt_card(printed_name: str, *, adv: bool = False) -> MagicMock:
    card = MagicMock()
    card.crypt = True
    card.printed_name = printed_name
    card.adv = adv
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
        mock_krcg, _ = _make_krcg_mock(get_return_value=_named_crypt_card("Mina Grotius"))
        kh._krcg_loaded = True
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            assert kh.canonical_crypt_name("Mina Grotius (G3)") == "Mina Grotius"

    def test_resolved_advanced_appends_adv(self):
        mock_krcg, _ = _make_krcg_mock(get_return_value=_named_crypt_card("Tariq", adv=True))
        kh._krcg_loaded = True
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
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
        mock_krcg, _ = _make_krcg_mock(get_return_value=None)
        kh._krcg_loaded = True
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            result = kh.get_library_card_type("Nonexistent")
        assert result is None

    def test_returns_single_type(self):
        mock_card = MagicMock()
        mock_card.types = ["Master"]
        mock_krcg, _ = _make_krcg_mock(get_return_value=mock_card)
        kh._krcg_loaded = True
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            result = kh.get_library_card_type("Blood Doll")
        assert result == "Master"

    def test_returns_sorted_joined_types(self):
        mock_card = MagicMock()
        mock_card.types = ["Combat", "Action"]
        mock_krcg, _ = _make_krcg_mock(get_return_value=mock_card)
        kh._krcg_loaded = True
        with patch.dict(sys.modules, {"krcg": mock_krcg}):
            result = kh.get_library_card_type("Multi-type Card")
        assert result == "Action/Combat"
