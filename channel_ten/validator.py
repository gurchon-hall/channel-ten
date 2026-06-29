"""Pure validation logic for VTES TWD YAML files.
Enrichment functions (enrich_crypt_cards, fix_card_sections,
canonicalize_card_names, unresolved_card_errors) operate on Pydantic Deck /
CryptCard / LibrarySection / LibraryCard models and mutate them in-place.

error_types() accepts a raw dict[str, Any] (as loaded from YAML) so it can
detect missing or structurally invalid fields before Pydantic validation.

Error types
-----------
Mandatory tournament fields
  illegal_header     : any of name, location, date_start, rounds_format,
                       players_count, or event_url is absent or blank
                       (forum_post_url is optional — hand-crafted files may omit it)
  unconfirmed_winner : winner is absent/blank, or vekn_number is absent/None
  limited_format     : tournament name contains "Limited" (draft/limited event)

Mandatory deck fields
  illegal_crypt  : deck.crypt is empty, crypt groupings are not a pair of
                   consecutive integers, or deck.crypt_count != sum of card counts
                   (cards with grouping==ANY are ignored in the grouping check)
  illegal_library: deck.library_sections is empty, a section count != sum of
                   its card counts, or deck.library_count != sum of section counts

Player count
  too_few_players : players_count is present but below MIN_PLAYERS (default 12, env-configurable)

Date coherence (requires a calendar_date from the VEKN event calendar)
  incoherent_date : date_start in the file does not match the official date

When multiple errors are present the first one (in the order listed above)
determines the error directory used by the CLI validate command.
"""

import logging
import os
from datetime import date
from typing import Any, cast

from channel_ten._krcg_helper import (
    TYPE_ORDER,
    canonical_crypt_name,
    canonicalize_card_name,
    get_all_vamp_variants,
    get_library_card_type,
    is_krcg_loaded,
    krcg_card_search,
)
from channel_ten.models import (
    CryptCard,
    Deck,
    LibraryCard,
    LibrarySection,
    Tournament,
)

logger = logging.getLogger(__name__)
MIN_PLAYERS: int = int(os.getenv("MIN_PLAYERS", "12"))

# Fields copied from krcg into a scraped CryptCard; count and name are
# preserved from the scraped data and never overwritten.
_ENRICH_FIELDS: frozenset[str] = frozenset(
    {"capacity", "disciplines", "title", "clan", "grouping", "path"}
)

# ---------------------------------------------------------------------------
# krcg card-section validation helpers
# ---------------------------------------------------------------------------


def _pick_best_crypt_version(versions: list[CryptCard], reference_groups: set[int]) -> CryptCard:
    """Pick the grouping version that best fits the established group range.

    Grouping rule: all non-ANY groups must form a set of at most 2 consecutive integers.
    Priority:
      1. Version whose group is already present in *reference_groups* (exact match).
      2. Version whose group extends *reference_groups* to at most 2 consecutive ints.
      3. First integer-grouped version found (fallback).
    """
    int_versions = [v for v in versions if isinstance(v.grouping, int)]
    if not int_versions:
        return versions[0]

    if reference_groups:
        for v in int_versions:
            if isinstance(v.grouping, int) and v.grouping in reference_groups:
                return v

        for v in int_versions:
            if not isinstance(v.grouping, int):
                continue
            candidate = reference_groups | {v.grouping}
            c_sorted = sorted(candidate)
            if len(c_sorted) <= 2 and c_sorted[-1] - c_sorted[0] <= 1:
                return v

    return int_versions[0]


def enrich_crypt_cards(deck: Deck) -> list[str]:
    """Enrich crypt card data using krcg card database.

    For each crypt card, look it up in krcg and update ``capacity``,
    ``disciplines``, ``title``, ``clan``, ``grouping``, and ``path`` from the
    database.  ``count`` and ``name`` are always preserved from the scraped
    data.  Cards not found in krcg are left unchanged.

    When a vampire exists in multiple groupings, the version whose group fits
    the grouping rules of the rest of the crypt is used (two consecutive
    integers at most, e.g. G5-G6).  If no version fits, the first one found
    is used.

    ADV and non-ADV versions are never mixed.

    Mutates *deck* in-place.  Returns a list of human-readable descriptions
    of the changes made (empty when no changes were needed or krcg is
    unavailable).
    """
    if not deck.crypt:
        return []

    all_versions: list[list[CryptCard]] = [get_all_vamp_variants(card.name) for card in deck.crypt]

    fixed_groups: set[int] = set()
    for versions in all_versions:
        if len(versions) == 1 and isinstance(versions[0].grouping, int):
            fixed_groups.add(versions[0].grouping)

    fixes: list[str] = []
    for card, versions in zip(deck.crypt, all_versions):
        if not versions:
            continue
        best = (
            _pick_best_crypt_version(versions, fixed_groups) if len(versions) > 1 else versions[0]
        )
        changed: list[str] = []
        for field in _ENRICH_FIELDS:
            new_value = getattr(best, field)
            old_value = getattr(card, field)
            if old_value != new_value:
                setattr(card, field, new_value)
                changed.append(f"{field}: {old_value!r} → {new_value!r}")
        if changed:
            fixes.append(f"  {card.name!r}: " + ", ".join(changed))

    return fixes


def fix_card_sections(deck: Deck) -> list[str]:
    """Validate and fix library card sections using krcg card type data.

    For each library card, look it up in krcg and check whether it is in the
    correct section (section name == ``"/".join(sorted(card.types))``).
    Misassigned cards are moved to the correct section; cards that krcg cannot
    identify are left in their current section.

    Mutates *deck* in-place — ``library_sections`` is replaced with a rebuilt
    list when corrections are needed, and ``library_count`` is kept consistent.

    Returns a list of human-readable fix descriptions (empty when no changes
    were made or when krcg is unavailable).
    """
    if not deck.library_sections:
        return []

    all_cards: list[tuple[str, LibraryCard]] = []
    fixes: list[str] = []
    any_moved = False

    for section in deck.library_sections:
        section_name = section.name or ""
        is_nameless = not section_name
        for card in section.cards:
            card_name = card.name or ""
            expected = get_library_card_type(card_name)
            if expected is not None and expected != section_name:
                fixes.append(f"  {card_name!r}: {section_name!r} → {expected!r}")
                all_cards.append((expected, card))
                any_moved = True
            elif is_nameless:
                # Card in a nameless section krcg couldn't type: flag for
                # removal; the count mismatch surfaces via illegal_library.
                any_moved = True
            else:
                all_cards.append((section_name, card))

    if not any_moved:
        return []

    type_order: list[str] = TYPE_ORDER

    def _order(name: str) -> int:
        try:
            return type_order.index(name)
        except ValueError:
            return len(type_order)

    sections_map: dict[str, list[LibraryCard]] = {}
    for section_name, card in all_cards:
        sections_map.setdefault(section_name, []).append(card)

    new_sections: list[LibrarySection] = []
    for section_name in sorted(sections_map, key=_order):
        if not section_name:
            continue
        cards = sections_map[section_name]
        new_sections.append(
            LibrarySection(name=section_name, count=sum(c.count for c in cards), cards=cards)
        )

    deck.library_sections = new_sections
    deck.library_count = sum(s.count for s in new_sections)

    return fixes


def _iter_crypt_cards(deck: Deck) -> list[CryptCard]:
    """Return every crypt card in *deck* (mutable references)."""
    return deck.crypt


def _iter_library_cards(deck: Deck) -> list[LibraryCard]:
    """Return every library card in *deck* (mutable references)."""
    return [card for section in deck.library_sections for card in section.cards]


def canonicalize_card_names(deck: Deck) -> list[str]:
    """Rewrite crypt and library card names to krcg's canonical spelling.

    Library cards resolve leading-"The" word order, typographic apostrophes, and
    localized (i18n) names to their canonical English form. Crypt cards resolve to
    the *bare* printed name (no ``(G#)`` suffix, ``(ADV)`` preserved) since the group
    is stored separately. Names krcg cannot resolve are left unchanged. Mutates
    *deck* in place; returns human-readable descriptions of the renames (empty when
    krcg is unavailable or nothing changed).
    """
    if not is_krcg_loaded():
        return []

    fixes: list[str] = []
    for card in _iter_crypt_cards(deck):
        old_name = card.name or ""
        if not old_name:
            continue
        new_name = canonical_crypt_name(old_name)
        if new_name != old_name:
            card.name = new_name
            fixes.append(f"  {old_name!r} → {new_name!r}")
    for lib_card in _iter_library_cards(deck):
        old_name = lib_card.name or ""
        if not old_name:
            continue
        new_name = canonicalize_card_name(old_name)
        if new_name != old_name:
            lib_card.name = new_name
            fixes.append(f"  {old_name!r} → {new_name!r}")
    return fixes


def unresolved_card_errors(deck: Deck) -> list[str]:
    """Flag decks whose card names do not resolve in krcg, for manual review.

    Returns ``["illegal_crypt"]`` and/or ``["illegal_library"]`` when any crypt or
    library card name (after canonicalization) is unknown to krcg. Returns ``[]``
    when krcg is unavailable, so offline runs never produce false positives.
    """
    if not is_krcg_loaded():
        return []

    errors: list[str] = []
    if deck.crypt and any(not krcg_card_search(c.name) for c in deck.crypt):
        errors.append("illegal_crypt")

    library_cards = _iter_library_cards(deck)
    if any(not krcg_card_search(c.name) for c in library_cards):
        errors.append("illegal_library")

    return errors


def parse_date_field(raw: date | str | None) -> date | None:
    """Coerce whatever ruamel.yaml hands back for date_start into a date."""
    if raw is None:
        return None
    if isinstance(raw, date):
        return raw
    try:
        return Tournament.parse_date(raw)
    except ValueError:
        return None


def error_types(data: dict[str, Any], calendar_date: date | None = None) -> list[str]:
    """Return a list of validation error-type strings for one YAML file."""
    errors: list[str] = []

    # --- Mandatory tournament fields ---
    if (
        not data.get("name")
        or not data.get("location")
        or data.get("date_start") is None
        or not data.get("rounds_format")
        or not data.get("players_count")
        or not data.get("event_url")
    ):
        errors.append("illegal_header")
    if not data.get("winner") or not data.get("vekn_number"):
        errors.append("unconfirmed_winner")
    name_val: str = data.get("name") or ""
    if "limited" in name_val.lower():
        errors.append("limited_format")

    # --- Mandatory deck fields ---
    deck_raw: dict[str, Any] = data.get("deck") or {}
    crypt_list = cast(list[dict[str, Any]], deck_raw.get("crypt") or [])
    illegal_crypt = False
    if not crypt_list:
        illegal_crypt = True
    else:
        groupings: set[int] = set()
        for card in crypt_list:
            g = card.get("grouping")
            if isinstance(g, int):
                groupings.add(g)
        if len(groupings) > 2 or (len(groupings) == 2 and max(groupings) - min(groupings) != 1):
            illegal_crypt = True
        crypt_count = deck_raw.get("crypt_count")
        if crypt_count is not None:
            expected_crypt = sum(card.get("count", 0) for card in crypt_list)
            if crypt_count != expected_crypt:
                illegal_crypt = True
    if illegal_crypt:
        errors.append("illegal_crypt")
    if not deck_raw.get("library_sections"):
        errors.append("illegal_library")

    # --- Deck count consistency ---
    illegal_library = False
    if deck_raw:
        lib_sections = cast(list[dict[str, Any]], deck_raw.get("library_sections") or [])
        for section in lib_sections:
            section_cards = cast(list[dict[str, Any]], section.get("cards") or [])
            section_count = section.get("count")
            if section_count and section_cards:
                expected_section = sum(c.get("count", 0) for c in section_cards)
                if section_count != expected_section:
                    illegal_library = True
                    break

        library_count = deck_raw.get("library_count")
        if lib_sections and library_count is not None:
            expected_library = sum(s.get("count", 0) for s in lib_sections)
            if library_count != expected_library:
                illegal_library = True
    if illegal_library:
        errors.append("illegal_library")

    # --- Player count floor ---
    players_count: int = data.get("players_count") or 0
    if 0 < players_count < MIN_PLAYERS:
        errors.append("too_few_players")

    # --- Date coherence (only when calendar_date was fetched) ---
    if calendar_date is not None:
        file_date = parse_date_field(data.get("date_start"))
        if file_date is not None and file_date != calendar_date:
            errors.append("incoherent_date")

    return errors
