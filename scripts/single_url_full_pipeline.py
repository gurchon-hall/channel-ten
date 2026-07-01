"""Run the full scraping pipeline for a single forum URL.

Saves the resulting YAML under twds/ so the output can be inspected visually.
"""

import argparse
import logging
from pathlib import Path

import httpx

from channel_ten._logger import setup_logging
from channel_ten.cli.scrape import RouteCounters, process_tournament, route_tournament
from channel_ten.scraper import DEFAULT_DELAY_SECONDS, HEADERS
from channel_ten.scraper._forum import extract_twd_from_thread

DEFAULT_URL = "https://www.vekn.net/forum/event-reports-and-twd/80827-twd-bleeding-in-wroclaw-wroclaw-poland-22-july-2023"

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?", default=DEFAULT_URL, help="Forum thread URL to scrape.")
    parser.add_argument("--twds-dir", "-o", type=Path, default=Path("twds"), dest="twds_dir")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    setup_logging(args.verbose)

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=60.0) as client:
        tournament = extract_twd_from_thread(client, args.url, delay=args.delay)
        if tournament is None:
            logger.error("No tournament found at %s", args.url)
            return

        logger.info("Parsed: %s", tournament.name)

        tournament, errors = process_tournament(client, tournament, args.delay)

        counters = RouteCounters()
        route_tournament(
            tournament,
            errors,
            icon=None,
            output_dir=args.twds_dir,
            overwrite=args.overwrite,
            counters=counters,
        )

    logger.info(
        "Done — written=%d skipped=%d failed=%d",
        counters.written,
        counters.skipped,
        counters.failed,
    )
    if errors:
        logger.warning("Validation errors: %s", ", ".join(errors))


if __name__ == "__main__":
    main()
