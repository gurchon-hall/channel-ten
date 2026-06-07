"""Main entry point for TWD text parsing."""

from channel_ten.models import Tournament
from channel_ten.parser import _helpers as helpers
from channel_ten.parser._deck import parse_deck_block
from channel_ten.parser._header import (
    parse_header_lenient,
    parse_header_strict,
)


def parse_twd_text(raw: str, forum_post_url: str | None = None) -> Tournament:
    lines = [helpers.helpers.strip_hash_comment(line) for line in raw.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    if len(lines) < 7:
        raise ValueError(f"TWD block has fewer than 7 mandatory lines (got {len(lines)})")

    deck_start = next(
        (i for i, line in enumerate(lines) if helpers.regex.CRYPT_HEADER_RE.search(line)),
        None,
    )
    if deck_start is None:
        raise ValueError("Mandatory 'Crypt (N cards, ...)' block not found")

    header_lines = lines[:deck_start]

    try:
        tournament = parse_header_strict(header_lines)
    except ValueError:
        tournament = parse_header_lenient(header_lines)

    tournament.forum_post_url = forum_post_url
    tournament.deck = parse_deck_block(lines)  # receives full lines; finds crypt idx itself
    return tournament
