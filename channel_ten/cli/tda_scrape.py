"""CLI subcommand: tda-scrape.

Scraping workflow for TDA (Tournament Deck Archive — every participant's deck,
not just the winner's):
  1. List every archive in smeea/vdb's ``frontend/public/tournaments/`` folder.
  2. For each archive: fetch the zip, parse ``archon.xlsx`` for event metadata,
     and parse each participant's deck ``.txt``.
  3. Resolve each deck's author to a VEKN number (:func:`~channel_ten.pipeline_tda.resolve_author`).
  4-5. Enrich and validate via :func:`~channel_ten.pipeline_tda.process_tda_deck`.
  6. Route each deck file via :func:`~channel_ten.pipeline_tda.route_tda_deck`.
"""

import argparse
import logging
import os
from pathlib import Path

import httpx

from channel_ten._logger import setup_logging
from channel_ten.cli._common import SubParsersAction, vekn_login_from_env
from channel_ten.models import TdaDeck
from channel_ten.parser import parse_tda_deck_text
from channel_ten.pipeline import RouteCounters
from channel_ten.pipeline_tda import process_tda_deck, resolve_author, route_tda_deck
from channel_ten.scraper import (
    DEFAULT_DELAY_SECONDS,
    HEADERS,
    VDB_RAW_BASE,
    fetch_tda_archive,
    iter_tda_deck_texts,
    list_tda_archive_ids,
    parse_archon_xlsx,
    read_archon_xlsx,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CLI registration
# ---------------------------------------------------------------------------


def register(sub: SubParsersAction) -> None:
    p = sub.add_parser(
        "tda-scrape",
        help="Scrape smeea/vdb Tournament Deck Archives and write YAML files.",
    )
    p.add_argument(
        "--tda-dir",
        "-o",
        type=Path,
        default=Path("tda"),
        dest="tda_dir",
        help=(
            "Root directory; files are written to "
            "<dir>/YYYY/MM/<event_id>/<author_id>.yaml. (default: tda)"
        ),
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
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N archives (useful for testing).",
    )
    p.add_argument(
        "--github-token",
        default=None,
        dest="github_token",
        help=(
            "GitHub token used only to raise the rate limit on the archive listing. "
            "Falls back to $GITHUB_TOKEN. Not required."
        ),
    )
    p.add_argument("--verbose", "-v", action="store_true")
    p.set_defaults(func=run)


# ---------------------------------------------------------------------------
# Command runner
# ---------------------------------------------------------------------------


def run(args: argparse.Namespace) -> int:
    """Scrape smeea/vdb Tournament Deck Archives and export each deck as a YAML file."""
    setup_logging(args.verbose)

    token = args.github_token or os.environ.get("GITHUB_TOKEN") or None
    counters = RouteCounters()

    with httpx.Client(headers=HEADERS, timeout=60.0) as client:
        vekn_login_from_env(client, args.delay)

        try:
            archive_ids = list_tda_archive_ids(client, token, delay=args.delay)
        except RuntimeError as exc:
            logger.error("%s", exc)
            return 1
        except httpx.HTTPStatusError as exc:
            logger.error("could not list smeea/vdb: %s", exc)
            return 1

        if args.limit is not None:
            archive_ids = archive_ids[: args.limit]

        logger.info("%d archive(s) to process.", len(archive_ids))

        for archive_id in archive_ids:
            zip_bytes = fetch_tda_archive(client, archive_id, delay=args.delay)
            if zip_bytes is None:
                logger.warning("%s  (not fetchable — skipped)", archive_id)
                counters.skipped += 1
                continue

            try:
                meta = parse_archon_xlsx(read_archon_xlsx(zip_bytes))
            except Exception as exc:
                logger.error("%s: could not parse archon.xlsx: %s", archive_id, exc)
                logger.debug("Stack trace:", exc_info=True)
                counters.failed += 1
                continue

            event_url = (
                f"https://www.vekn.net/event-calendar/event/{archive_id}"
                if archive_id.isdigit()
                else None
            )
            archive_url = f"{VDB_RAW_BASE}/{archive_id}.zip"

            for filename, deck_text in iter_tda_deck_texts(zip_bytes):
                try:
                    deck = parse_tda_deck_text(deck_text)
                except (ValueError, Exception) as exc:
                    logger.error("%s/%s: parse error: %s", archive_id, filename, exc)
                    logger.debug("Stack trace:", exc_info=True)
                    counters.failed += 1
                    continue

                raw_author = deck.created_by or ""
                if not raw_author:
                    logger.warning("%s/%s  (no author — skipped)", archive_id, filename)
                    counters.skipped += 1
                    continue

                author, author_vekn_number = resolve_author(client, raw_author, args.delay)

                entry = TdaDeck(
                    event_id=archive_id,
                    name=meta.name,
                    location=meta.location,
                    date_start=meta.date_start,
                    rounds_format=meta.rounds_format,
                    players_count=meta.players_count,
                    winner=meta.winner,
                    winner_vekn_number=meta.winner_vekn_number,
                    event_url=event_url,
                    archive_url=archive_url,
                    author=author,
                    author_vekn_number=author_vekn_number,
                    deck=deck,
                )

                entry, errors = process_tda_deck(entry)
                route_tda_deck(
                    entry,
                    errors,
                    output_dir=args.tda_dir,
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
