"""CLI subcommand: scrape.

Scraping workflow:
  1. Scrape forum data (fetch thread HTML).
  2. Parse data (extract Tournament from post text).
  3-7. Enrich, validate and route via :mod:`channel_ten.pipeline`.
"""

import argparse
import logging
from pathlib import Path

import httpx

from channel_ten._logger import setup_logging
from channel_ten.cli._common import SubParsersAction, vekn_login_from_env
from channel_ten.output.yaml import find_existing_yaml
from channel_ten.pipeline import RouteCounters, process_tournament, route_tournament
from channel_ten.scraper import (
    DEFAULT_DELAY_SECONDS,
    HEADERS,
    is_twda_import,
    scrape_forum,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CLI registration
# ---------------------------------------------------------------------------


def register(sub: SubParsersAction) -> None:
    p = sub.add_parser("scrape", help="Scrape the VEKN forum and write YAML files.")
    p.add_argument(
        "--twds-dir",
        "-o",
        type=Path,
        default=Path("twds"),
        dest="twds_dir",
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
      3-7. Enrich, validate and route via :func:`~channel_ten.pipeline.process_tournament` /
           :func:`~channel_ten.pipeline.route_tournament`.
    """
    setup_logging(args.verbose)

    max_pages: int | None = None
    if args.last_page is not None:
        max_pages = args.last_page - args.start_page + 1

    counters = RouteCounters()

    with httpx.Client(headers=HEADERS, timeout=60.0) as client:
        vekn_login_from_env(client, args.delay)

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

            # TWDA-imported events must never be overwritten by the forum scraper —
            # the archive is the authoritative source; use `import` to refresh them.
            existing = find_existing_yaml(args.twds_dir, tournament.yaml_filename)
            if existing is not None and is_twda_import(existing):
                logger.debug("%s  (TWDA import — skipped by scrape)", tournament.event_id)
                counters.skipped += 1
                continue

            # Steps 3-6: enrich and validate
            tournament, errors = process_tournament(client, tournament, args.delay)

            # Step 7: route file to the appropriate destination
            route_tournament(
                tournament,
                errors,
                icon=icon,
                output_dir=args.twds_dir,
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
