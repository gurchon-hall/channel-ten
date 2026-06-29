"""CLI subcommand: scrape.

Scraping workflow:
  1. Scrape forum data (fetch thread HTML).
  2. Parse data (extract Tournament from post text).
  3. Check event calendar for the tournament name.
  4. Check event calendar for the winner's name.
  5. Look up the winner in the VEKN player registry for their VEKN number.
  6. Validate card information with the krcg library.
  7. Validate content and route files to the appropriate destination.

Steps 3-7 are exposed as :func:`process_tournament` and :func:`route_tournament`
so the ``import`` subcommand can reuse the exact same pipeline.
"""

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from channel_ten._logger import setup_logging
from channel_ten.cli._common import SubParsersAction
from channel_ten.models import Tournament
from channel_ten.output import write_tournament_yaml
from channel_ten.output.yaml import tournament_to_yaml_str
from channel_ten.scraper import (
    DEFAULT_DELAY_SECONDS,
    HEADERS,
    ICON_MERGED,
    fetch_event_date,
    fetch_event_name,
    fetch_event_winner,
    fetch_player,
    scrape_forum,
)
from channel_ten.validator import (
    enrich_crypt_cards,
    error_types,
    fix_card_sections,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Serialization helper
# ---------------------------------------------------------------------------


def serialize_tournament(obj: Tournament) -> dict[str, Any]:
    """Convert a Tournament Pydantic model to a plain dict, excluding None values."""
    return obj.model_dump(exclude_none=True)


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------


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
        calendar_winner = fetch_event_winner(client, tournament.event_url, delay=delay)
        if calendar_winner is None:
            logger.debug("No results data on event page: %s", tournament.event_url)
            return tournament, True
        if calendar_winner != tournament.winner:
            logger.debug(
                "Calendar winner override: %r → %r  (%s)",
                tournament.winner,
                calendar_winner,
                tournament.event_url,
            )
            return tournament.model_copy(update={"winner": calendar_winner}), False
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

    if crypt_fixes:
        logger.debug("%s  crypt enriched:\n%s", tournament.yaml_filename, "\n".join(crypt_fixes))
    if section_fixes:
        logger.debug("%s  sections fixed:\n%s", tournament.yaml_filename, "\n".join(section_fixes))

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


# ---------------------------------------------------------------------------
# Shared pipeline orchestration and routing (reused by the import subcommand)
# ---------------------------------------------------------------------------


@dataclass
class RouteCounters:
    """Tallies for a processing run, shared across subcommands."""

    written: int = 0
    skipped: int = 0
    failed: int = 0
    overwrite_skipped: int = 0


def process_tournament(
    client: httpx.Client,
    tournament: Tournament,
    delay: float,
) -> tuple[Tournament, list[str]]:
    """Run pipeline steps 3-6 and return the enriched tournament and its errors.

    The returned ``errors`` list includes ``"unconfirmed_winner"`` when the event
    has a calendar URL but the calendar page has no results/standings data yet.
    """
    # Step 3: check event calendar for the tournament name
    tournament = _check_calendar_name(client, tournament, delay)

    # Step 4: check event calendar for the winner's name
    tournament, calendar_winner_missing = _check_calendar_winner(client, tournament, delay)

    # Step 5: look up winner in VEKN player registry
    tournament = _lookup_player(client, tournament, delay)

    # Step 6: validate card information with krcg
    tournament = _enrich_with_krcg(tournament)

    # Step 7a: validate content
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


# ---------------------------------------------------------------------------
# CLI registration
# ---------------------------------------------------------------------------


def register(sub: SubParsersAction) -> None:
    p = sub.add_parser("scrape", help="Scrape the VEKN forum and write YAML files.")
    p.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=Path("twds"),
        dest="output_dir",
        help="Root directory; files are written to <dir>/YYYY/MM/<event_id>.yaml. (default: twds)",
    )

    p.add_argument(
        "--start-page",
        type=int,
        default=0,
        dest="start_page",
        help="Forum index page to start scraping from, 0-indexed (default: 0).",
    )
    p.add_argument(
        "--last-page",
        type=int,
        default=None,
        dest="last_page",
        help=("Last forum index page to scrape, 0-indexed inclusive (default: scrape all pages)."),
    )
    p.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY_SECONDS,
        help=f"Seconds between HTTP requests (default: {DEFAULT_DELAY_SECONDS}).",
    )
    p.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing YAML files.",
    )
    p.add_argument("--verbose", "-v", action="store_true")
    p.set_defaults(func=run)


# ---------------------------------------------------------------------------
# Command runner
# ---------------------------------------------------------------------------


def run(args: argparse.Namespace) -> int:
    """Scrape the VEKN forum and export each TWD as a YAML file.

    Scraping workflow per tournament:
      1. Scrape forum data (fetch thread HTML).
      2. Parse data (extract Tournament from post text).
      3-7. Enrich, validate and route via :func:`process_tournament` /
           :func:`route_tournament`.
    """
    setup_logging(args.verbose)

    max_pages: int | None = None
    if args.last_page is not None:
        max_pages = args.last_page - args.start_page + 1

    counters = RouteCounters()

    with httpx.Client(headers=HEADERS, timeout=60.0) as client:
        # Steps 1-2: scrape forum data and parse it into Tournament objects
        for tournament, icon in scrape_forum(
            client,
            max_pages=max_pages,
            start_page=args.start_page,
            delay=args.delay,
        ):
            if not tournament.event_id:
                logger.warning("%r  (no event_id — skipped)", tournament.name)
                counters.skipped += 1
                continue

            # Steps 3-6: enrich and validate
            tournament, errors = process_tournament(client, tournament, args.delay)

            # Step 7: route file to the appropriate destination
            route_tournament(
                tournament,
                errors,
                icon=icon,
                output_dir=args.output_dir,
                overwrite=args.overwrite,
                counters=counters,
            )

    logger.info(
        "Done — %d written, %d skipped, %d failed",
        counters.written,
        counters.skipped,
        counters.failed,
    )
    if counters.overwrite_skipped:
        logger.warning(
            "%d deck(s) already existed and were not overwritten "
            "(use --overwrite to replace them).",
            counters.overwrite_skipped,
        )
    return 1 if counters.failed else 0
