"""
CLI for Channel 10.

Usage examples in README file
"""

import argparse
import sys

from channel_ten.cli import parse, publish, reimport, scrape, tda_scrape, validate
from channel_ten.cli._common import SubParsersAction


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="channel-ten",
        description="Scrape VTES tournament winning decks from vekn.net and export to YAML.",
    )
    sub: SubParsersAction = parser.add_subparsers(dest="command", required=True)
    scrape.register(sub)
    reimport.register(sub)
    tda_scrape.register(sub)
    parse.register(sub)
    publish.register(sub)
    validate.register(sub)
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))
