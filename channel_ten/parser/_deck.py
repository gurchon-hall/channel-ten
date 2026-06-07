"""Deck block parser — extracts crypt and library sections from TWD text."""

from channel_ten.models import CryptCard, Deck, LibrarySection
from channel_ten.parser import _helpers as helpers


def parse_deck_block(lines: list[str]) -> Deck:
    deck_name: str | None = None
    created_by: str | None = None
    description: str = ""
    crypt_count = crypt_min = crypt_max = 0
    crypt_avg = 0.0
    crypt_cards: list[CryptCard] = []
    library_count = 0
    library_sections: list[LibrarySection] = []

    # Lines before the Crypt header = deck metadata (Deck Name, Author, Description)
    crypt_header_idx = next(
        (i for i, line in enumerate(lines) if helpers.regex.CRYPT_HEADER_RE.search(line)),
        0,
    )
    _collecting_description = False
    for line in lines[:crypt_header_idx]:
        s = line.strip()
        if not s:
            _collecting_description = False  # blank line ends multiline description
            continue
        # Multiline description continuation (line after "Description:" with empty value)
        if _collecting_description:
            description = s
            _collecting_description = False
            continue
        m = helpers.regex.DECK_NAME_RE.match(s)
        if m:
            deck_name = m.group(1).strip() or None
            continue
        m = helpers.regex.CREATED_BY_RE.match(s)
        if m:
            created_by = m.group(1).strip() or None
            continue
        m = helpers.regex.DESCRIPTION_RE.match(s)
        if m:
            value = m.group(1).strip()
            if value:
                description = value
            else:
                _collecting_description = True  # value on next line
            continue
        # All other lines (tournament header, VP comments, unlabeled text) are ignored

    idx = crypt_header_idx
    n = len(lines)

    # --- Crypt (mandatory) ---
    m = helpers.regex.CRYPT_HEADER_RE.search(lines[idx])
    if not m:
        raise ValueError("Mandatory 'Crypt (N cards, ...)' block not found in deck")

    crypt_count = int(m.group("count"))
    crypt_min = int(m.group("min"))
    crypt_max = int(m.group("max"))
    crypt_avg = float(m.group("avg"))
    idx += 1

    if idx < n and lines[idx].strip() and lines[idx].strip()[0] in ("-", "="):
        idx += 1

    while idx < n:
        line = lines[idx]
        if helpers.regex.LIBRARY_HEADER_RE.search(line):
            break
        if not line.strip():  # empty lines between cards — skip, don't break
            idx += 1
            continue
        crypt_card = helpers.parsers.parse_crypt_line(line)
        if crypt_card:
            crypt_cards.append(crypt_card)
        idx += 1

    # --- Library (mandatory) ---
    library_found = False
    while idx < n:
        line = lines[idx]
        m = helpers.regex.LIBRARY_HEADER_RE.search(line)
        if m:
            library_found = True
            library_count = int(m.group("count"))
            idx += 1
            current_section: LibrarySection | None = None
            while idx < n:
                line = lines[idx]
                if not line.strip():
                    idx += 1
                    continue
                sm = helpers.regex.SECTION_HEADER_RE.match(line.strip())
                if sm and not line.strip()[0].isdigit():
                    current_section = LibrarySection(
                        name=sm.group("name").strip(),
                        count=int(sm.group("count")),
                    )
                    library_sections.append(current_section)
                    idx += 1
                    continue
                library_card = helpers.parsers.parse_library_line(line)
                if library_card:
                    if current_section is None:
                        current_section = LibrarySection(name="", count=0)
                        library_sections.append(current_section)
                    current_section.cards.append(library_card)
                idx += 1
            break
        idx += 1

    if not library_found:
        raise ValueError("Mandatory 'Library (N cards)' block not found in deck")

    return Deck(
        name=deck_name,
        created_by=created_by,
        description=description,
        crypt_count=crypt_count,
        crypt_min=crypt_min,
        crypt_max=crypt_max,
        crypt_avg=crypt_avg,
        crypt=crypt_cards,
        library_count=library_count,
        library_sections=library_sections,
    )
