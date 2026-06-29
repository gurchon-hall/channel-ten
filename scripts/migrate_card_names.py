"""One-time migration script: rename cards in the eternal-vigilance storage folder.

Run this script once after deploying card-id support.  It walks every YAML file
under STORAGE_DIR, applies OLD_TO_NEW_NAME renames to any card whose name matches
an old key, re-enriches the deck with krcg to set canonical names and card IDs,
then writes the file back in-place.

After the migration all old names are gone from storage and this script is no
longer needed.

Usage:
    uv run python scripts/migrate_card_names.py <storage_dir>

Example:
    uv run python scripts/migrate_card_names.py ../eternal-vigilance
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, cast

from ruamel.yaml import YAML

from channel_ten._krcg_helper import is_krcg_loaded
from channel_ten.models import Tournament
from channel_ten.output.yaml import tournament_to_yaml_str
from channel_ten.validator import (
    canonicalize_card_names,
    enrich_card_ids,
    enrich_crypt_cards,
    fix_card_sections,
)

logger = logging.getLogger(__name__)

# Map old card names to their new canonical names.  Populate manually as
# official VTES card renames are announced.
OLD_TO_NEW_NAME: dict[str, str] = {
    "Mind Rape": "Puppet Master",
}


def _apply_renames(deck_data: dict[str, Any]) -> list[str]:
    """Rename any card matching OLD_TO_NEW_NAME in a raw deck dict.

    Mutates *deck_data* in-place.  Returns human-readable descriptions of
    changes made.
    """
    changes: list[str] = []
    for card in cast(list[dict[str, Any]], deck_data.get("crypt") or []):
        old: str = card.get("name", "")
        new = OLD_TO_NEW_NAME.get(old)
        if new:
            card["name"] = new
            changes.append(f"  crypt {old!r} → {new!r}")

    for section in cast(list[dict[str, Any]], deck_data.get("library_sections") or []):
        for card in cast(list[dict[str, Any]], section.get("cards") or []):
            old = card.get("name", "")
            new = OLD_TO_NEW_NAME.get(old)
            if new:
                card["name"] = new
                changes.append(f"  library {old!r} → {new!r}")

    return changes


def migrate(storage_dir: Path, dry_run: bool = False) -> None:
    """Walk *storage_dir* and apply card-name renames to every YAML file.

    Args:
        storage_dir: Root of the eternal-vigilance checkout.
        dry_run: When True, log what would change but do not write files.
    """
    if not is_krcg_loaded():
        logger.error("krcg is not available — cannot migrate.  Install krcg and retry.")
        sys.exit(1)

    yaml = YAML()
    yaml.preserve_quotes = True

    yaml_files = sorted(storage_dir.rglob("*.yaml"))
    logger.info("Found %d YAML files under %s", len(yaml_files), storage_dir)

    changed = 0
    for path in yaml_files:
        raw = cast(dict[str, Any], yaml.load(path))  # pyright: ignore[reportUnknownMemberType]

        deck_raw = cast(dict[str, Any], raw.get("deck") or {})
        renames = _apply_renames(deck_raw)
        if not renames:
            continue

        logger.info("%s", path.name)
        for line in renames:
            logger.info("%s", line)

        if dry_run:
            continue

        # Re-parse as a full Tournament so the enrichment pipeline can run.
        try:
            tournament = Tournament.model_validate(raw)
        except Exception as exc:
            logger.warning("Skipping %s — validation error: %s", path.name, exc)
            continue

        if tournament.deck:
            canonicalize_card_names(tournament.deck)
            enrich_crypt_cards(tournament.deck)
            fix_card_sections(tournament.deck)
            enrich_card_ids(tournament.deck)

        path.write_text(tournament_to_yaml_str(tournament), encoding="utf-8")
        changed += 1

    logger.info("Done — %d file(s) updated.", changed)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("storage_dir", type=Path, help="Path to eternal-vigilance checkout")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would change without writing files"
    )
    args = parser.parse_args()

    if not args.storage_dir.is_dir():
        logger.error("Not a directory: %s", args.storage_dir)
        sys.exit(1)

    migrate(args.storage_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
