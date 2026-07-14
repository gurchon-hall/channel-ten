"""Tests for channel_ten.validator."""

import contextlib
from datetime import date
from typing import Any, cast
from unittest.mock import patch

import pytest

from channel_ten.models import (
    CryptCard,
    Deck,
    LibraryCard,
    LibrarySection,
    Tournament,
)
from channel_ten.validator import (
    _pick_best_crypt_version,  # pyright: ignore[reportPrivateUsage]
    canonicalize_card_names,
    enrich_card_ids,
    enrich_crypt_cards,
    error_types,
    fix_card_sections,
    missing_card_id_errors,
    parse_date_field,
    tda_deck_errors,
    unresolved_card_errors,
)


def _deck(**kwargs: Any) -> Deck:
    defaults: dict[str, Any] = {
        "crypt_count": 2,
        "crypt": [
            CryptCard(
                count=2,
                name="Nathan Turner",
                capacity=4,
                disciplines="PRO ani",
                clan="Gangrel",
                grouping=6,
            )
        ],
        "library_count": 1,
        "library_sections": [
            LibrarySection(
                name="Master",
                count=1,
                cards=[LibraryCard(count=1, name="Blood Doll")],
            )
        ],
    }
    for k, v in kwargs.items():
        if k in Deck.model_fields:
            defaults[k] = v
    return Deck.model_validate(defaults)


def _tournament(**kwargs: Any) -> dict[str, Any]:
    if "deck" in kwargs:
        deck_obj = kwargs["deck"]
        deck_data: Any = (
            deck_obj.model_dump(exclude_none=True) if isinstance(deck_obj, Deck) else deck_obj
        )
    else:
        deck_kw = {k: v for k, v in kwargs.items() if k in Deck.model_fields}
        deck_data = _deck(**deck_kw).model_dump(exclude_none=True)

    base: dict[str, Any] = {
        "name": "Test Event",
        "location": "Paris, France",
        "date_start": date(2023, 3, 25),
        "rounds_format": "3R+F",
        "players_count": 15,
        "winner": "Jane Doe",
        "vekn_number": 1234567,
        "event_url": "https://www.vekn.net/event-calendar/event/9999",
        "forum_post_url": "https://www.vekn.net/forum/event-reports-and-twd/99999-test-event",
        "deck": deck_data,
    }
    for k, v in kwargs.items():
        if k in Tournament.model_fields and k != "deck":
            base[k] = v
    return base


# ---------------------------------------------------------------------------
# Mandatory field checks
# ---------------------------------------------------------------------------


class TestMandatoryFields:
    def test_valid_returns_no_errors(self):
        deck = _deck()
        deck.crypt[0].id = 1
        deck.library_sections[0].cards[0].id = 2
        assert error_types(_tournament(deck=deck)) == []

    def test_missing_name(self):
        assert "illegal_header" in error_types(_tournament(name=""))

    def test_missing_location(self):
        assert "illegal_header" in error_types(_tournament(location=None))

    def test_missing_date_start(self):
        assert "illegal_header" in error_types(_tournament(date_start=None))

    def test_missing_rounds_format(self):
        assert "illegal_header" in error_types(_tournament(rounds_format=""))

    def test_missing_players_count(self):
        assert "illegal_header" in error_types(_tournament(players_count=0))

    def test_missing_winner(self):
        assert "unconfirmed_winner" in error_types(_tournament(winner=""))

    def test_missing_event_url(self):
        assert "illegal_header" in error_types(_tournament(event_url=None))

    def test_missing_forum_post_url_is_allowed(self):
        assert "illegal_header" not in error_types(_tournament(forum_post_url=None))

    def test_empty_forum_post_url_is_allowed(self):
        assert "illegal_header" not in error_types(_tournament(forum_post_url=""))

    def test_limited_format(self):
        assert "limited_format" in error_types(_tournament(name="Limited Edition Cup"))


# ---------------------------------------------------------------------------
# Unconfirmed winner (missing vekn_number)
# ---------------------------------------------------------------------------


class TestUnconfirmedWinner:
    def test_missing_vekn_number_key(self):
        t = _tournament()
        del t["vekn_number"]
        assert "unconfirmed_winner" in error_types(t)

    def test_none_vekn_number(self):
        assert "unconfirmed_winner" in error_types(_tournament(vekn_number=None))

    def test_present_vekn_number(self):
        assert "unconfirmed_winner" not in error_types(_tournament(vekn_number=1234567))

    def test_priority_illegal_header_before_unconfirmed_winner(self):
        """illegal_header should come before unconfirmed_winner in errors list."""
        errors = error_types(_tournament(name="", winner=""))
        assert "illegal_header" in errors
        assert "unconfirmed_winner" in errors
        assert errors.index("illegal_header") < errors.index("unconfirmed_winner")


# ---------------------------------------------------------------------------
# Deck structure checks
# ---------------------------------------------------------------------------


class TestDeckChecks:
    def test_empty_crypt(self):
        deck = _deck(crypt=[])
        assert "illegal_crypt" in error_types(_tournament(deck=deck))

    def test_illegal_crypt_non_consecutive(self):
        deck = _deck(
            crypt_count=3,
            crypt=[
                {
                    "count": 1,
                    "name": "A",
                    "capacity": 4,
                    "disciplines": "PRO",
                    "clan": "Gangrel",
                    "grouping": 4,
                },
                {
                    "count": 1,
                    "name": "B",
                    "capacity": 4,
                    "disciplines": "PRO",
                    "clan": "Gangrel",
                    "grouping": 6,
                },
                {
                    "count": 1,
                    "name": "C",
                    "capacity": 4,
                    "disciplines": "PRO",
                    "clan": "Gangrel",
                    "grouping": 8,
                },
            ],
        )
        assert "illegal_crypt" in error_types(_tournament(deck=deck))

    def test_empty_library(self):
        deck = _deck(library_sections=[])
        assert "illegal_library" in error_types(_tournament(deck=deck))


# ---------------------------------------------------------------------------
# Count consistency checks
# ---------------------------------------------------------------------------


class TestCryptCountMismatch:
    def test_matching_count_no_error(self):
        assert "illegal_crypt" not in error_types(_tournament())

    def test_crypt_count_too_high(self):
        deck = _deck(crypt_count=5)  # actual sum is 2
        assert "illegal_crypt" in error_types(_tournament(deck=deck))

    def test_crypt_count_too_low(self):
        deck = _deck(crypt_count=1)  # actual sum is 2
        assert "illegal_crypt" in error_types(_tournament(deck=deck))

    def test_no_crypt_count_field_skipped(self):
        t = _tournament()
        del t["deck"]["crypt_count"]
        assert "illegal_crypt" not in error_types(t)


class TestLibrarySectionCountMismatch:
    def test_matching_count_no_error(self):
        assert "illegal_library" not in error_types(_tournament())

    def test_section_count_too_high(self):
        deck = _deck(
            library_sections=[
                {
                    "name": "Master",
                    "count": 5,  # actual card sum is 1
                    "cards": [{"count": 1, "name": "Blood Doll"}],
                }
            ]
        )
        assert "illegal_library" in error_types(_tournament(deck=deck))

    def test_section_count_matches_sum(self):
        deck = _deck(
            library_count=3,
            library_sections=[
                {
                    "name": "Master",
                    "count": 3,
                    "cards": [
                        {"count": 2, "name": "Blood Doll"},
                        {"count": 1, "name": "Vessel"},
                    ],
                }
            ],
        )
        assert "illegal_library" not in error_types(_tournament(deck=deck))


class TestLibraryCountMismatch:
    def test_matching_count_no_error(self):
        assert "illegal_library" not in error_types(_tournament())

    def test_library_count_too_high(self):
        deck = _deck(library_count=10)  # sum of sections is 1
        assert "illegal_library" in error_types(_tournament(deck=deck))

    def test_library_count_matches_section_sum(self):
        deck = _deck(
            library_count=3,
            library_sections=[
                {
                    "name": "Master",
                    "count": 2,
                    "cards": [{"count": 2, "name": "Blood Doll"}],
                },
                {
                    "name": "Action",
                    "count": 1,
                    "cards": [{"count": 1, "name": "Govern the Unaligned"}],
                },
            ],
        )
        assert "illegal_library" not in error_types(_tournament(deck=deck))

    def test_no_library_count_field_skipped(self):
        t = _tournament()
        del t["deck"]["library_count"]
        assert "illegal_library" not in error_types(t)


# ---------------------------------------------------------------------------
# Player count floor
# ---------------------------------------------------------------------------


class TestTooFewPlayers:
    def test_exactly_10_ok(self):
        assert "too_few_players" not in error_types(_tournament(players_count=10))

    def test_9_flagged(self):
        assert "too_few_players" in error_types(_tournament(players_count=9))

    def test_zero_not_flagged_as_too_few(self):
        # Zero triggers illegal_header but NOT too_few_players
        assert "too_few_players" not in error_types(_tournament(players_count=0))


# ---------------------------------------------------------------------------
# Date coherence
# ---------------------------------------------------------------------------


class TestDateCoherence:
    def test_matching_date_no_error(self):
        data = _tournament(date_start="2023-03-25")
        assert "incoherent_date" not in error_types(data, calendar_date=date(2023, 3, 25))

    def test_mismatched_date_flagged(self):
        data = _tournament(date_start="2023-03-25")
        assert "incoherent_date" in error_types(data, calendar_date=date(2023, 4, 1))

    def test_no_calendar_date_skipped(self):
        data = _tournament(date_start="2023-03-25")
        assert "incoherent_date" not in error_types(data, calendar_date=None)


# ---------------------------------------------------------------------------
# parse_date_field helper
# ---------------------------------------------------------------------------


class TestParseDateField:
    def test_none_returns_none(self):
        assert parse_date_field(None) is None

    def test_date_passthrough(self):
        d = date(2023, 3, 25)
        assert parse_date_field(d) == d

    def test_iso_string(self):
        assert parse_date_field("2023-03-25") == date(2023, 3, 25)

    def test_invalid_string_returns_none(self):
        assert parse_date_field("not-a-date") is None


# ---------------------------------------------------------------------------
# fix_card_sections
# ---------------------------------------------------------------------------


def _make_deck_with_sections(sections: list[LibrarySection]) -> Deck:
    """Build a minimal Deck with given library_sections."""
    total = sum(s.count for s in sections)
    return Deck.model_validate({"library_count": total, "library_sections": sections})


def _section(name: str, cards: list[LibraryCard]) -> LibrarySection:
    count = sum(c.count for c in cards)
    return LibrarySection(name=name, count=count, cards=cards)


def _card(name: str, count: int = 1) -> LibraryCard:
    return LibraryCard(name=name, count=count)


# Mapping used in tests: card name → krcg section name
_FAKE_KRCG = {
    "Villein": "Master",
    "Govern the Unaligned": "Action",
    "Deflection": "Reaction",
    "Mirror Walk": "Action Modifier",
    "Plasmic Form": "Action Modifier/Combat",
}


def _fake_krcg_section(card_name: str):
    return _FAKE_KRCG.get(card_name)


class TestFixCardSections:
    def _patch_krcg(self, available: bool = True):
        """Return a context-manager stack that fakes krcg availability."""

        @contextlib.contextmanager
        def _ctx():
            krcg_fn = (  # pyright: ignore[reportUnknownVariableType]
                _fake_krcg_section if available else (lambda _: None)  # pyright: ignore[reportUnknownLambdaType]
            )
            with patch(
                "channel_ten.validator.get_library_card_type",
                side_effect=krcg_fn,
            ):
                yield

        return _ctx()

    def test_no_changes_when_sections_correct(self):
        deck = _make_deck_with_sections(
            [
                _section("Master", [_card("Villein", 3)]),
                _section("Action", [_card("Govern the Unaligned", 2)]),
            ]
        )
        with self._patch_krcg():
            fixes = fix_card_sections(deck)
        assert fixes == []
        assert deck.library_sections[0].name == "Master"
        assert deck.library_sections[1].name == "Action"

    def test_moves_card_to_correct_section(self):
        # Govern the Unaligned is in Master — should move to Action
        deck = _make_deck_with_sections(
            [
                _section(
                    "Master",
                    [_card("Villein", 2), _card("Govern the Unaligned", 1)],
                ),
            ]
        )
        with self._patch_krcg():
            fixes = fix_card_sections(deck)

        assert len(fixes) == 1
        assert "'Govern the Unaligned'" in fixes[0]
        assert "'Master'" in fixes[0]
        assert "'Action'" in fixes[0]

        section_names = [s.name for s in deck.library_sections]
        assert "Master" in section_names
        assert "Action" in section_names
        master = next(s for s in deck.library_sections if s.name == "Master")
        assert master.count == 2
        action = next(s for s in deck.library_sections if s.name == "Action")
        assert action.count == 1

    def test_library_count_updated(self):
        deck = _make_deck_with_sections(
            [
                _section(
                    "Master",
                    [_card("Villein", 2), _card("Govern the Unaligned", 1)],
                ),
            ]
        )
        with self._patch_krcg():
            fix_card_sections(deck)
        assert deck.library_count == 3  # unchanged total

    def test_unknown_card_stays_in_current_section(self):
        deck = _make_deck_with_sections([_section("Master", [_card("Some Unknown Card", 1)])])
        with self._patch_krcg():
            fixes = fix_card_sections(deck)
        assert fixes == []
        assert deck.library_sections[0].name == "Master"

    def test_krcg_unavailable_returns_empty(self):
        deck = _make_deck_with_sections([_section("Master", [_card("Govern the Unaligned", 1)])])
        with self._patch_krcg(available=False):
            fixes = fix_card_sections(deck)
        assert fixes == []

    def test_empty_library_sections_returns_empty(self):
        deck = _deck(library_sections=[])
        with self._patch_krcg():
            fixes = fix_card_sections(deck)
        assert fixes == []

    def test_sections_rebuilt_in_type_order(self):
        """After fixing, sections must follow krcg TYPE_ORDER."""
        # Put Reaction before Master deliberately
        deck = _make_deck_with_sections(
            [
                _section("Reaction", [_card("Deflection", 2)]),
                _section("Master", [_card("Villein", 3)]),
            ]
        )
        # Both are already correct, so force a move to trigger rebuild.
        # Put Mirror Walk (Action Modifier) in the Master section.
        deck.library_sections[1].cards.append(LibraryCard(name="Mirror Walk", count=1))
        deck.library_sections[1].count += 1
        deck.library_count += 1

        with self._patch_krcg():
            fixes = fix_card_sections(deck)

        assert fixes  # something was moved
        names = [s.name for s in deck.library_sections]
        # Master should come before Action Modifier, which should come before Reaction
        assert names.index("Master") < names.index("Action Modifier")
        assert names.index("Action Modifier") < names.index("Reaction")


# ---------------------------------------------------------------------------
# enrich_crypt_cards
# ---------------------------------------------------------------------------


def _crypt_card(name: str, count: int = 2, **overrides: Any) -> CryptCard:
    base = CryptCard(
        count=count,
        name=name,
        capacity=0,
        disciplines="",
        title=None,
        clan="Unknown",
        grouping=0,
    )
    for k, v in overrides.items():
        if k in CryptCard.model_fields:
            setattr(base, k, v)
    return base


class TestEnrichCryptCards:
    @pytest.fixture(autouse=True)
    def _inject_krcg(self, fake_crypt_krcg: dict[str, Any]) -> None:
        """Inject a per-test deep copy of the fake krcg data — safe to mutate."""
        self.krcg_data = fake_crypt_krcg

    def _patch_krcg(self, available: bool = True):
        krcg_data = self.krcg_data

        @contextlib.contextmanager
        def _ctx():
            def _lookup(name: str) -> list[CryptCard]:
                data = krcg_data.get(name)
                if data is None:
                    return []
                entries: list[dict[str, Any]] = (
                    cast(list[dict[str, Any]], data) if isinstance(data, list) else [data]
                )
                return [CryptCard(count=0, name=name, **entry) for entry in entries]

            def _fallback(_: str) -> list[CryptCard]:
                return []

            fn = _lookup if available else _fallback
            with patch(
                "channel_ten.validator.get_all_vamp_variants",
                side_effect=fn,
            ):
                yield

        return _ctx()

    def test_enriches_fields_from_krcg(self):
        card = _crypt_card("Nathan Turner", capacity=0, clan="Unknown", grouping=0)
        deck = _deck(crypt=[card])
        with self._patch_krcg():
            fixes = enrich_crypt_cards(deck)
        assert fixes
        assert deck.crypt[0].capacity == 4
        assert deck.crypt[0].disciplines == "PRO ani"
        assert deck.crypt[0].clan == "Gangrel"
        assert deck.crypt[0].grouping == 6
        assert deck.crypt[0].title is None

    def test_path_enriched_from_krcg(self):
        card = _crypt_card("Aaradhya, The Callous Tyrant")
        deck = _deck(crypt=[card])
        with self._patch_krcg():
            enrich_crypt_cards(deck)
        assert deck.crypt[0].path == "Power and the Inner Voice"

    def test_path_is_none_for_non_path_vampires(self):
        """Non-path vampires must have path explicitly set to None after enrichment."""
        card = _crypt_card("Nathan Turner")
        deck = _deck(crypt=[card])
        with self._patch_krcg():
            enrich_crypt_cards(deck)
        assert deck.crypt[0].path is None

    def test_count_and_name_preserved(self):
        card = _crypt_card("Nathan Turner", count=3)
        deck = _deck(crypt=[card])
        with self._patch_krcg():
            enrich_crypt_cards(deck)
        assert deck.crypt[0].count == 3
        assert deck.crypt[0].name == "Nathan Turner"

    def test_title_enriched(self):
        card = _crypt_card("Antón de Concepción", title=None)
        deck = _deck(crypt=[card])
        with self._patch_krcg():
            enrich_crypt_cards(deck)
        assert deck.crypt[0].title == "Prince"

    def test_any_grouping_stored_as_string(self):
        card = _crypt_card("Anarch Convert", grouping=0)
        deck = _deck(crypt=[card])
        with self._patch_krcg():
            enrich_crypt_cards(deck)
        assert deck.crypt[0].grouping == "ANY"

    def test_no_changes_when_already_correct(self):
        card = _crypt_card(
            "Nathan Turner",
            capacity=4,
            disciplines="PRO ani",
            clan="Gangrel",
            grouping=6,
        )
        deck = _deck(crypt=[card])
        with self._patch_krcg():
            fixes = enrich_crypt_cards(deck)
        assert fixes == []

    def test_unknown_card_left_unchanged(self):
        card = _crypt_card("Unknown Vampire", capacity=5, clan="Nosferatu", grouping=3)
        deck = _deck(crypt=[card])
        with self._patch_krcg():
            fixes = enrich_crypt_cards(deck)
        assert fixes == []
        assert deck.crypt[0].capacity == 5
        assert deck.crypt[0].clan == "Nosferatu"

    def test_krcg_unavailable_returns_empty(self):
        card = _crypt_card("Nathan Turner", capacity=0, clan="Unknown")
        deck = _deck(crypt=[card])
        with self._patch_krcg(available=False):
            fixes = enrich_crypt_cards(deck)
        assert fixes == []
        assert deck.crypt[0].capacity == 0  # unchanged

    def test_empty_crypt_returns_empty(self):
        deck = _deck(crypt=[])
        with self._patch_krcg():
            fixes = enrich_crypt_cards(deck)
        assert fixes == []

    def test_base_vampire_not_replaced_by_adv(self):
        """Scraped 'Xaviar' must never be enriched with 'Xaviar (ADV)' data."""
        card = _crypt_card("Xaviar", capacity=0)
        deck = _deck(crypt=[card])
        with self._patch_krcg():
            enrich_crypt_cards(deck)
        # Must use base Xaviar data (capacity=11), not ADV data (capacity=10)
        assert deck.crypt[0].capacity == 11
        assert deck.crypt[0].disciplines == "ANI CEL FOR PRO"
        # Name must not be changed to include "(ADV)"
        assert deck.crypt[0].name == "Xaviar"

    def test_adv_vampire_uses_adv_data(self):
        """Scraped 'Xaviar (ADV)' must be enriched with ADV data, not base data."""
        card = _crypt_card("Xaviar (ADV)", capacity=0)
        deck = _deck(crypt=[card])
        with self._patch_krcg():
            enrich_crypt_cards(deck)
        assert deck.crypt[0].capacity == 10
        assert deck.crypt[0].disciplines == "aus cel pot ABO ANI FOR PRO"
        assert deck.crypt[0].name == "Xaviar (ADV)"

    def test_multi_version_picks_matching_group(self):
        """When a vampire has two grouping versions, pick the one that fits."""
        self.krcg_data["Nathan Turner"] = [
            {
                "capacity": 4,
                "disciplines": "PRO ani",
                "title": None,
                "clan": "Gangrel",
                "grouping": 5,
                "path": None,
            },
            {
                "capacity": 4,
                "disciplines": "PRO ani",
                "title": None,
                "clan": "Gangrel",
                "grouping": 6,
                "path": None,
            },
        ]
        single_card = _crypt_card("Antón de Concepción", grouping=6)
        multi_card = _crypt_card("Nathan Turner", grouping=0)
        deck = _deck(crypt=[single_card, multi_card])
        with self._patch_krcg():
            enrich_crypt_cards(deck)
        assert deck.crypt[1].grouping == 6

    def test_multi_version_fallback_to_first_when_no_match(self):
        """When no version fits the range, use the first version found."""
        self.krcg_data["Nathan Turner"] = [
            {
                "capacity": 4,
                "disciplines": "PRO ani",
                "title": None,
                "clan": "Gangrel",
                "grouping": 3,
                "path": None,
            },
            {
                "capacity": 4,
                "disciplines": "PRO ani",
                "title": None,
                "clan": "Gangrel",
                "grouping": 6,
                "path": None,
            },
        ]
        self.krcg_data["_RefCard_G10"] = {
            "capacity": 5,
            "disciplines": "",
            "title": None,
            "clan": "Gangrel",
            "grouping": 10,
            "path": None,
        }
        single_card = _crypt_card("_RefCard_G10")
        multi_card = _crypt_card("Nathan Turner", grouping=0)
        deck = _deck(crypt=[single_card, multi_card])
        with self._patch_krcg():
            enrich_crypt_cards(deck)
        # G3→{3,10} not consecutive; G6→{6,10} not consecutive → fallback to first (G3)
        assert deck.crypt[1].grouping == 3

    def test_multi_version_no_reference_uses_first(self):
        """When all crypt cards are multi-version, fall back to first version."""
        self.krcg_data["Nathan Turner"] = [
            {
                "capacity": 4,
                "disciplines": "PRO ani",
                "title": None,
                "clan": "Gangrel",
                "grouping": 5,
                "path": None,
            },
            {
                "capacity": 4,
                "disciplines": "PRO ani",
                "title": None,
                "clan": "Gangrel",
                "grouping": 6,
                "path": None,
            },
        ]
        multi_card = _crypt_card("Nathan Turner", grouping=0)
        deck = _deck(crypt=[multi_card])
        with self._patch_krcg():
            enrich_crypt_cards(deck)
        # No fixed reference → fallback to first version (G5)
        assert deck.crypt[0].grouping == 5


# ---------------------------------------------------------------------------
# _pick_best_crypt_version
# ---------------------------------------------------------------------------


class TestPickBestCryptVersion:
    def _v(self, grouping: int) -> CryptCard:
        return CryptCard(
            count=1,
            name="Test",
            capacity=5,
            disciplines="",
            title=None,
            clan="Gangrel",
            grouping=grouping,
        )

    def test_exact_match_preferred(self):
        versions = [self._v(5), self._v(6)]
        best = _pick_best_crypt_version(versions, {6})
        assert best.grouping == 6

    def test_consecutive_extension_chosen(self):
        versions = [self._v(4), self._v(5)]
        best = _pick_best_crypt_version(versions, {6})
        # G5 extends {6} to {5,6} which is consecutive; G4 would give {4,6} which is not
        assert best.grouping == 5

    def test_no_reference_returns_first(self):
        versions = [self._v(3), self._v(7)]
        best = _pick_best_crypt_version(versions, set())
        assert best.grouping == 3

    def test_no_fit_returns_first(self):
        versions = [self._v(3), self._v(7)]
        best = _pick_best_crypt_version(versions, {1})
        assert best.grouping == 3

    def test_any_grouping_only_falls_back(self):
        versions = [
            CryptCard(
                count=1,
                name="Anarch Convert",
                capacity=1,
                disciplines="",
                title=None,
                clan="Caitiff",
                grouping="ANY",
            )
        ]
        best = _pick_best_crypt_version(versions, {5})
        assert best.grouping == "ANY"


# ---------------------------------------------------------------------------
# canonicalize_card_names
# ---------------------------------------------------------------------------


class TestCanonicalizeCardNames:
    def test_rewrites_crypt_and_library_names(self):
        deck = _deck()
        crypt_renames = {"Nathan Turner": "Turner, Nathan"}
        library_renames = {"Blood Doll": "Blood Doll, The"}

        def _rename_crypt(name: str) -> str:
            return crypt_renames.get(name, name)

        def _rename_library(name: str) -> str:
            return library_renames.get(name, name)

        with (
            patch("channel_ten.validator.is_krcg_loaded", return_value=True),
            patch(
                "channel_ten.validator.canonical_crypt_name",
                side_effect=_rename_crypt,
            ),
            patch(
                "channel_ten.validator.canonicalize_card_name",
                side_effect=_rename_library,
            ),
        ):
            fixes = canonicalize_card_names(deck)
        assert deck.crypt[0].name == "Turner, Nathan"
        assert deck.library_sections[0].cards[0].name == "Blood Doll, The"
        assert len(fixes) == 2

    def test_crypt_uses_crypt_canonicalizer_not_library(self):
        deck = _deck()

        def _crypt_alias(_name: str) -> str:
            return "Mina Grotius"

        def _lib_alias(name: str) -> str:
            return name

        with (
            patch("channel_ten.validator.is_krcg_loaded", return_value=True),
            patch(
                "channel_ten.validator.canonical_crypt_name",
                side_effect=_crypt_alias,
            ) as crypt_fn,
            patch(
                "channel_ten.validator.canonicalize_card_name",
                side_effect=_lib_alias,
            ) as lib_fn,
        ):
            canonicalize_card_names(deck)
        assert crypt_fn.called
        crypt_args = {c.args[0] for c in crypt_fn.call_args_list}
        assert "Nathan Turner" in crypt_args
        assert "Nathan Turner" not in {c.args[0] for c in lib_fn.call_args_list}

    def test_no_op_when_krcg_unavailable(self):
        deck = _deck()
        with patch("channel_ten.validator.is_krcg_loaded", return_value=False):
            fixes = canonicalize_card_names(deck)
        assert fixes == []
        assert deck.crypt[0].name == "Nathan Turner"


# ---------------------------------------------------------------------------
# unresolved_card_errors
# ---------------------------------------------------------------------------


class TestUnresolvedCardErrors:
    def test_flags_unresolved_crypt(self):
        deck = _deck()
        deck.crypt[0].name = "Carna, The Princess Bitch"  # unknown to krcg

        def _search_card(name: str) -> object | None:
            return None if "Bitch" in name else object()

        with (
            patch("channel_ten.validator.is_krcg_loaded", return_value=True),
            patch(
                "channel_ten.validator.krcg_card_search",
                side_effect=_search_card,
            ),
        ):
            assert unresolved_card_errors(deck) == ["illegal_crypt"]

    def test_flags_unresolved_library(self):
        deck = _deck()
        deck.library_sections[0].cards[0].name = "Cloak of the Gathering"

        def _search_card(name: str) -> object | None:
            return None if name == "Cloak of the Gathering" else object()

        with (
            patch("channel_ten.validator.is_krcg_loaded", return_value=True),
            patch(
                "channel_ten.validator.krcg_card_search",
                side_effect=_search_card,
            ),
        ):
            assert unresolved_card_errors(deck) == ["illegal_library"]

    def test_no_errors_when_all_resolve(self):
        deck = _deck()
        with (
            patch("channel_ten.validator.is_krcg_loaded", return_value=True),
            patch("channel_ten.validator.krcg_card_search", return_value=object()),
        ):
            assert unresolved_card_errors(deck) == []

    def test_no_errors_when_krcg_unavailable(self):
        deck = _deck()
        with patch("channel_ten.validator.is_krcg_loaded", return_value=False):
            assert unresolved_card_errors(deck) == []


# ---------------------------------------------------------------------------
# enrich_crypt_cards — id attribution
# ---------------------------------------------------------------------------


class TestEnrichCryptCardsId:
    """Verify that enrich_crypt_cards() sets card.id from the best krcg version."""

    @pytest.fixture(autouse=True)
    def _inject_krcg(self, fake_crypt_krcg: dict[str, Any]) -> None:
        self.krcg_data = fake_crypt_krcg

    def _patch_krcg(self):
        krcg_data = self.krcg_data

        @contextlib.contextmanager
        def _ctx():
            def _lookup(name: str) -> list[CryptCard]:
                data = krcg_data.get(name)
                if data is None:
                    return []
                entries: list[dict[str, Any]] = (
                    cast(list[dict[str, Any]], data) if isinstance(data, list) else [data]
                )
                return [CryptCard(count=0, name=name, **entry) for entry in entries]

            with patch("channel_ten.validator.get_all_vamp_variants", side_effect=_lookup):
                yield

        return _ctx()

    def test_id_set_from_krcg(self):
        card = _crypt_card("Nathan Turner", capacity=0, clan="Unknown", grouping=0)
        deck = _deck(crypt=[card])
        with self._patch_krcg():
            enrich_crypt_cards(deck)
        assert deck.crypt[0].id == 200848

    def test_existing_id_not_overwritten(self):
        card = _crypt_card("Nathan Turner", capacity=0, clan="Unknown", grouping=0)
        card.id = 9999
        deck = _deck(crypt=[card])
        with self._patch_krcg():
            enrich_crypt_cards(deck)
        assert deck.crypt[0].id == 9999

    def test_id_stays_none_when_card_unknown(self):
        card = _crypt_card("Unknown Vampire", capacity=5, clan="Nosferatu", grouping=3)
        deck = _deck(crypt=[card])
        with self._patch_krcg():
            enrich_crypt_cards(deck)
        assert deck.crypt[0].id is None


# ---------------------------------------------------------------------------
# enrich_card_ids
# ---------------------------------------------------------------------------


class _FakeKrcgCard:
    """Minimal stand-in for a krcg Card object."""

    def __init__(self, card_id: int) -> None:
        self.id = card_id


class TestEnrichCardIds:
    def _patch(self, available: bool = True, card_id: int | None = 42):
        @contextlib.contextmanager
        def _ctx():
            fake = _FakeKrcgCard(card_id) if card_id is not None else None
            with (
                patch("channel_ten.validator.is_krcg_loaded", return_value=available),
                patch("channel_ten.validator.krcg_card_search", return_value=fake),
            ):
                yield

        return _ctx()

    def test_sets_id_on_library_card(self):
        deck = _deck()
        assert deck.library_sections[0].cards[0].id is None
        with self._patch(card_id=42):
            enrich_card_ids(deck)
        assert deck.library_sections[0].cards[0].id == 42

    def test_skips_card_with_existing_id(self):
        deck = _deck()
        deck.library_sections[0].cards[0].id = 99
        with self._patch(card_id=42):
            enrich_card_ids(deck)
        assert deck.library_sections[0].cards[0].id == 99

    def test_returns_description_of_attributed_ids(self):
        deck = _deck()
        with self._patch(card_id=42):
            result = enrich_card_ids(deck)
        assert result  # at least one description returned

    def test_returns_empty_when_krcg_unavailable(self):
        deck = _deck()
        with self._patch(available=False):
            result = enrich_card_ids(deck)
        assert result == []
        assert deck.library_sections[0].cards[0].id is None

    def test_returns_empty_when_card_not_in_krcg(self):
        deck = _deck()
        with self._patch(card_id=None):
            result = enrich_card_ids(deck)
        assert result == []
        assert deck.library_sections[0].cards[0].id is None


# ---------------------------------------------------------------------------
# missing_card_id_errors
# ---------------------------------------------------------------------------


class TestMissingCardIdErrors:
    def test_returns_error_when_crypt_card_has_no_id(self):
        deck = _deck()
        assert deck.crypt[0].id is None
        with patch("channel_ten.validator.is_krcg_loaded", return_value=True):
            assert missing_card_id_errors(deck) == ["missing_card_id"]

    def test_error_types_reports_missing_card_id(self):
        deck = _deck()
        with patch("channel_ten.validator.is_krcg_loaded", return_value=True):
            assert "missing_card_id" in error_types(_tournament(deck=deck))

    def test_returns_error_when_library_card_has_no_id(self):
        deck = _deck()
        deck.crypt[0].id = 1
        assert deck.library_sections[0].cards[0].id is None
        with patch("channel_ten.validator.is_krcg_loaded", return_value=True):
            assert missing_card_id_errors(deck) == ["missing_card_id"]

    def test_returns_empty_when_all_ids_set(self):
        deck = _deck()
        deck.crypt[0].id = 1
        deck.library_sections[0].cards[0].id = 2
        with patch("channel_ten.validator.is_krcg_loaded", return_value=True):
            assert missing_card_id_errors(deck) == []

    def test_returns_empty_when_krcg_unavailable(self):
        deck = _deck()
        with patch("channel_ten.validator.is_krcg_loaded", return_value=False):
            assert missing_card_id_errors(deck) == []


# ---------------------------------------------------------------------------
# tda_deck_errors
# ---------------------------------------------------------------------------


class TestTdaDeckErrors:
    def test_valid_deck_has_no_errors(self):
        with patch("channel_ten.validator.is_krcg_loaded", return_value=False):
            assert tda_deck_errors(_deck()) == []

    def test_empty_crypt_is_illegal(self):
        deck = _deck(crypt=[])
        assert "illegal_crypt" in tda_deck_errors(deck)

    def test_non_consecutive_groupings_illegal(self):
        deck = _deck(
            crypt_count=2,
            crypt=[
                CryptCard(
                    count=1, name="A", capacity=4, disciplines="PRO", clan="Gangrel", grouping=4
                ),
                CryptCard(
                    count=1, name="B", capacity=4, disciplines="PRO", clan="Gangrel", grouping=8
                ),
            ],
        )
        assert "illegal_crypt" in tda_deck_errors(deck)

    def test_crypt_count_mismatch_illegal(self):
        deck = _deck(crypt_count=5)  # actual sum is 2
        assert "illegal_crypt" in tda_deck_errors(deck)

    def test_empty_library_is_illegal(self):
        deck = _deck(library_sections=[])
        assert "illegal_library" in tda_deck_errors(deck)

    def test_library_section_count_mismatch_illegal(self):
        deck = _deck(
            library_sections=[
                LibrarySection(
                    name="Master", count=5, cards=[LibraryCard(count=1, name="Blood Doll")]
                )
            ]
        )
        assert "illegal_library" in tda_deck_errors(deck)

    def test_library_count_mismatch_illegal(self):
        deck = _deck(library_count=5)  # actual section sum is 1
        assert "illegal_library" in tda_deck_errors(deck)

    def test_missing_card_id_reported_when_krcg_loaded(self):
        deck = _deck()
        with patch("channel_ten.validator.is_krcg_loaded", return_value=True):
            assert "missing_card_id" in tda_deck_errors(deck)
