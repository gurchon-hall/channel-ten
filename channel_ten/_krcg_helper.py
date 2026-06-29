import logging
import re
from typing import Any

from channel_ten.models import CryptCard

logger = logging.getLogger(__name__)

# Previously imported from krcg.config; removed in krcg 5.0.
TYPE_ORDER: list[str] = [
    "Master",
    "Conviction",
    "Action",
    "Action/Combat",
    "Action/Reaction",
    "Ally",
    "Equipment",
    "Political Action",
    "Retainer",
    "Power",
    "Action Modifier",
    "Action Modifier/Combat",
    "Action Modifier/Reaction",
    "Reaction",
    "Combat",
    "Combat/Reaction",
    "Event",
]

_krcg_loaded: bool | None = None
_i18n_ensured: bool = False
_cards: Any = None  # krcg.collections.CardDict once loaded
_i18n_lookup: dict[str, int] = {}  # localized_name → card.id, built lazily
_seen_cards: set[str | int] = set()
_cards_loaded: dict[str | int, Any] = {}

_LEADING_THE_RE = re.compile(r"^[Tt]he\s+(.+)$")
# Trailing crypt group marker, e.g. " (G3)" or " (G6 ADV)". The group number is
# stored separately in the YAML, so the group part is redundant — and a bare "(G3)"
# left in the name breaks the exact-match resolution done by downstream consumers.
# An ``ADV`` flag inside the marker is kept (re-emitted as " (ADV)") so an advanced
# vampire is not silently downgraded to its base version. A lone "(ADV)" never
# matches and is left intact.
_GROUP_SUFFIX_RE = re.compile(r"\s*\(G\d+(?P<adv>\s+ADV)?\)\s*$", re.IGNORECASE)


def _strip_group_suffix(name: str) -> str:
    """Drop a trailing ``(G#)`` group marker from *name*, preserving any ADV flag."""
    return _GROUP_SUFFIX_RE.sub(lambda m: " (ADV)" if m.group("adv") else "", name).strip()


def is_krcg_loaded() -> bool:
    """Check if the KRCG module is available."""
    global _krcg_loaded, _cards
    if _krcg_loaded is not None:
        return _krcg_loaded

    try:
        from krcg import (
            load as _krcg_load,  # pyright: ignore[reportAttributeAccessIssue, reportUnknownVariableType] # noqa: PLC0415
        )

        _cards = _krcg_load()  # pyright: ignore[reportUnknownVariableType]
        _krcg_loaded = True
    except ImportError as exc:
        logger.debug("krcg unavailable — card-section check skipped: %s", exc)
        _krcg_loaded = False
    return _krcg_loaded


def krcg_card_search(card_name_or_id: str | int) -> Any:
    """Search for a card by name or id in krcg's card database.

    Returns a krcg ``Card`` object, or ``None`` when the card is not found.
    Typed as ``Any`` because krcg is an optional dependency whose ``Card``
    class cannot be imported unconditionally.
    """
    if not is_krcg_loaded():
        return None

    if card_name_or_id in _seen_cards:
        return _cards_loaded.get(card_name_or_id)

    try:
        card = _cards[card_name_or_id]
    except KeyError:
        card = None
    _seen_cards.add(card_name_or_id)
    _cards_loaded[card_name_or_id] = card
    if not card:
        logger.debug("Error searching for card '%s' in krcg", card_name_or_id)

    return card


def _ensure_i18n_loaded() -> None:
    """Build a localized-name → card.id lookup from the loaded krcg card data.

    In krcg 5.0, translated names (es-ES, fr-FR, …) are stored in each card's
    ``i18n`` field but are not indexed in ``CardDict`` for direct lookup. This
    function iterates every card once and builds ``_i18n_lookup`` so that
    ``canonicalize_card_name`` can still resolve a localized name to its English
    card. Runs at most once; failures are swallowed.
    """
    global _i18n_ensured, _i18n_lookup
    if _i18n_ensured or not is_krcg_loaded():
        return
    _i18n_ensured = True

    try:
        for card in _cards.cards():
            for _, translation in card.i18n.items():
                name = getattr(translation, "name", None)
                if name:
                    _i18n_lookup[name] = card.id
    except Exception as exc:
        logger.debug("Could not build i18n lookup from krcg data: %s", exc)


def canonicalize_card_name(name: str) -> str:
    """Return krcg's canonical spelling for *name*, or *name* unchanged.

    Resolution order (each step returns the matched card's ``printed_name``):

    1. Direct lookup.
    2. Leading-"The" reorder: ``The Coven`` → ``Coven, The``.
    3. Trailing ", The": ``Unmasking`` → ``Unmasking, The``.
    4. i18n fallback: localized names (e.g. ``Sueños de la Esfinge``) resolve via
       a pre-built i18n index to the English card.

    Returns the input unchanged when krcg is unavailable or no variant resolves
    (genuine forum typos and unknown names are left for downstream flagging).
    """
    if not is_krcg_loaded():
        return name

    card = krcg_card_search(name)
    if card:
        return str(card.printed_name)

    m = _LEADING_THE_RE.match(name)
    if m:
        card = krcg_card_search(f"{m.group(1)}, The")
        if card:
            return str(card.printed_name)

    if not name.endswith(", The"):
        card = krcg_card_search(f"{name}, The")
        if card:
            return str(card.printed_name)

    _ensure_i18n_loaded()
    card_id = _i18n_lookup.get(name)
    if card_id is not None:
        card = krcg_card_search(card_id)
        if card:
            return str(card.printed_name)

    return name


def canonical_crypt_name(name: str) -> str:
    """Return the canonical *bare* crypt name for *name* (no group suffix).

    Crypt cards are stored with their group in a separate ``grouping`` field, so the
    name must not carry krcg's ``(G#)`` / ``(G# ADV)`` suffix (``Card.full_name``
    includes it). A lone ``(ADV)`` suffix is kept — downstream consumers use it to
    flag the advanced version.

    When krcg resolves *name* (including localized or suffixed spellings), the card's
    ``printed_name`` is returned (krcg's official spelling, e.g. ``The Horde``), plus
    ``" (ADV)"`` for advanced cards. Otherwise the input is returned with any trailing
    ``(G#)`` group marker stripped, leaving a bare name for genuine typos / unknown
    cards.
    """
    if is_krcg_loaded():
        card = krcg_card_search(name)
        if not card:
            _ensure_i18n_loaded()
            card_id = _i18n_lookup.get(name)
            if card_id is not None:
                card = krcg_card_search(card_id)
        if card and card.kind == "Crypt":
            return str(card.printed_name) + (" (ADV)" if card.advanced else "")

    return _strip_group_suffix(name)


def get_all_vamp_variants(vamp_name: str) -> list[CryptCard]:
    """Return krcg data for all relevant grouping versions of a crypt card by name.

    Iterates the full card database to find every crypt card sharing the same
    ``printed_name`` as *vamp_name*, filtering to only non-ADV or only ADV versions
    (matching the presence of "(ADV)" in *vamp_name*). ADV and non-ADV are never
    mixed:

    - ``"Xaviar"``       → only base (non-ADV) Xaviar versions
    - ``"Xaviar (ADV)"`` → only ADV Xaviar versions

    Returns an empty list if the card is not found in krcg or is not a crypt card.
    """
    _ensure_i18n_loaded()
    card = krcg_card_search(vamp_name)
    if not card or card.kind != "Crypt":
        return []

    want_adv: bool = "(ADV)" in vamp_name
    target_printed_name: str = card.printed_name

    try:
        result: list[CryptCard] = []
        for candidate in _cards.cards():
            if candidate.kind != "Crypt":
                continue
            if candidate.printed_name != target_printed_name:
                continue
            if bool(candidate.advanced) != want_adv:
                continue

            raw_group = candidate.group
            if not raw_group:
                continue
            grouping: int | str
            if str(raw_group) == "Any":
                grouping = "ANY"
            else:
                try:
                    grouping = int(str(raw_group)[1:])  # "G3" → 3
                except TypeError, ValueError:
                    continue

            disciplines = " ".join(candidate.disciplines) if candidate.disciplines else ""
            clan: str = candidate.clan or ""
            _path = getattr(candidate, "path", None)
            result.append(
                CryptCard(
                    count=0,
                    name=target_printed_name,
                    capacity=candidate.capacity,
                    disciplines=disciplines,
                    title=str(candidate.title) if candidate.title else None,
                    clan=clan,
                    grouping=grouping,
                    path=_path if _path else None,
                )
            )

        return result
    except KeyError, AttributeError, TypeError, ValueError:
        return []


def get_library_card_type(card_name: str) -> str | None:
    """Return the canonical section name for a library card according to krcg, or
    ``None`` if the card is not in the database.

    The section name is the card's types joined by ``"/"`` in alphabetical order,
    matching krcg's ``TYPE_ORDER`` convention (e.g. ``"Action/Combat"``).
    """
    card = krcg_card_search(card_name)
    if not card:
        return None
    return "/".join(sorted(str(t) for t in card.types))
