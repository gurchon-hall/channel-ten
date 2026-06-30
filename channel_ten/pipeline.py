"""Shared tournament-processing pipeline used by the scrape and import subcommands.

Enriches a parsed Tournament via VEKN calendar lookups and krcg card data,
then validates and routes the output file to the correct destination.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

from channel_ten.models import Tournament
from channel_ten.output import write_tournament_yaml
from channel_ten.output.yaml import tournament_to_yaml_str
from channel_ten.scraper import (
    ICON_MERGED,
    fetch_event_date,
    fetch_event_name,
    fetch_event_winner,
    fetch_player,
)
from channel_ten.validator import (
    enrich_card_ids,
    enrich_crypt_cards,
    error_types,
    fix_card_sections,
)

logger = logging.getLogger(__name__)


@dataclass
class RouteCounters:
    """Tallies for a processing run, shared across subcommands."""

    written: int = 0
    skipped: int = 0
    failed: int = 0
    overwrite_skipped: int = 0


def _check_calendar_name(
    client: httpx.Client,
    tournament: Tournament,
    delay: float,
) -> Tournament:
    """Step 3: override the tournament name with the official VEKN calendar name."""
    if not tournament.event_url:
        return tournament
    try:
        calendar_name = fetch_event_name(client, tournament.event_url, delay=delay)
        if calendar_name is None:
            logger.debug("No name data on event page: %s", tournament.event_url)
            return tournament
        if calendar_name != tournament.name:
            logger.debug(
                "Calendar name override: %r → %r  (%s)",
                tournament.name,
                calendar_name,
                tournament.event_url,
            )
            return tournament.model_copy(update={"name": calendar_name})
    except Exception as exc:
        logger.warning(
            "Could not fetch calendar name for %s: %s",
            tournament.event_url,
            exc,
        )
    return tournament


def _check_calendar_winner(
    client: httpx.Client,
    tournament: Tournament,
    delay: float,
) -> tuple[Tournament, bool]:
    """Step 3: override the winner with the official VEKN calendar standings.

    Returns ``(tournament, calendar_winner_missing)`` where
    ``calendar_winner_missing`` is ``True`` when the event URL is set but the
    calendar page has no results/standings data yet.
    """
    if not tournament.event_url:
        return tournament, False
    try:
        result = fetch_event_winner(client, tournament.event_url, delay=delay)
        if result is None:
            logger.debug("No results data on event page: %s", tournament.event_url)
            return tournament, True
        calendar_winner, calendar_vekn_id = result
        updates: dict[str, object] = {}
        if calendar_winner != tournament.winner:
            logger.debug(
                "Calendar winner override: %r → %r  (%s)",
                tournament.winner,
                calendar_winner,
                tournament.event_url,
            )
            updates["winner"] = calendar_winner
        if calendar_vekn_id is not None and tournament.vekn_number is None:
            updates["vekn_number"] = calendar_vekn_id
        if updates:
            return tournament.model_copy(update=updates), False
    except Exception as exc:
        logger.warning(
            "Could not fetch calendar winner for %s: %s",
            tournament.event_url,
            exc,
        )
    return tournament, False


def _lookup_player(
    client: httpx.Client,
    tournament: Tournament,
    delay: float,
) -> Tournament:
    """Step 4: look up winner in the VEKN player registry."""
    if tournament.vekn_number is not None:
        return tournament

    winner = tournament.winner

    try:
        result = fetch_player(client, winner, delay=delay)
    except Exception as exc:
        logger.warning("Player lookup failed for %r: %s", winner, exc)
        return tournament

    if result is None:
        logger.warning("%s  winner not found in VEKN: %r", tournament.yaml_filename, winner)
        return tournament

    canonical_name, vekn_number = result
    if canonical_name != winner:
        logger.info(
            "%s  winner coerced: %r → %r  (VEKN %s)",
            tournament.yaml_filename,
            winner,
            canonical_name,
            vekn_number,
        )
    return tournament.model_copy(update={"winner": canonical_name, "vekn_number": vekn_number})


def _enrich_with_krcg(tournament: Tournament) -> Tournament:
    """Step 5: validate and enrich crypt and library cards via krcg."""
    if not tournament.deck:
        return tournament

    crypt_fixes = enrich_crypt_cards(tournament.deck)
    section_fixes = fix_card_sections(tournament.deck)
    id_fixes = enrich_card_ids(tournament.deck)

    if crypt_fixes:
        logger.debug("%s  crypt enriched:\n%s", tournament.yaml_filename, "\n".join(crypt_fixes))
    if section_fixes:
        logger.debug("%s  sections fixed:\n%s", tournament.yaml_filename, "\n".join(section_fixes))
    if id_fixes:
        logger.debug("%s  card ids enriched:\n%s", tournament.yaml_filename, "\n".join(id_fixes))

    return tournament


def _validate_content(
    client: httpx.Client,
    tournament: Tournament,
    delay: float,
) -> list[str]:
    """Step 6: validate tournament content and return a list of error-type strings."""
    calendar_date = None
    if tournament.event_url:
        try:
            calendar_date = fetch_event_date(client, tournament.event_url, delay=delay)
        except Exception as exc:
            logger.warning(
                "Could not fetch calendar date for %s: %s",
                tournament.event_url,
                exc,
            )

    errors = error_types(tournament.model_dump(exclude_none=True), calendar_date=calendar_date)
    if errors:
        logger.debug(
            "Validation errors for %s: %s",
            tournament.yaml_filename,
            errors,
        )
    return errors


def process_tournament(
    client: httpx.Client,
    tournament: Tournament,
    delay: float,
) -> tuple[Tournament, list[str]]:
    """Run pipeline steps 3-6 and return the enriched tournament and its errors.

    The returned ``errors`` list includes ``"unconfirmed_winner"`` when the event
    has a calendar URL but the calendar page has no results/standings data yet.
    """
    tournament = _check_calendar_name(client, tournament, delay)
    tournament, calendar_winner_missing = _check_calendar_winner(client, tournament, delay)
    tournament = _lookup_player(client, tournament, delay)
    tournament = _enrich_with_krcg(tournament)
    errors = _validate_content(client, tournament, delay)
    if calendar_winner_missing:
        errors.append("unconfirmed_winner")
    return tournament, errors


def route_tournament(
    tournament: Tournament,
    errors: list[str],
    icon: str | None,
    output_dir: Path,
    overwrite: bool,
    counters: RouteCounters,
) -> None:
    """Step 7b: write the tournament to the appropriate destination.

    Routing rules:
      * validation errors  → ``output_dir/errors/<first_error>/<event_id>.yaml``
      * merged forum icon  → ``output_dir/changes_required/<event_id>.yaml``
      * otherwise          → ``output_dir/YYYY/MM/<event_id>.yaml`` (and any stale
        ``changes_required`` copy is removed)

    Mutates *counters* in place.
    """
    changes_required_dir = output_dir / "changes_required"

    if errors:
        error_dir = output_dir / "errors" / errors[0]
        error_dir.mkdir(parents=True, exist_ok=True)
        path = error_dir / tournament.yaml_filename
        try:
            path.write_text(tournament_to_yaml_str(tournament), encoding="utf-8")
            logger.warning(
                "%s  %s  (errors: %s)",
                path.name,
                tournament.name,
                ", ".join(errors),
            )
            counters.written += 1
        except Exception as exc:
            logger.error("%s: %s", tournament.event_id, exc)
            logger.debug("Stack trace:", exc_info=True)
            counters.failed += 1
    elif icon == ICON_MERGED:
        changes_required_dir.mkdir(parents=True, exist_ok=True)
        path = changes_required_dir / tournament.yaml_filename
        try:
            path.write_text(tournament_to_yaml_str(tournament), encoding="utf-8")
            logger.info("%s  %s  (changes required)", path.name, tournament.name)
            counters.written += 1
        except Exception as exc:
            logger.error("%s: %s", tournament.event_id, exc)
            logger.debug("Stack trace:", exc_info=True)
            counters.failed += 1
    else:
        try:
            path = write_tournament_yaml(
                tournament,
                output_dir,
                overwrite=overwrite,
            )
            logger.info("%s  %s", path.name, tournament.name)
            counters.written += 1

            stale = changes_required_dir / tournament.yaml_filename
            if stale.exists():
                stale.unlink()
                logger.info("removed stale changes_required/%s", stale.name)
        except FileExistsError as exc:
            logger.debug("%s", exc)
            counters.skipped += 1
            counters.overwrite_skipped += 1
        except Exception as exc:
            logger.error("%s: %s", tournament.event_id, exc)
            logger.debug("Stack trace:", exc_info=True)
            counters.failed += 1
