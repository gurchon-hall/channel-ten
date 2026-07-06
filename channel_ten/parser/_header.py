"""Strict and lenient header parsers for TWD posts."""

import re

from channel_ten.models import Tournament
from channel_ten.parser import _helpers as helpers


def parse_header_strict(lines: list[str]) -> Tournament:
    non_blank = [line.strip() for line in lines if line.strip()]
    if len(non_blank) < 7:
        raise ValueError(f"Strict: need 7 non-blank lines, got {len(non_blank)}")

    name, location, raw_date, rounds_raw, players_raw, winner, event_url = non_blank[:7]

    if not helpers.regex.PLAYERS_RE.search(players_raw):
        raise ValueError(f"Strict: line 4 not player count: {players_raw!r}")
    if not helpers.regex.ROUNDS_RE.search(rounds_raw):
        raise ValueError(f"Strict: line 3 not rounds format: {rounds_raw!r}")
    if "vekn.net" not in event_url:
        raise ValueError(f"Strict: line 6 not vekn URL: {event_url!r}")

    date_start, date_end = helpers.helpers.split_date(raw_date)

    vp_comment: str | None = None
    for line in non_blank[7:]:
        if line.startswith("-") or re.search(r"vp|gw|final", line, re.IGNORECASE):
            vp_comment = line.lstrip("- ").strip()
            break

    return Tournament(
        name=name,
        location=location,
        date_start=date_start,
        date_end=date_end,
        rounds_format=helpers.helpers.normalize_rounds(rounds_raw),
        players_count=players_raw,
        winner=winner,
        event_url=helpers.helpers.extract_vekn_url(event_url) or event_url,
        vp_comment=vp_comment,
        deck=None,
    )


def parse_header_lenient(lines: list[str]) -> Tournament:
    non_blank = [line.strip() for line in lines if line.strip()]

    name = location = date_start = date_end = None
    rounds_format = players_count = winner = event_url = vp_comment = None
    unlabeled: list[str] = []

    for line in non_blank:
        # Rounds
        if helpers.regex.ROUNDS_RE.search(line) and not helpers.regex.PLAYERS_RE.search(line):
            rounds_format = helpers.helpers.normalize_rounds(line)
            continue
        # Players (short line only — avoids matching "X players won with...")
        pm = helpers.regex.PLAYERS_RE.search(line)
        if pm and len(line) < 30:
            players_count = line
            continue
        # Winner labeled
        wm = helpers.regex.WINNER_LABEL_RE.match(line)
        if wm:
            winner = wm.group(1).strip()
            continue
        # VEKN URL
        url = helpers.helpers.extract_vekn_url(line)
        if url:
            if event_url is None:
                event_url = url
            continue
        # VP/GW comment
        if re.match(r"^[-\d]", line) and re.search(r"vp|gw|final", line, re.IGNORECASE):
            vp_comment = line.lstrip("- ").strip()
            continue
        # Stop at deck metadata
        if (
            helpers.regex.DECK_NAME_RE.match(line)
            or helpers.regex.CREATED_BY_RE.match(line)
            or helpers.regex.DESCRIPTION_RE.match(line)
        ):
            break

        unlabeled.append(line)

    if unlabeled:
        name = unlabeled[0]
    # Venue/location often wraps across several lines (e.g. "Venue Name" then
    # "City, Country"), so its line count can't be assumed — find the date
    # line instead and treat everything between name and date as location.
    rest = unlabeled[1:]
    date_idx = next(
        (i for i, line in enumerate(rest) if helpers.helpers.looks_like_date(line)), None
    )
    if date_idx is not None:
        if date_idx:
            location = ", ".join(rest[:date_idx])
        date_start, date_end = helpers.helpers.split_date(rest[date_idx])
        trailing = rest[date_idx + 1 :]
    else:
        location = rest[0] if rest else None
        trailing = rest[1:]
    if winner is None and trailing:
        winner = trailing[0]

    missing = [
        f
        for f, v in [
            ("name", name),
            ("location", location),
            ("date_start", date_start),
            ("rounds_format", rounds_format),
            ("players_count", players_count),
            ("winner", winner),
            ("event_url", event_url),
        ]
        if not v
    ]
    if missing:
        raise ValueError(f"Lenient parse: missing fields {missing}")

    return Tournament(
        name=name or "",
        location=location or "",
        date_start=date_start or "",
        date_end=date_end,
        rounds_format=rounds_format or "",
        players_count=players_count or "",
        winner=winner or "",
        event_url=event_url or "",
        vp_comment=vp_comment,
        deck=None,
    )
