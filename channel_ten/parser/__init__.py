"""
Parser for TWD posts scraped from the VEKN forum.

Submodules:
  _helpers       — regex constants and line-level helper functions
  _header        — strict and lenient header parsers
  _deck          — deck block parser (crypt + library sections)
  _twd           — main entry point (parse_twd_text)

Exports:
  helpers, ...   — regex, helpers and parsers in _helpers as objects
  parse_twd_text — Main entry point
"""

from channel_ten.parser._helpers import helpers, parsers, regex
from channel_ten.parser._twd import parse_twd_text

__all__ = [
    # Helpers
    "helpers",
    "regex",
    "parsers",
    # Main entry point
    "parse_twd_text",
]
