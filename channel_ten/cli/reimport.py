"""CLI subcommand: import.

Backfill layer for decks that exist in the canonical
[GiottoVerducci/TWD](https://github.com/GiottoVerducci/TWD) archive but are
missing from the base (e.g. they were never posted on the VEKN forum the
``scrape`` command covers).

Workflow:
  1. List every ``decks/<event_id>.txt`` file in GiottoVerducci/TWD.
  2. Keep only event ids that are NOT already present anywhere in the output dir.
  3. For each new id: fetch the raw text, parse it, then run the SAME pipeline as
     ``scrape`` (calendar name/winner overrides, VEKN player lookup, krcg
     enrichment, content validation) and route the file to its destination.

The module is named ``importer`` because ``import`` is a Python keyword; the
argparse subcommand is still ``import``.
"""

import argparse
import logging
import os
from pathlib import Path

import httpx

from channel_ten._logger import setup_logging
from channel_ten.cli._common import SubParsersAction
from channel_ten.cli.scrape import RouteCounters, process_tournament, route_tournament
from channel_ten.output.yaml import find_existing_yaml
from channel_ten.parser import parse_twd_text
from channel_ten.publisher import post_twda_issue
from channel_ten.scraper import (
    DEFAULT_DELAY_SECONDS,
    HEADERS,
    fetch_twda_txt,
    list_twda_event_ids,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CLI registration
# ---------------------------------------------------------------------------


def register(sub: SubParsersAction) -> None:
    p = sub.add_parser(
        "import",
        help="Import TWDs from GiottoVerducci/TWD that are not already in the base.",
    )
    p.add_argument(
        "--twds-dir",
        "-o",
        type=Path,
        default=Path("twds"),
        dest="output_dir",
        help=(
            "Base directory; new decks are written to <dir>/YYYY/MM/<event_id>.yaml. "
            "Existing ids anywhere under this tree are skipped. (default: twds)"
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
        help="Re-fetch and reimport decks already in the base, overwriting their files.",
    )
    p.add_argument(
        "--github-token",
        default=None,
        dest="github_token",
        help=(
            "GitHub token used only to raise the rate limit on the deck listing. "
            "Falls back to $GITHUB_TOKEN. Not required."
        ),
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Import at most N new decks (useful for testing).",
    )
    p.add_argument(
        "--create-issue",
        action="store_true",
        default=False,
        dest="create_issue",
        help=(
            "After the run, open a GitHub issue on GiottoVerducci/TWD listing every "
            "event that could not be imported and why. Requires a GitHub token with "
            "public_repo scope (--github-token or $GITHUB_TOKEN)."
        ),
    )
    p.add_argument("--verbose", "-v", action="store_true")
    p.set_defaults(func=run)


# ---------------------------------------------------------------------------
# Command runner
# ---------------------------------------------------------------------------


def run(args: argparse.Namespace) -> int:
    """Import GiottoVerducci/TWD decks whose event_id is not already in the base."""
    setup_logging(args.verbose)

    token = args.github_token or os.environ.get("GITHUB_TOKEN") or None
    output_dir: Path = args.output_dir
    counters = RouteCounters()
    failures: list[tuple[int, str]] = []

    with httpx.Client(headers=HEADERS, timeout=60.0) as client:
        # Step 1: list every deck id in the archive
        try:
            all_ids = list_twda_event_ids(client, token, delay=args.delay)
        except RuntimeError as exc:
            logger.error("%s", exc)
            return 1
        except httpx.HTTPStatusError as exc:
            logger.error("could not list GiottoVerducci/TWD: %s", exc)
            return 1

        # Step 2: keep only ids not already present anywhere in the base,
        # unless --overwrite is set (in which case all ids are candidates).
        if args.overwrite:
            new_ids = list(all_ids)
            existing_count = sum(
                1
                for event_id in all_ids
                if find_existing_yaml(output_dir, f"{event_id}.yaml") is not None
            )
            logger.info(
                "%d deck(s) in GiottoVerducci/TWD, %d already in base (will reimport).",
                len(all_ids),
                existing_count,
            )
        else:
            new_ids = [
                event_id
                for event_id in all_ids
                if find_existing_yaml(output_dir, f"{event_id}.yaml") is None
            ]
            logger.info(
                "%d deck(s) in GiottoVerducci/TWD, %d not in base.",
                len(all_ids),
                len(new_ids),
            )

        if args.limit is not None:
            new_ids = new_ids[: args.limit]
            logger.info("Limiting this run to %d deck(s).", len(new_ids))

        # Step 3: fetch, parse, process and route each new deck
        for event_id in new_ids:
            raw = fetch_twda_txt(client, event_id, delay=args.delay)
            if raw is None:
                logger.warning("%s  (not fetchable — skipped)", event_id)
                failures.append((event_id, "not fetchable"))
                counters.skipped += 1
                continue

            try:
                tournament = parse_twd_text(raw)
            except (ValueError, Exception) as exc:
                logger.error("%s: parse error: %s", event_id, exc)
                logger.debug("Stack trace:", exc_info=True)
                failures.append((event_id, str(exc)))
                counters.failed += 1
                continue

            # GiottoVerducci imports have no forum thread — the source is the
            # event page itself. Without a source URL the deck would be wrongly
            # routed to errors/illegal_header/.
            if not tournament.forum_post_url and tournament.event_url:
                tournament = tournament.model_copy(update={"forum_post_url": tournament.event_url})

            if not tournament.event_id:
                logger.warning("%s  (no event_id — skipped)", event_id)
                counters.skipped += 1
                continue

            tournament, errors = process_tournament(client, tournament, args.delay)
            route_tournament(
                tournament,
                errors,
                icon=None,
                output_dir=output_dir,
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

    if args.create_issue and failures:
        if not token:
            logger.error(
                "--create-issue requires a GitHub token (--github-token or $GITHUB_TOKEN)."
            )
            return 1
        try:
            with httpx.Client(headers=HEADERS, timeout=60.0) as issue_client:
                post_twda_issue(issue_client, failures, token=token)
        except Exception as exc:
            logger.error("Could not create GitHub issue: %s", exc)
            return 1

    return 1 if counters.failed else 0
