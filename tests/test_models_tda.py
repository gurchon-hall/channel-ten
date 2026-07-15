"""Tests for channel_ten.models.TdaDeck."""

import pytest
from conftest import make_tda_deck

from channel_ten.models import TdaDeck


class TestYamlFilename:
    def test_uses_author_vekn_number_when_resolved(self):
        entry = make_tda_deck(author="Jane Doe", author_vekn_number=1234567)
        assert entry.yaml_filename == "1234567.yaml"

    def test_falls_back_to_slug_of_raw_author(self):
        entry = make_tda_deck(author="100WD1", author_vekn_number=None)
        assert entry.yaml_filename == "100wd1.yaml"

    def test_slugifies_name_with_spaces_and_punctuation(self):
        entry = make_tda_deck(author="Jane O'Doe", author_vekn_number=None)
        assert entry.yaml_filename == "jane_o_doe.yaml"

    def test_blank_author_falls_back_to_unknown(self):
        entry = make_tda_deck(author="   ", author_vekn_number=None)
        assert entry.yaml_filename == "unknown.yaml"


class TestRoundsFormatValidation:
    def test_rejects_malformed_rounds_format(self):
        with pytest.raises(ValueError, match="rounds_format"):
            make_tda_deck(rounds_format="not-a-format")

    def test_accepts_valid_rounds_format(self):
        entry = make_tda_deck(rounds_format="4R+F")
        assert entry.rounds_format == "4R+F"


class TestDateParsing:
    def test_accepts_iso_date_string(self):
        entry = make_tda_deck(date_start="2022-11-05")
        assert entry.date_start.isoformat() == "2022-11-05"


class TestOptionalFields:
    def test_online_event_has_no_event_url(self):
        entry = make_tda_deck(event_id="online1", event_url=None)
        assert entry.event_id == "online1"
        assert entry.event_url is None

    def test_model_validate_round_trips(self):
        entry = make_tda_deck()
        dumped = entry.model_dump()
        assert TdaDeck.model_validate(dumped) == entry
