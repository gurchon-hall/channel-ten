"""Additional parser tests for edge cases not covered by test_parser.py."""

import pytest

from channel_ten.parser import (
    helpers,
    parse_twd_text,
    parsers,
)

# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestStripInlineComment:
    def test_with_comment(self):
        text, comment = helpers.strip_inline_comment("Blood Doll -- very useful")
        assert text == "Blood Doll"
        assert comment == "very useful"

    def test_without_comment(self):
        text, comment = helpers.strip_inline_comment("Blood Doll")
        assert text == "Blood Doll"
        assert comment is None

    def test_double_dash_without_trailing_space(self):
        text, comment = helpers.strip_inline_comment("Abombwe        --a lot, I know")
        assert text == "Abombwe"
        assert comment == "a lot, I know"

    def test_en_dash(self):
        text, comment = helpers.strip_inline_comment("Obedient Flesh – 3rd copy")
        assert text == "Obedient Flesh"
        assert comment == "3rd copy"

    def test_spaced_hyphen(self):
        text, comment = helpers.strip_inline_comment("Perfectionist - could be a DI?")
        assert text == "Perfectionist"
        assert comment == "could be a DI?"

    def test_footnote_slashes_no_space(self):
        text, comment = helpers.strip_inline_comment("Filchware's Pawn Shop *//recursion is broken")
        assert text == "Filchware's Pawn Shop"
        assert comment == "recursion is broken"

    def test_footnote_slashes_with_space(self):
        text, comment = helpers.strip_inline_comment("Erebus Mask *// tons of value")
        assert text == "Erebus Mask"
        assert comment == "tons of value"

    def test_trailing_period_before_comment_is_kept(self):
        # The trailing period is preserved at parse time (some names end in a
        # period); canonicalization removes it for cards that don't end in one.
        text, comment = helpers.strip_inline_comment(
            "Dreams of the Sphinx.           --I make no apologies"
        )
        assert text == "Dreams of the Sphinx."
        assert comment == "I make no apologies"

    def test_trailing_period_in_name_preserved(self):
        # Several card names genuinely end in a period and must not be truncated.
        for name in ("J. S. Simmons, Esq.", "CrimethInc."):
            text, comment = helpers.strip_inline_comment(name)
            assert text == name
            assert comment is None

    def test_trailing_footnote_star_stripped(self):
        text, comment = helpers.strip_inline_comment("Carlton Van Wyk*")
        assert text == "Carlton Van Wyk"
        assert comment is None

    def test_hyphenated_name_untouched(self):
        text, comment = helpers.strip_inline_comment("Anti-toxin")
        assert text == "Anti-toxin"
        assert comment is None


class TestNormalizeUnicode:
    def test_folds_non_breaking_spaces(self):
        assert helpers.normalize_unicode("Walk\xa0of\xa0Flame") == "Walk of Flame"

    def test_straightens_curly_apostrophe(self):
        assert helpers.normalize_unicode("My Enemy’s Enemy") == "My Enemy's Enemy"

    def test_drops_zero_width_chars(self):
        assert helpers.normalize_unicode("Blood​Doll") == "BloodDoll"

    def test_preserves_ascii_space_runs(self):
        # Multi-space runs (column alignment) and in-name hyphens must survive.
        assert helpers.normalize_unicode("Nathan   Turner - Anti-toxin") == (
            "Nathan   Turner - Anti-toxin"
        )

    def test_repairs_utf8_as_cp1252_mojibake(self):
        assert helpers.normalize_unicode("Aline GÃ¤deke") == "Aline Gädeke"
        assert helpers.normalize_unicode("Saku PihlajamÃ¤ki") == "Saku Pihlajamäki"
        assert helpers.normalize_unicode("KuyÃ©n") == "Kuyén"

    def test_leaves_correct_accents_untouched(self):
        # Already-valid UTF-8 accents must never be "repaired".
        for name in ("Ángel Guerrero", "Clara Hjortshøj", "Saankaláxt"):
            assert helpers.normalize_unicode(name) == name

    def test_drops_soft_hyphen(self):
        # U+00AD (soft hyphen) is invisible and must be removed (the "Dí\xada" case).
        assert helpers.normalize_unicode("Dí\xada de los Muertos") == "Día de los Muertos"
        assert helpers.normalize_unicode("Blood\xadDoll") == "BloodDoll"


class TestStripHashComment:
    def test_strips_hash(self):
        result = helpers.strip_hash_comment("Some text # comment here")
        assert result == "Some text"

    def test_no_hash(self):
        result = helpers.strip_hash_comment("Some text")
        assert result == "Some text"

    def test_leading_hash(self):
        result = helpers.strip_hash_comment("# full comment")
        assert result == ""


class TestNormalizeRounds:
    def test_canonical(self):
        assert helpers.normalize_rounds("3R+F") == "3R+F"

    def test_with_final(self):
        assert helpers.normalize_rounds("3R+Final") == "3R+F"

    def test_with_spaces(self):
        assert helpers.normalize_rounds("2 R + F") == "2R+F"

    def test_no_match_returns_stripped(self):
        assert helpers.normalize_rounds("  blah  ") == "blah"


class TestExtractVeknUrl:
    def test_full_url(self):
        url = helpers.extract_vekn_url("https://www.vekn.net/event-calendar/event/8470")
        assert url == "https://www.vekn.net/event-calendar/event/8470"

    def test_bare_www(self):
        url = helpers.extract_vekn_url("www.vekn.net/event-calendar/event/1234")
        assert url == "https://www.vekn.net/event-calendar/event/1234"

    def test_no_url(self):
        url = helpers.extract_vekn_url("No URL here")
        assert url is None


class TestSplitDate:
    def test_single_date(self):
        start, end = helpers.split_date("March 25th 2023")
        assert start == "March 25th 2023"
        assert end is None

    def test_date_range(self):
        start, end = helpers.split_date("March 25th 2023 -- March 26th 2023")
        assert start == "March 25th 2023"
        assert end == "March 26th 2023"

    def test_strips_time(self):
        start, _ = helpers.split_date("March 25th 2023 14:00")
        assert "14:00" not in start


class TestParseCryptLine:
    def test_valid_line(self):
        card = parsers.parse_crypt_line("2x Nathan Turner      4 PRO ani                 Gangrel:6")
        assert card is not None
        assert card.name == "Nathan Turner"
        assert card.count == 2
        assert card.capacity == 4
        assert card.clan == "Gangrel"
        assert card.grouping == 6

    def test_invalid_line_returns_none(self):
        card = parsers.parse_crypt_line("This is not a card line")
        assert card is None

    def test_with_comment(self):
        card = parsers.parse_crypt_line(
            "2x Nathan Turner      4 PRO ani                 Gangrel:6 -- some note"
        )
        assert card is not None
        assert card.comment == "some note"

    def test_with_title(self):
        card = parsers.parse_crypt_line("1x Tara              6 cel POT PRE prince       Brujah:5")
        assert card is not None
        assert card.title == "prince"
        assert card.clan == "Brujah"

    def test_strips_group_suffix_from_name(self):
        # Some posts bake the group into the name; the group is parsed from "Clan:N".
        card = parsers.parse_crypt_line("1x Mina Grotius (G3)   5 for pre   Tremere:3")
        assert card is not None
        assert card.name == "Mina Grotius"
        assert card.grouping == 3

    def test_group_suffix_keeps_adv_flag(self):
        card = parsers.parse_crypt_line("2x Tariq (G6 ADV)   8 cel obf pre   Banu Haqim:6")
        assert card is not None
        assert card.name == "Tariq (ADV)"
        assert card.grouping == 6

    def test_lone_adv_suffix_preserved(self):
        card = parsers.parse_crypt_line("2x Tariq (ADV)   8 cel obf pre   Banu Haqim:6")
        assert card is not None
        assert card.name == "Tariq (ADV)"


class TestParseLibraryLine:
    def test_valid_line(self):
        card = parsers.parse_library_line("1x Blood Doll")
        assert card is not None
        assert card.name == "Blood Doll"
        assert card.count == 1

    def test_with_comment(self):
        card = parsers.parse_library_line("1x Blood Doll -- discard this")
        assert card is not None
        assert card.comment == "discard this"

    def test_invalid_line_returns_none(self):
        card = parsers.parse_library_line("Not a card line")
        assert card is None


# ---------------------------------------------------------------------------
# Lenient parse mode
# ---------------------------------------------------------------------------

LENIENT_EXAMPLE = """\
Winner: Bobby Lemon
6th Great Symposium
Mikkeli, Finland
March 25th 2023
13 players
3R+F
https://www.vekn.net/event-calendar/event/10546

Crypt (2 cards, min=4, max=4, avg=4)
-------------------------------------
2x Nathan Turner      4 PRO ani                 Gangrel:6

Library (1 cards)
Master (1)
1x Blood Doll
"""


class TestLenientParse:
    def test_labeled_winner(self):
        t = parse_twd_text(LENIENT_EXAMPLE)
        assert t.winner == "Bobby Lemon"

    def test_event_name_inferred(self):
        t = parse_twd_text(LENIENT_EXAMPLE)
        assert t.name == "6th Great Symposium"

    def test_location_inferred(self):
        t = parse_twd_text(LENIENT_EXAMPLE)
        assert t.location == "Mikkeli, Finland"


# ---------------------------------------------------------------------------
# VP comment in lenient mode
# ---------------------------------------------------------------------------

LENIENT_WITH_VP = """\
Conservative Agitation
Vila Velha, Brazil
October 1st 2016
2R+F
12 players
Winner: Ravel Zorzal
https://www.vekn.net/event-calendar/event/8470
-- 5VP in final

Crypt (2 cards, min=4, max=4, avg=4)
-------------------------------------
2x Nathan Turner      4 PRO ani                 Gangrel:6

Library (1 cards)
Master (1)
1x Blood Doll
"""


class TestVpCommentLenient:
    def test_vp_comment_parsed(self):
        t = parse_twd_text(LENIENT_WITH_VP)
        assert t.vp_comment == "5VP in final"


# ---------------------------------------------------------------------------
# forum_post_url passthrough
# ---------------------------------------------------------------------------

SIMPLE = """\
Conservative Agitation
Vila Velha, Brazil
October 1st 2016
2R+F
12 players
Ravel Zorzal
https://www.vekn.net/event-calendar/event/8470

Crypt (2 cards, min=4, max=4, avg=4)
-------------------------------------
2x Nathan Turner      4 PRO ani                 Gangrel:6

Library (1 cards)
Master (1)
1x Blood Doll
"""


class TestForumPostUrl:
    def test_forum_post_url_set(self):
        url = "https://www.vekn.net/forum/event-reports-and-twd/12345-test"
        t = parse_twd_text(SIMPLE, forum_post_url=url)
        assert t.forum_post_url == url

    def test_forum_post_url_none_by_default(self):
        t = parse_twd_text(SIMPLE)
        assert t.forum_post_url is None


# ---------------------------------------------------------------------------
# Library card without section header
# ---------------------------------------------------------------------------

NO_SECTION_HEADER = """\
Conservative Agitation
Vila Velha, Brazil
October 1st 2016
2R+F
12 players
Ravel Zorzal
https://www.vekn.net/event-calendar/event/8470

Crypt (2 cards, min=4, max=4, avg=4)
-------------------------------------
2x Nathan Turner      4 PRO ani                 Gangrel:6

Library (2 cards)
1x Blood Doll
1x Vessel
"""


class TestLibraryWithoutSection:
    def test_cards_parsed_without_section(self):
        t = parse_twd_text(NO_SECTION_HEADER)
        assert t.deck
        # Should still parse cards even without a section header
        total_cards = sum(len(s.cards) for s in t.deck.library_sections)
        assert total_cards == 2


# ---------------------------------------------------------------------------
# Deck with multiline description
# ---------------------------------------------------------------------------

MULTILINE_DESC = """\
Conservative Agitation
Vila Velha, Brazil
October 1st 2016
2R+F
12 players
Ravel Zorzal
https://www.vekn.net/event-calendar/event/8470

Deck Name: My Deck
Description:
A great description here.

Crypt (2 cards, min=4, max=4, avg=4)
-------------------------------------
2x Nathan Turner      4 PRO ani                 Gangrel:6

Library (1 cards)
Master (1)
1x Blood Doll
"""


class TestMultilineDescription:
    def test_description_on_next_line(self):
        t = parse_twd_text(MULTILINE_DESC)
        assert t.deck
        assert "great description" in t.deck.description


# ---------------------------------------------------------------------------
# Inline description (value on same line as Description:)
# ---------------------------------------------------------------------------

INLINE_DESC = """\
Conservative Agitation
Vila Velha, Brazil
October 1st 2016
2R+F
12 players
Ravel Zorzal
https://www.vekn.net/event-calendar/event/8470

Deck Name: My Deck
Description: Inline description value.

Crypt (2 cards, min=4, max=4, avg=4)
-------------------------------------
2x Nathan Turner      4 PRO ani                 Gangrel:6

Library (1 cards)
Master (1)
1x Blood Doll
"""


class TestInlineDescription:
    def test_description_inline(self):
        t = parse_twd_text(INLINE_DESC)
        assert t.deck
        assert t.deck.description == "Inline description value."


# ---------------------------------------------------------------------------
# Lenient parse: missing fields raises
# ---------------------------------------------------------------------------

INCOMPLETE = """\
Just a name here
https://www.vekn.net/event-calendar/event/1234

Crypt (2 cards, min=4, max=4, avg=4)
-------------------------------------
2x Nathan Turner      4 PRO ani                 Gangrel:6

Library (1 cards)
Master (1)
1x Blood Doll
"""


class TestLenientMissingFields:
    def test_raises_when_too_many_fields_missing(self):
        with pytest.raises(ValueError):
            parse_twd_text(INCOMPLETE)
