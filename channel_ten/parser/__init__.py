"""
Parser for TWD posts scraped from the VEKN forum, and TDA deck files from VDB archives.

Submodules:
  _helpers       — regex constants and line-level helper functions
  _header        — strict and lenient header parsers
  _deck          — deck block parser (crypt + library sections)
  _twd           — main entry point (parse_twd_text)
  _tda           — main entry point for TDA deck files (parse_tda_deck_text)

Exports:
  helpers, ...       — regex, helpers and parsers in _helpers as objects
  parse_twd_text     — TWD main entry point
  parse_tda_deck_text — TDA deck main entry point
"""

from channel_ten.parser._helpers import helpers, parsers, regex
from channel_ten.parser._tda import parse_tda_deck_text
from channel_ten.parser._twd import parse_twd_text

__all__ = [
    # Helpers
    "helpers",
    "regex",
    "parsers",
    # Main entry points
    "parse_twd_text",
    "parse_tda_deck_text",
]
