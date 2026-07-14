"""Deck-text entry point for TDA (Tournament Deck Archive) files.

TDA deck ``.txt`` files (one per participant, inside a VDB archive zip) use the
exact same ``Deck Name:`` / ``Author:`` / ``Description:`` / ``Crypt (...)`` /
``Library (...)`` body format as a TWD post's deck block, so this module only
does the same preprocessing :func:`~channel_ten.parser._twd.parse_twd_text` does
before handing off to the existing, unchanged :func:`parse_deck_block`.
"""

from channel_ten.models import Deck
from channel_ten.parser import _helpers as helpers
from channel_ten.parser._deck import parse_deck_block


def parse_tda_deck_text(raw: str) -> Deck:
    """Parse one TDA deck ``.txt`` file into a :class:`~channel_ten.models.Deck`."""
    raw = helpers.helpers.normalize_unicode(raw)
    lines = [helpers.helpers.strip_hash_comment(line) for line in raw.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return parse_deck_block(lines)
