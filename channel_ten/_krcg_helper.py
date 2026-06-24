import logging
import re
from typing import Any

from channel_ten.models import Crypt_Card_Dict

_logger = logging.getLogger(__name__)


try:
    from krcg.config import TYPE_ORDER as TYPE_ORDER
except ImportError:
    TYPE_ORDER: list[str] = []  # type: ignore[no-redef]

_krcg_loaded: bool | None = None
_i18n_ensured: bool = False
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


# A known Spanish card name used only to probe whether translated-name aliases
# are present in the loaded krcg data ("Dreams of the Sphinx").
_I18N_PROBE_NAME = "Sueños de la Esfinge"


def is_krcg_loaded() -> bool:
    """Check if the KRCG module is available."""
    global _krcg_loaded
    if _krcg_loaded is not None:
        return _krcg_loaded

    try:
        from krcg import vtes as _kv  # noqa: PLC0415

        _kv.VTES.load()
        _krcg_loaded = True
    except ImportError as exc:
        _logger.debug("krcg unavailable — card-section check skipped: %s", exc)
        _krcg_loaded = False
    return _krcg_loaded


def krcg_card_search(card_name_or_id: str | int) -> Any:
    """Search for a card by name in KRCG's VTES database.

    Returns a krcg ``Card`` object, or ``None`` when the card is not found.
    Typed as ``Any`` because krcg is an optional dependency whose ``Card``
    class cannot be imported unconditionally.
    """
    if not is_krcg_loaded():
        return None

    from krcg import vtes as _kv  # noqa: PLC0415

    if card_name_or_id in _seen_cards:
        return _cards_loaded.get(card_name_or_id)

    card = _kv.VTES.get(card_name_or_id, None)
    _seen_cards.add(card_name_or_id)
    _cards_loaded[card_name_or_id] = card
    if not card:
        _logger.debug("Error searching for card '%s' in KRCG", card_name_or_id)

    return card


def _ensure_i18n_loaded() -> None:
    """Best-effort: ensure translated card-name aliases are available.

    krcg registers every translated card name (es-ES, fr-FR, …) as an alias, so a
    plain lookup resolves a localized name to its English card. The KRCG static
    data loaded by ``VTES.load()`` includes translations for krcg>=4.0; if it does
    not (older builds), fall back to ``load_from_vekn()`` which always loads them.

    Failures are swallowed — English-only resolution still works and any name that
    stays unresolved is flagged for manual review downstream. Runs at most once.
    """
    global _i18n_ensured
    if _i18n_ensured or not is_krcg_loaded():
        return
    _i18n_ensured = True

    from krcg import vtes as _kv  # noqa: PLC0415

    if _kv.VTES.get(_I18N_PROBE_NAME, None):
        return  # translations already present in the static data

    try:
        _kv.VTES.load_from_vekn()
        # Re-querying is required: cached misses from the English-only data are stale.
        _seen_cards.clear()
        _cards_loaded.clear()
    except Exception as exc:
        _logger.debug("Could not load krcg i18n data from vekn.net: %s", exc)


def canonicalize_card_name(name: str) -> str:
    """Return krcg's canonical spelling for *name*, or *name* unchanged.

    Resolution order (each step returns the matched card's canonical ``name``):

    1. Direct lookup.
    2. Leading-"The" reorder: ``The Coven`` → ``Coven, The``.
    3. Trailing ", The": ``Unmasking`` → ``Unmasking, The``.
    4. i18n fallback: localized names (e.g. ``Sueños de la Esfinge``) resolve via
       krcg's translated-name aliases to the English card.

    Returns the input unchanged when krcg is unavailable or no variant resolves
    (genuine forum typos and unknown names are left for downstream flagging).
    """
    if not is_krcg_loaded():
        return name

    card = krcg_card_search(name)
    if card:
        return card.name

    m = _LEADING_THE_RE.match(name)
    if m:
        card = krcg_card_search(f"{m.group(1)}, The")
        if card:
            return card.name

    if not name.endswith(", The"):
        card = krcg_card_search(f"{name}, The")
        if card:
            return card.name

    _ensure_i18n_loaded()
    card = krcg_card_search(name)
    if card:
        return card.name

    return name


def canonical_crypt_name(name: str) -> str:
    """Return the canonical *bare* crypt name for *name* (no group suffix).

    Crypt cards are stored with their group in a separate ``grouping`` field, so the
    name must not carry krcg's ``(G#)`` / ``(G# ADV)`` suffix (``Card.name`` includes
    it). A lone ``(ADV)`` suffix is kept — downstream consumers use it to flag the
    advanced version.

    When krcg resolves *name* (including localized or suffixed spellings), the card's
    ``printed_name`` is returned (krcg's official spelling, e.g. ``The Horde``), plus
    ``" (ADV)"`` for advanced cards. Reconciling that spelling to a particular
    reference dataset's sort order is the consumer's responsibility. Otherwise the
    input is returned with any trailing ``(G#)`` group marker stripped, leaving a
    bare name for genuine typos / unknown cards.
    """
    if is_krcg_loaded():
        card = krcg_card_search(name)
        if not card:
            _ensure_i18n_loaded()
            card = krcg_card_search(name)
        if card and card.crypt:
            return card.printed_name + (" (ADV)" if card.adv else "")

    return _strip_group_suffix(name)


def get_all_vamp_variants(vamp_name: str) -> list[Crypt_Card_Dict]:
    """
    Return krcg data for all relevant grouping versions of a crypt card by name.

    When a vampire exists in multiple groupings (e.g. G5 and G6), each non-ADV
    version is returned as a separate dict (for a non-ADV lookup), or each ADV
    version (for an ADV lookup).  ADV and non-ADV are never mixed:

    - ``"Xaviar"``       → only base (non-ADV) Xaviar versions
    - ``"Xaviar (ADV)"`` → only ADV Xaviar versions

    Returns an empty list if the card is not found in krcg.

    Each returned dict contains:
    - ``capacity``    - blood capacity (int)
    - ``disciplines`` - space-separated discipline string, e.g. ``"PRO ani cel"``
    - ``title``       - title string or ``None``
    - ``clan``        - primary clan name string
    - ``grouping``    - group number (int) or ``"ANY"`` for group-independent cards
    - ``path``        - V5 Sabbat path string or ``None`` (requires a krcg build
      that exposes ``Card.path``; degrades to ``None`` otherwise)
    """
    card = krcg_card_search(vamp_name)
    if not card or not card.crypt:
        return []

    # Determine whether the scraped name is an ADV card. This is a heuristic but
    # should be reliable since the presence of "(ADV)" in the name is a strong
    # signal of the card's identity and krcg's data is consistent in this regard.
    want_adv: bool = "(ADV)" in vamp_name

    # Gather all variant IDs: the card itself plus all related grouping variants
    all_ids: set[int] = {card.id}
    all_ids.update(card.variants.values())

    try:
        result: list[Crypt_Card_Dict] = []
        for card_id in all_ids:
            try:
                card_from_id = krcg_card_search(card_id)
            except KeyError:
                continue
            if not card_from_id:
                continue
            if not card_from_id.crypt:
                continue
            # Skip variants that don't match the ADV/non-ADV kind of the lookup
            if bool(card_from_id.adv) != want_adv:
                continue
            disciplines = " ".join(card_from_id.disciplines) if card_from_id.disciplines else ""
            clan: str = card_from_id.clans[0] if card_from_id.clans else ""
            raw_group = card_from_id.group
            if not raw_group:
                continue
            grouping: int | str
            if raw_group == "ANY":
                grouping = "ANY"
            else:
                try:
                    grouping = int(raw_group)
                except TypeError, ValueError:
                    continue
            _path = getattr(card_from_id, "path", None)
            entry: Crypt_Card_Dict = {
                "id": card_from_id.id,
                "capacity": card_from_id.capacity,
                "disciplines": disciplines,
                "title": card_from_id.title or None,
                "clan": clan,
                "grouping": grouping,
                "path": _path if _path else None,  # coerce "" to None
            }
            result.append(entry)

        return result
    except KeyError, AttributeError, TypeError, ValueError:
        return []


def get_library_card_type(card_name: str) -> str | None:
    """
    Return the canonical section name for a library card according to krcg, or
    ``None`` if the card is not in the database.

    The section name is the card's types joined by ``"/"`` in alphabetical order,
    matching krcg's ``TYPE_ORDER`` convention (e.g. ``"Action/Combat"``).
    """
    card = krcg_card_search(card_name)
    if not card:
        return None
    return "/".join(sorted(card.types))
