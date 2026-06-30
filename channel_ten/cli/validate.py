"""CLI subcommand: validate.

Re-applies the full scraping validation pipeline to all published tournament
YAML files:

  1. Rescrape the forum post (forum_post_url) for fresh tournament data.
  2. Fetch the canonical winner name and VEKN number from the event calendar.
  3. Enrich crypt cards and fix library card sections via krcg.
  4. Fetch the official event date from the VEKN calendar for date-coherence.
  4b. If --force-date is set and the calendar date differs from date_start,
      overwrite date_start with the calendar date (marks file dirty).
  5. Run the full error_types() check (illegal_header, unconfirmed_winner,
     limited_format, illegal_crypt, illegal_library, too_few_players,
     incoherent_date).
  6. Move files that still have errors to twds/errors/<first_error>/.
     Files without errors that were modified in place are written back.

Scans all YAML files under twds/ except the ``changes_required/`` directory.
Files in ``errors/`` are also re-validated so that previously failing files can
be recovered when the underlying issue (e.g. missing calendar results) is fixed.
"""

import argparse
import datetime
import logging
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import httpx
from ruamel.yaml import YAML

from channel_ten._logger import setup_logging
from channel_ten.cli._common import SubParsersAction
from channel_ten.models import Deck
from channel_ten.output.yaml import reorder_tournament_dict
from channel_ten.scraper._forum import extract_twd_from_thread
from channel_ten.scraper._http import DEFAULT_DELAY_SECONDS, HEADERS
from channel_ten.scraper._vekn import fetch_event_date, fetch_event_winner, fetch_player
from channel_ten.validator import (
    canonicalize_card_names,
    enrich_card_ids,
    enrich_crypt_cards,
    error_types,
    fix_card_sections,
    parse_date_field,
)

logger = logging.getLogger(__name__)

# Error dir is rechecked every time to see if errors have been fixed
# and can be removed; so we skip only tournaments flagged as "changes_required"
# to avoid moving them back and forth.
SKIP_DIRS = {"changes_required"}
_FAST_VALIDATION_YAML_FILES_NUMBER_THRESHOLD = 25

# Name of the opt-out file placed at the root of the eternal-vigilance checkout
# (sibling of the twds/ directory).  One event ID per line; lines starting with
# '#' are treated as comments and ignored.
SKIP_EVENTS_FILENAME = "skip_events.txt"


def register(sub: SubParsersAction) -> None:
    p = sub.add_parser(
        "validate",
        help="Re-validate all published tournament YAML files.",
        description=__doc__,
    )
    p.add_argument(
        "--full-validation",
        action="store_true",
        default=False,
        help="Perform a full validation of all tournaments (default: False).",
    )
    p.add_argument(
        "--errors-only",
        action="store_true",
        default=False,
        dest="errors_only",
        help="Validate only files currently in the errors/ subdirectory.",
    )
    p.add_argument(
        "--twds-dir",
        type=Path,
        default=Path("twds"),
        help="Root twds directory (default: twds)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report; do not move or update files.",
    )
    p.add_argument(
        "--force-date",
        action="store_true",
        default=False,
        dest="force_date",
        help="Overwrite date_start with the date fetched from the VEKN event calendar.",
    )
    p.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging.")
    p.set_defaults(func=run)


def _load_skip_event_ids(twds_dir: Path) -> frozenset[int]:
    """Return the set of event IDs listed in skip_events.txt next to twds_dir.

    The file is optional; an absent file returns an empty set.  Each non-blank,
    non-comment line must contain a single integer event ID.  Lines starting
    with '#' are ignored.
    """
    skip_file = twds_dir.parent / SKIP_EVENTS_FILENAME
    if not skip_file.exists():
        return frozenset()
    ids: set[int] = set()
    for raw_line in skip_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            ids.add(int(line))
        except ValueError:
            logger.warning("skip_events.txt: ignoring non-integer line %r", line)
    return frozenset(ids)


def _iter_published_yaml(
    twds_dir: Path, full_validation: bool, skip_event_ids: frozenset[int] = frozenset()
) -> Iterator[Path]:
    """Yield all YAML files that are NOT inside changes_required/ or in skip_event_ids."""
    for yaml_file in _filter_yaml_paths(twds_dir, full_validation):
        parts = yaml_file.relative_to(twds_dir).parts
        if parts and parts[0] in SKIP_DIRS:
            continue
        try:
            event_id = int(yaml_file.stem)
        except ValueError:
            event_id = -1
        if event_id in skip_event_ids:
            logger.debug("skipping %s (listed in %s)", yaml_file.name, SKIP_EVENTS_FILENAME)
            continue
        yield yaml_file


def _iter_errors_yaml(
    twds_dir: Path, skip_event_ids: frozenset[int] = frozenset()
) -> Iterator[Path]:
    """Yield every YAML file under twds/errors/ that is not in skip_event_ids."""
    errors_dir = twds_dir / "errors"
    if not errors_dir.exists():
        return
    for yaml_file in sorted(errors_dir.rglob("*.yaml")):
        try:
            event_id = int(yaml_file.stem)
        except ValueError:
            event_id = -1
        if event_id in skip_event_ids:
            logger.debug("skipping %s (listed in %s)", yaml_file.name, SKIP_EVENTS_FILENAME)
            continue
        yield yaml_file


def _filter_yaml_paths(twds_dir: Path, full_validation: bool) -> list[Path]:
    yaml_files: list[Path] = sorted(list(twds_dir.rglob("*.yaml")), reverse=True)

    if not full_validation:
        yaml_files = [p for p in yaml_files if p.relative_to(twds_dir).parts[0] not in SKIP_DIRS]
        yaml_files = yaml_files[:_FAST_VALIDATION_YAML_FILES_NUMBER_THRESHOLD]

    return yaml_files


def _check_and_update_winner(
    client: httpx.Client,
    data: dict[str, Any],
    event_url: str,
    delay: float = DEFAULT_DELAY_SECONDS,
) -> bool:
    """Mirror scraping steps 3+4: update winner and vekn_number from the VEKN calendar.

    Fetches the official winner from the event calendar page, then looks up
    their canonical name and VEKN number in the player registry.
    Mutates *data* in-place. Returns True if any field was changed.
    """
    dirty = False

    winner_result = fetch_event_winner(client, event_url, delay)
    if winner_result is None:
        return dirty
    calendar_winner, calendar_vekn_id = winner_result
    if calendar_winner and calendar_winner != data.get("winner"):
        data["winner"] = calendar_winner
        dirty = True
    if calendar_vekn_id is not None and data.get("vekn_number") is None:
        data["vekn_number"] = calendar_vekn_id
        dirty = True

    winner: str = data.get("winner") or ""
    if not winner:
        return dirty

    result = fetch_player(client, winner, delay)
    if result is None:
        return dirty

    canonical_name, vekn_number = result
    if canonical_name != data.get("winner"):
        data["winner"] = canonical_name
        dirty = True
    if vekn_number != data.get("vekn_number"):
        data["vekn_number"] = vekn_number
        dirty = True

    return dirty


def run(args: argparse.Namespace) -> int:
    setup_logging(args.verbose)

    yaml = YAML()
    full_validation: bool = args.full_validation
    errors_only: bool = args.errors_only
    twds_dir: Path = args.twds_dir
    dry_run: bool = args.dry_run
    force_date: bool = args.force_date

    moved: list[Path] = []
    updated: list[Path] = []
    skip_event_ids = _load_skip_event_ids(twds_dir)
    if skip_event_ids:
        logger.info("Skipping %d event(s) listed in %s.", len(skip_event_ids), SKIP_EVENTS_FILENAME)

    yaml_iter: Iterator[Path] = (
        _iter_errors_yaml(twds_dir, skip_event_ids)
        if errors_only
        else _iter_published_yaml(twds_dir, full_validation, skip_event_ids)
    )

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=60.0) as client:
        for path in yaml_iter:
            with open(path, encoding="utf-8") as fh:
                raw = yaml.load(fh)  # pyright: ignore[reportUnknownMemberType]

            if not isinstance(raw, dict):
                continue

            data: dict[str, Any] = cast(dict[str, Any], raw)

            forum_post_url: str = data.get("forum_post_url") or ""
            # TWDA-imported files use an event-calendar URL as forum_post_url;
            # they have no forum thread to rescrape.  Calendar winner check,
            # enrichment, and re-validation still run so errors can be resolved.
            is_twda_import = "/event-calendar/" in forum_post_url

            dirty = False

            # Step 1: rescrape the forum post for fresh tournament data
            if forum_post_url and not dry_run and not is_twda_import:
                try:
                    fresh = extract_twd_from_thread(
                        client, forum_post_url, delay=DEFAULT_DELAY_SECONDS
                    )
                    if fresh is not None:
                        fresh_data = fresh.model_dump(exclude_none=True)
                        # Preserve vekn_number — forum posts never contain it
                        preserved_vekn = data.get("vekn_number")
                        if preserved_vekn is not None:
                            fresh_data["vekn_number"] = preserved_vekn
                        data = fresh_data
                        dirty = True
                except Exception as exc:
                    logger.error("forum rescrape error for %s: %s", path.name, exc)

            # Step 2: check event calendar for canonical winner name + VEKN number
            event_url: str = data.get("event_url") or ""
            if event_url and not dry_run:
                try:
                    if _check_and_update_winner(client, data, event_url):
                        dirty = True
                except Exception as exc:
                    logger.error("calendar check error for %s: %s", path.name, exc)

            # Step 3: canonicalize names, enrich crypt cards and fix library sections
            # via krcg. Canonicalization runs first so enrichment/section lookups see
            # the official spelling (localized names, "The …" order, bare crypt names).
            deck_raw: dict[str, Any] = data.get("deck") or {}
            if deck_raw:
                deck = Deck.model_validate(deck_raw)
                name_fixes = canonicalize_card_names(deck)
                crypt_fixes = enrich_crypt_cards(deck)
                section_fixes = fix_card_sections(deck)
                id_fixes = enrich_card_ids(deck)
                if name_fixes or crypt_fixes or section_fixes or id_fixes:
                    data["deck"] = deck.model_dump(exclude_none=True)
                    dirty = True
                if name_fixes:
                    logger.debug("%s  names canonicalized:\n%s", path.name, "\n".join(name_fixes))
                if crypt_fixes:
                    logger.debug("%s  crypt enriched:\n%s", path.name, "\n".join(crypt_fixes))
                if section_fixes:
                    logger.debug("%s  sections fixed:\n%s", path.name, "\n".join(section_fixes))
                if id_fixes:
                    logger.debug("%s  card ids enriched:\n%s", path.name, "\n".join(id_fixes))

            # Step 4: fetch official event date for date-coherence check
            calendar_date = None
            # --force-date needs the calendar date even in dry-run to report what would change.
            if event_url and (not dry_run or force_date):
                try:
                    calendar_date = fetch_event_date(client, event_url)
                except Exception as exc:
                    logger.error("calendar date error for %s: %s", path.name, exc)

            # Step 4b: force-update date_start from calendar if requested
            if force_date and calendar_date is not None:
                file_date = parse_date_field(data.get("date_start"))
                if file_date != calendar_date:
                    if dry_run:
                        logger.debug(
                            "[dry-run] would update %s date_start: %s → %s",
                            path.name,
                            file_date,
                            calendar_date,
                        )
                    else:
                        data["date_start"] = calendar_date
                        dirty = True
                        logger.debug(
                            "%s  date_start updated: %s → %s",
                            path.name,
                            file_date,
                            calendar_date,
                        )

            # Step 5: full validation
            errors = error_types(data, calendar_date=calendar_date)

            if not errors:
                rel_parts = path.relative_to(twds_dir).parts
                in_errors = len(rel_parts) > 1 and rel_parts[0] == "errors"
                if in_errors:
                    d = data.get("date_start")
                    if isinstance(d, datetime.date):
                        dest = twds_dir / f"{d.year:04d}" / f"{d.month:02d}" / path.name
                    else:
                        dest = twds_dir / path.name
                else:
                    dest = path
                if dry_run:
                    if in_errors:
                        logger.info("[dry-run] would recover %s from errors/", path.name)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if dirty:
                        with open(dest, "w", encoding="utf-8") as fh:
                            yaml.dump(  # pyright: ignore[reportUnknownMemberType]
                                reorder_tournament_dict(data),
                                fh,
                            )
                        if in_errors:
                            path.unlink()
                    elif in_errors:
                        shutil.move(str(path), str(dest))
                    if dirty or in_errors:
                        label = "recovered" if in_errors else "updated"
                        logger.info("%s %s", label, path.name)
                        updated.append(path)
                continue

            # Step 6: move to errors/<first_error>/
            dest_dir = twds_dir / "errors" / errors[0]
            if dry_run:
                logger.info(
                    "[dry-run] would move %s → errors/%s/  (%s)",
                    path.name,
                    errors[0],
                    ", ".join(errors),
                )
            else:
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / path.name
                shutil.move(str(path), str(dest))
                logger.warning(
                    "%s → errors/%s/  (%s)",
                    path.name,
                    errors[0],
                    ", ".join(errors),
                )
            moved.append(path)

    if not moved and not updated:
        logger.info("All published files passed validation.")
    else:
        label = "would be moved" if dry_run else "moved"
        if moved:
            logger.info("%d file(s) %s.", len(moved), label)
        if updated:
            logger.info("%d file(s) updated in place.", len(updated))

    return 0
