"""CLI subcommand: parse.

Bidirectional conversion between TWD text format and YAML:
  - .txt  → YAML
  - .yaml / .yml → TXT
"""

import argparse
import logging
import sys
from pathlib import Path

from ruamel.yaml import YAML

from channel_ten._logger import setup_logging
from channel_ten.cli._common import SubParsersAction
from channel_ten.models import Tournament
from channel_ten.output import (
    tournament_to_txt,
    tournament_to_yaml_str,
    write_tournament_txt,
    write_tournament_yaml,
)
from channel_ten.parser import parse_twd_text

logger = logging.getLogger(__name__)

_YAML_EXTENSIONS = {".yaml", ".yml"}
_TXT_EXTENSIONS = {".txt"}


def register(sub: SubParsersAction) -> None:
    p = sub.add_parser(
        "parse",
        help="Convert between TWD text and YAML formats.",
    )
    p.add_argument(
        "input_file",
        type=Path,
        help="Path to a .txt or .yaml file. Direction is inferred from the extension.",
    )
    p.add_argument(
        "--twds-dir",
        "-o",
        type=Path,
        default=None,
        dest="twds_dir",
        help="Directory to write the output file. If omitted, prints to stdout.",
    )
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--verbose", "-v", action="store_true")
    p.set_defaults(func=run)


def _parse_txt_to_yaml(args: argparse.Namespace) -> int:
    """Convert a TWD .txt file to YAML."""
    raw = args.input_file.read_text(encoding="utf-8")
    try:
        tournament = parse_twd_text(raw)
    except ValueError as exc:
        logger.error("parse error: %s", exc)
        return 1

    if args.twds_dir is None:
        sys.stdout.write(tournament_to_yaml_str(tournament))
    else:
        try:
            path = write_tournament_yaml(tournament, args.twds_dir, overwrite=args.overwrite)
            logger.info("written to %s", path)
        except FileExistsError as exc:
            logger.warning("%s", exc)
    return 0


def _parse_yaml_to_txt(args: argparse.Namespace) -> int:
    """Convert a YAML tournament file to TWD .txt format."""
    yaml = YAML()
    try:
        data = yaml.load(  # pyright: ignore[reportUnknownMemberType]
            args.input_file.read_text(encoding="utf-8")
        )
        tournament = Tournament.model_validate(data)
    except Exception as exc:
        logger.error("parse error: %s", exc)
        return 1

    if args.twds_dir is None:
        sys.stdout.write(tournament_to_txt(tournament) + "\n")
    else:
        try:
            path = write_tournament_txt(tournament, args.twds_dir, overwrite=args.overwrite)
            logger.info("written to %s", path)
        except FileExistsError as exc:
            logger.warning("%s", exc)
    return 0


def run(args: argparse.Namespace) -> int:
    """Convert between TWD text and YAML formats."""
    setup_logging(args.verbose)

    ext = args.input_file.suffix.lower()
    if ext in _TXT_EXTENSIONS:
        return _parse_txt_to_yaml(args)
    if ext in _YAML_EXTENSIONS:
        return _parse_yaml_to_txt(args)

    logger.error("unsupported file extension %r — expected .txt, .yaml, or .yml", ext)
    return 1
