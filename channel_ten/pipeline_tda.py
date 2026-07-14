"""TDA-specific processing pipeline: enrich, validate and route one deck at a time.

Parallels :mod:`channel_ten.pipeline` (TWD) and reuses its ``RouteCounters`` plus
the krcg enrichment functions in :mod:`channel_ten.validator` unchanged, but
diverges where TDA is structurally different: event metadata comes from
``archon.xlsx`` (an already-submitted VEKN tournament report), so there is no
VEKN-calendar cross-check step here the way there is for forum-scraped TWD
entries, and one archive yields many decks instead of one.
"""

import logging
from pathlib import Path

import httpx

from channel_ten.models import TdaDeck
from channel_ten.output.tda_yaml import tda_deck_to_yaml_str, write_tda_deck_yaml
from channel_ten.pipeline import RouteCounters
from channel_ten.scraper import fetch_player, fetch_player_by_id
from channel_ten.validator import (
    enrich_card_ids,
    enrich_crypt_cards,
    fix_card_sections,
    tda_deck_errors,
)

logger = logging.getLogger(__name__)


def resolve_author(client: httpx.Client, raw_author: str, delay: float) -> tuple[str, int | None]:
    """Resolve a deck's raw ``Author:`` field to a display name and VEKN number.

    Numeric values are VEKN member numbers already; the canonical name is fetched
    from the player registry by id (:func:`channel_ten.scraper.fetch_player_by_id`).
    Non-numeric values (a player name) are resolved via the same by-name lookup used
    for TWD winners (:func:`channel_ten.scraper.fetch_player`). Either way, if the
    lookup fails the raw value is kept as the name and a warning logged — the deck is
    still written (never dropped), under a slugified filename when no VEKN number was
    resolvable.

    Caveat: a numeric id is not proof of a *real* VEKN registration — Archon assigns
    small placeholder numbers for online-event participants without one (see
    ``docs/tda_pipeline.md``), and those can collide with an unrelated real player's
    low id. The resolved name is only as trustworthy as the source id.
    """
    raw_author = raw_author.strip()
    if raw_author.isdigit():
        vekn_number = int(raw_author)
        try:
            name = fetch_player_by_id(client, vekn_number, delay=delay)
        except Exception as exc:
            logger.warning("Player registry lookup failed for id %s: %s", vekn_number, exc)
            return raw_author, vekn_number
        if name is None:
            logger.warning("VEKN id %s not found in player registry", vekn_number)
            return raw_author, vekn_number
        return name, vekn_number

    try:
        result = fetch_player(client, raw_author, delay=delay)
    except Exception as exc:
        logger.warning("Player lookup failed for %r: %s", raw_author, exc)
        return raw_author, None

    if result is None:
        logger.warning("TDA author not found in VEKN registry: %r", raw_author)
        return raw_author, None

    canonical_name, vekn_number = result
    return canonical_name, vekn_number


def process_tda_deck(entry: TdaDeck) -> tuple[TdaDeck, list[str]]:
    """Enrich *entry*'s deck via krcg and return it with its validation errors.

    Also syncs ``deck.created_by`` to *entry*'s already-resolved ``author`` name
    (:func:`resolve_author`) — the parser only ever sets it to the deck's raw
    ``Author:`` line, which for a numeric author is not human-readable.
    """
    entry.deck.created_by = entry.author
    crypt_fixes = enrich_crypt_cards(entry.deck)
    section_fixes = fix_card_sections(entry.deck)
    id_fixes = enrich_card_ids(entry.deck)
    if crypt_fixes:
        logger.debug("%s  crypt enriched:\n%s", entry.yaml_filename, "\n".join(crypt_fixes))
    if section_fixes:
        logger.debug("%s  sections fixed:\n%s", entry.yaml_filename, "\n".join(section_fixes))
    if id_fixes:
        logger.debug("%s  card ids enriched:\n%s", entry.yaml_filename, "\n".join(id_fixes))

    errors = tda_deck_errors(entry.deck)
    return entry, errors


def route_tda_deck(
    entry: TdaDeck,
    errors: list[str],
    output_dir: Path,
    overwrite: bool,
    counters: RouteCounters,
) -> None:
    """Write *entry* to ``output_dir/YYYY/MM/<event_id>/<author_id>.yaml``, or
    ``output_dir/errors/<first_error>/<event_id>_<author_id>.yaml`` when invalid.

    Mutates *counters* in place.
    """
    if errors:
        error_dir = output_dir / "errors" / errors[0]
        error_dir.mkdir(parents=True, exist_ok=True)
        path = error_dir / f"{entry.event_id}_{entry.yaml_filename}"
        try:
            path.write_text(tda_deck_to_yaml_str(entry), encoding="utf-8")
            logger.warning("%s  %s  (errors: %s)", path.name, entry.name, ", ".join(errors))
            counters.written += 1
        except Exception as exc:
            logger.error("%s/%s: %s", entry.event_id, entry.author, exc)
            logger.debug("Stack trace:", exc_info=True)
            counters.failed += 1
        return

    try:
        path = write_tda_deck_yaml(entry, output_dir, overwrite=overwrite)
        logger.info("%s  %s (%s)", path, entry.name, entry.author)
        counters.written += 1
    except FileExistsError as exc:
        logger.debug("%s", exc)
        counters.skipped += 1
        counters.overwrite_skipped += 1
    except Exception as exc:
        logger.error("%s/%s: %s", entry.event_id, entry.author, exc)
        logger.debug("Stack trace:", exc_info=True)
        counters.failed += 1
