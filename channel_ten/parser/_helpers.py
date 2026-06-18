"""Regex constants and line-level helper functions for TWD parsing."""

import re
import unicodedata

from channel_ten.models import CryptCard, LibraryCard


# ---------------------------------------------------------------------------
# Regex constants
# ---------------------------------------------------------------------------
class ParserRegex:
    """ """

    CRYPT_HEADER_RE = re.compile(
        r"Crypt\s*\((?P<count>\d+)\s*cards?,\s*min=(?P<min>\d+),?\s*max=(?P<max>\d+),?\s*avg=(?P<avg>[\d.]+)\)"
    )
    LIBRARY_HEADER_RE = re.compile(r"Library\s*\((?P<count>\d+)\s*cards?\)")

    # Regex for crypt line parsing (handles both compact and column-aligned formats):
    #   <Qty>x <Name> <Capacity>( <discipline:3chars>)+ <Clan>:<grouping>
    CRYPT_LINE_RE = re.compile(
        r"^(?P<count>\d+)x\s+"
        r"(?P<name>.+?)\s+"
        r"(?P<capacity>\d{1,2})"
        r"(?P<disciplines>(?:\s+[a-zA-Z]{3})+)\s+"
        r"(?P<clan>[^:]+):(?P<grouping>\d+)\s*$"
    )
    LIBRARY_LINE_RE = re.compile(r"^(?P<count>\d+)x\s+(?P<name>.+)$")
    SECTION_HEADER_RE = re.compile(r"^(?P<name>[A-Za-z /,()]+)\s*\((?P<count>\d+).*\)$")

    # Known VTES titles that appear between disciplines and clan name in crypt lines
    TITLE_RE = re.compile(
        r"^(Baron|Prince|Primogen|Justicar|Inner Circle"
        r"|Archbishop|Bishop|Priscus|Cardinal|Regent"
        r"|Magaji|1 vote|2 votes)\s+",
        re.IGNORECASE,
    )

    ROUNDS_RE = re.compile(r"(\d+)\s*R\s*\+\s*F(?:inal)?", re.IGNORECASE)
    PLAYERS_RE = re.compile(r"(\d+)\s*[Pp]layers?")
    VEKN_URL_RE = re.compile(r"https?://(?:www\.)?vekn\.net/\S+?/(\d+)\b")
    WINNER_LABEL_RE = re.compile(r"^Winner\s*:\s*(.+)$", re.IGNORECASE)
    DECK_NAME_RE = re.compile(r"^Deck\s*Name\s*[:\s]\s*(.+)$", re.IGNORECASE)
    CREATED_BY_RE = re.compile(r"^(?:Created\s*by|Author)\s*:\s*(.+)$", re.IGNORECASE)
    DESCRIPTION_RE = re.compile(r"^Description\s*:\s*(.*)$", re.IGNORECASE)

    # Inline-comment delimiters appended after a card name. Forum authors use many
    # forms; we match the earliest one. Two groups of delimiters:
    #   * unambiguous (no surrounding space needed) — no VTES card name contains
    #     these: ``--`` (one or more dashes), ``//``, ``*//`` (footnote + comment).
    #   * space-required — an en/em dash or a single hyphen, but only when flanked
    #     by whitespace, so hyphenated names like "Anti-toxin" are left intact.
    COMMENT_DELIM_RE = re.compile(r"\s*(?:\*?\s*//|--+)|\s+[–—-]\s+")

    # Unicode whitespace to fold to a regular space (NBSP, narrow NBSP, figure/
    # en/em/thin spaces, ideographic space). Line separators are intentionally
    # excluded — str.splitlines() handles those.
    UNICODE_WS_RE = re.compile("[\\xa0\\u1680\\u2000-\\u200a\\u202f\\u205f\\u3000]")
    # Zero-width characters to drop entirely.
    ZERO_WIDTH_RE = re.compile("[\\u200b\\u200c\\u200d\\ufeff]")
    # Typographic apostrophes/quotes to straighten (matches krcg's spelling).
    APOSTROPHE_RE = re.compile("[\\u2018\\u2019\\u02bc\\u2032]")


# ---------------------------------------------------------------------------
# Line-level helpers
# ---------------------------------------------------------------------------
class LineHelpers:
    """ """

    @staticmethod
    def normalize_unicode(raw: str) -> str:
        """Normalise unicode quirks that prevent card-name resolution.

        - NFC-compose decomposed accents (e.g. combining acute) to match krcg.
        - Straighten typographic apostrophes/primes to ``'`` (e.g. ``My Enemy's``).
        - Drop zero-width characters.
        - Fold non-breaking and exotic unicode spaces to a regular space so card
          names like ``Walk\\xa0of\\xa0Flame`` become ``Walk of Flame``.

        Runs of regular ASCII spaces are left untouched — the column-aligned crypt
        regex and the whitespace-delimited inline comments depend on them. Dashes
        are likewise left alone (they are inline-comment delimiters).
        """
        raw = unicodedata.normalize("NFC", raw)
        raw = ParserRegex.APOSTROPHE_RE.sub("'", raw)
        raw = ParserRegex.ZERO_WIDTH_RE.sub("", raw)
        raw = ParserRegex.UNICODE_WS_RE.sub(" ", raw)
        return raw

    @staticmethod
    def _strip_name_markers(name: str) -> str:
        """Strip trailing footnote ``*`` and stray ``.`` left after a comment."""
        return name.rstrip().rstrip("*.").rstrip()

    @staticmethod
    def strip_inline_comment(line: str) -> tuple[str, str | None]:
        """Split a card line into ``(name, comment)``.

        Recognises several inline-comment delimiters used on the forum:
        ``--`` (with or without surrounding spaces), ``//`` / ``*//`` (footnote +
        comment), and a space-flanked en/em dash or single hyphen. The earliest
        delimiter wins. Trailing footnote ``*`` and ``.`` are stripped from the
        name even when no comment follows.
        """
        m = ParserRegex.COMMENT_DELIM_RE.search(line)
        if m:
            name = LineHelpers._strip_name_markers(line[: m.start()])
            comment = line[m.end() :].strip() or None
            return name, comment
        return LineHelpers._strip_name_markers(line.strip()), None

    @staticmethod
    def strip_hash_comment(line: str) -> str:
        idx = line.find("#")
        if idx >= 0:
            return line[:idx].rstrip()
        return line.rstrip()

    @staticmethod
    def normalize_rounds(raw: str) -> str:
        """Normalize '3R+Final', '2R + F', '2 R+F' -> '3R+F'."""
        m = ParserRegex.ROUNDS_RE.search(raw)
        if m:
            return f"{m.group(1)}R+F"
        return raw.strip()

    @staticmethod
    def extract_vekn_url(line: str) -> str | None:
        m = ParserRegex.VEKN_URL_RE.search(line)
        if m:
            return m.group(0)
        bare = re.search(r"(?<![:/])www\.vekn\.net/\S+?/(\d+)\b", line)
        if bare:
            return "https://" + bare.group(0)
        return None

    @staticmethod
    def split_date(raw: str) -> tuple[str, str | None]:
        raw = re.split(r",?\s*\d{1,2}:\d{2}", raw)[0].strip()
        if " -- " in raw:
            parts = raw.split(" -- ", 1)
            return parts[0].strip(), parts[1].strip()
        return raw, None


# ---------------------------------------------------------------------------
# Card line parsers
# ---------------------------------------------------------------------------
class CardParser:
    """ """

    @staticmethod
    def parse_crypt_line(line: str) -> CryptCard | None:
        """
        Parse a VTES crypt line.

        Handles both compact and column-aligned formats:
            <Qty>x <Name> <Capacity> <disc1> [<disc2> ...] <Clan>:<grouping>

        Examples:
            2x Nathan Turner 4 PRO ani Gangrel:6
            2x Nathan Turner      4 PRO ani                 Gangrel:6
        """
        line, comment = LineHelpers.strip_inline_comment(line)
        line = line.strip()

        m = ParserRegex.CRYPT_LINE_RE.match(line)
        if not m:
            return None
        raw_clan = m.group("clan").strip()
        title_m = ParserRegex.TITLE_RE.match(raw_clan)
        if title_m:
            title: str | None = title_m.group(1)
            clan = raw_clan[title_m.end() :].strip()
        else:
            title = None
            clan = raw_clan
        return CryptCard(
            count=int(m.group("count")),
            name=m.group("name").strip(),
            capacity=int(m.group("capacity")),
            disciplines=m.group("disciplines").strip(),
            clan=clan,
            grouping=int(m.group("grouping")),
            title=title,
            comment=comment,
        )

    @staticmethod
    def parse_library_line(line: str) -> LibraryCard | None:
        line, comment = LineHelpers.strip_inline_comment(line)
        m = ParserRegex.LIBRARY_LINE_RE.match(line.strip())
        if not m:
            return None
        return LibraryCard(
            count=int(m.group("count")),
            name=m.group("name").strip(),
            comment=comment,
        )


regex: ParserRegex = ParserRegex()
helpers: LineHelpers = LineHelpers()
parsers: CardParser = CardParser()


__all__ = ["regex", "helpers", "parsers"]
