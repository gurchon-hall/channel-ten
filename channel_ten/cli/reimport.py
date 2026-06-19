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

from channel_ten.cli._common import SubParsersAction, console, setup_logging
from channel_ten.cli.scrape import RouteCounters, process_tournament, route_tournament
from channel_ten.output.yaml import find_existing_yaml
from channel_ten.parser import parse_twd_text
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
        "--output-dir",
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
        help="Overwrite existing YAML files.",
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

    with httpx.Client(headers=HEADERS, timeout=60.0) as client:
        # Step 1: list every deck id in the archive
        try:
            all_ids = list_twda_event_ids(client, token, delay=args.delay)
        except RuntimeError as exc:
            console.print(f"[red]Error:[/red] {exc}")
            return 1
        except httpx.HTTPStatusError as exc:
            console.print(f"[red]Error:[/red] could not list GiottoVerducci/TWD: {exc}")
            return 1

        # Step 2: keep only ids not already present anywhere in the base
        new_ids = [
            event_id
            for event_id in all_ids
            if find_existing_yaml(output_dir, f"{event_id}.yaml") is None
        ]
        console.print(
            f"{len(all_ids)} deck(s) in GiottoVerducci/TWD, "
            f"[cyan]{len(new_ids)}[/cyan] not in base."
        )

        if args.limit is not None:
            new_ids = new_ids[: args.limit]
            console.print(f"[dim]Limiting this run to {len(new_ids)} deck(s).[/dim]")

        # Step 3: fetch, parse, process and route each new deck
        for event_id in new_ids:
            raw = fetch_twda_txt(client, event_id, delay=args.delay)
            if raw is None:
                console.print(
                    f"[yellow]─[/yellow] {event_id}  [dim](not fetchable — skipped)[/dim]"
                )
                counters.skipped += 1
                continue

            try:
                tournament = parse_twd_text(raw)
            except (ValueError, Exception) as exc:
                console.print(f"[red]✗[/red] {event_id}: parse error: {exc}")
                logger.debug("Stack trace:", exc_info=True)
                counters.failed += 1
                continue

            # GiottoVerducci imports have no forum thread — the source is the
            # event page itself. Without a source URL the deck would be wrongly
            # routed to errors/illegal_header/.
            if not tournament.forum_post_url and tournament.event_url:
                tournament = tournament.model_copy(update={"forum_post_url": tournament.event_url})

            if not tournament.event_id:
                console.print(f"[yellow]─[/yellow] {event_id}  [dim](no event_id — skipped)[/dim]")
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

    console.rule()
    console.print(
        f"Done — [green]{counters.written} written[/green], "
        f"[yellow]{counters.skipped} skipped[/yellow], "
        f"[red]{counters.failed} failed[/red]"
    )
    if counters.overwrite_skipped:
        console.print(
            f"[yellow]![/yellow] {counters.overwrite_skipped} deck(s) already existed "
            f"and were not overwritten (use --overwrite to replace them)."
        )
    return 1 if counters.failed else 0
