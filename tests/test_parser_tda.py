"""Tests for channel_ten.parser._tda."""

from channel_ten.parser import parse_tda_deck_text

_SAMPLE_DECK_TEXT = """Deck Name: Test Deck
Author: 3070069
Description: A test deck.

Crypt (2 cards, min=4 max=4 avg=4.00)
======================================
2x Nathan Turner  4 PRO ani  Gangrel:6

Library (1 cards)
==================
Master (1)
-----------
1x Blood Doll
"""


class TestParseTdaDeckText:
    def test_extracts_author_as_created_by(self):
        deck = parse_tda_deck_text(_SAMPLE_DECK_TEXT)
        assert deck.created_by == "3070069"

    def test_extracts_deck_name_and_description(self):
        deck = parse_tda_deck_text(_SAMPLE_DECK_TEXT)
        assert deck.name == "Test Deck"
        assert deck.description == "A test deck."

    def test_parses_crypt_and_library(self):
        deck = parse_tda_deck_text(_SAMPLE_DECK_TEXT)
        assert deck.crypt_count == 2
        assert deck.crypt[0].name == "Nathan Turner"
        assert deck.library_count == 1
        assert deck.library_sections[0].cards[0].name == "Blood Doll"

    def test_strips_hash_comments_and_blank_lines(self):
        text = "# a leading comment\n\n" + _SAMPLE_DECK_TEXT + "\n\n"
        deck = parse_tda_deck_text(text)
        assert deck.crypt_count == 2
