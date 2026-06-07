"""Tests for channel_ten.models."""

from datetime import date

import pytest
from conftest import make_tournament


class TestYamlFilename:
    def test_returns_event_id_yaml(self):
        t = make_tournament()
        assert t.yaml_filename == "9999.yaml"

    def test_raises_without_event_id(self):
        t = make_tournament(event_url="https://www.vekn.net/event-calendar/event/9999")
        t.event_id = None
        with pytest.raises(ValueError, match="event_id is missing"):
            _ = t.yaml_filename


class TestTxtFilename:
    def test_returns_event_id_txt(self):
        t = make_tournament()
        assert t.txt_filename == "9999.txt"

    def test_raises_without_event_id(self):
        t = make_tournament()
        t.event_id = None
        with pytest.raises(ValueError, match="event_id is missing"):
            _ = t.txt_filename


class TestCoercePlayers:
    def test_players_as_int(self):
        t = make_tournament(players_count=42)
        assert t.players_count == 42

    def test_players_as_string_with_word(self):
        t = make_tournament(players_count="42 players")
        assert t.players_count == 42

    def test_players_as_plain_string_number(self):
        t = make_tournament(players_count="13")
        assert t.players_count == 13


class TestDateParsing:
    def test_iso_format(self):
        t = make_tournament(date_start="2026-01-15")
        assert t.date_start == date(2026, 1, 15)

    def test_slash_format(self):
        t = make_tournament(date_start="15/01/2026")
        assert t.date_start == date(2026, 1, 15)

    def test_month_day_year(self):
        t = make_tournament(date_start="January 15 2026")
        assert t.date_start == date(2026, 1, 15)

    def test_ordinal_suffix_stripped(self):
        t = make_tournament(date_start="March 25th 2023")
        assert t.date_start == date(2023, 3, 25)

    def test_day_month_year(self):
        t = make_tournament(date_start="25 March 2023")
        assert t.date_start == date(2023, 3, 25)

    def test_abbreviated_month(self):
        t = make_tournament(date_start="Mar 25 2023")
        assert t.date_start == date(2023, 3, 25)

    def test_date_object_passthrough(self):
        d = date(2023, 3, 25)
        t = make_tournament(date_start=d)
        assert t.date_start == d

    def test_none_date_end(self):
        t = make_tournament(date_end=None)
        assert t.date_end is None

    def test_invalid_date_raises(self):
        with pytest.raises(ValueError, match="Cannot parse date"):
            make_tournament(date_start="not-a-date")


class TestRoundsFormat:
    def test_valid_format(self):
        t = make_tournament(rounds_format="2R+F")
        assert t.rounds_format == "2R+F"

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="rounds_format"):
            make_tournament(rounds_format="INVALID")


class TestEventId:
    def test_derived_from_url(self):
        t = make_tournament(event_url="https://www.vekn.net/event-calendar/event/12345")
        assert t.event_id == 12345
        assert isinstance(t.event_id, int)

    def test_no_match_stays_none(self):
        t = make_tournament(event_url="https://www.vekn.net/other/page")
        assert t.event_id is None

    def test_non_canonical_url_normalised(self):
        """A non-canonical vekn URL containing '/event/<id>' is rewritten."""
        t = make_tournament(event_url="https://www.vekn.net/player-registry/event/12345")
        assert t.event_id == 12345
        assert t.event_url == "https://www.vekn.net/event-calendar/event/12345"

    def test_canonical_url_unchanged(self):
        t = make_tournament(event_url="https://www.vekn.net/event-calendar/event/12345")
        assert t.event_url == "https://www.vekn.net/event-calendar/event/12345"
