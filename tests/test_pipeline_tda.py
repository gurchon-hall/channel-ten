"""Tests for channel_ten.pipeline_tda."""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from conftest import make_tda_deck

from channel_ten.pipeline import RouteCounters
from channel_ten.pipeline_tda import process_tda_deck, resolve_author, route_tda_deck

# ---------------------------------------------------------------------------
# resolve_author
# ---------------------------------------------------------------------------


class TestResolveAuthor:
    def test_numeric_author_used_directly_without_lookup(self):
        client = MagicMock()
        with patch("channel_ten.pipeline_tda.fetch_player") as mock_fetch:
            name, vekn_number = resolve_author(client, "3070069", delay=0)
        mock_fetch.assert_not_called()
        assert name == "3070069"
        assert vekn_number == 3070069

    def test_non_numeric_author_resolved_via_player_registry(self):
        client = MagicMock()
        with patch("channel_ten.pipeline_tda.fetch_player", return_value=("Jane Doe", 1234567)):
            name, vekn_number = resolve_author(client, "Jane Doe", delay=0)
        assert name == "Jane Doe"
        assert vekn_number == 1234567

    def test_unresolvable_author_keeps_raw_value(self, caplog: pytest.LogCaptureFixture):
        client = MagicMock()
        with (
            patch("channel_ten.pipeline_tda.fetch_player", return_value=None),
            caplog.at_level(logging.WARNING),
        ):
            name, vekn_number = resolve_author(client, "100WD1", delay=0)
        assert name == "100WD1"
        assert vekn_number is None
        assert any("not found" in r.message for r in caplog.records)

    def test_lookup_failure_keeps_raw_value(self, caplog: pytest.LogCaptureFixture):
        client = MagicMock()
        with (
            patch("channel_ten.pipeline_tda.fetch_player", side_effect=RuntimeError("boom")),
            caplog.at_level(logging.WARNING),
        ):
            name, vekn_number = resolve_author(client, "Some Name", delay=0)
        assert name == "Some Name"
        assert vekn_number is None


# ---------------------------------------------------------------------------
# process_tda_deck
# ---------------------------------------------------------------------------


class TestProcessTdaDeck:
    def test_returns_entry_and_empty_errors_for_valid_deck(self):
        entry = make_tda_deck()
        result, errors = process_tda_deck(entry)
        assert result is entry
        assert errors == []

    def test_returns_errors_for_empty_crypt(self):
        entry = make_tda_deck()
        entry.deck.crypt = []
        _, errors = process_tda_deck(entry)
        assert "illegal_crypt" in errors


# ---------------------------------------------------------------------------
# route_tda_deck
# ---------------------------------------------------------------------------


class TestRouteTdaDeck:
    def test_writes_valid_deck_to_event_dir(self, tmp_path: Path):
        entry = make_tda_deck()
        counters = RouteCounters()
        route_tda_deck(entry, [], output_dir=tmp_path, overwrite=False, counters=counters)

        expected = tmp_path / "2022" / "11" / "10367" / "3070069.yaml"
        assert expected.exists()
        assert counters.written == 1
        assert counters.failed == 0

    def test_writes_invalid_deck_to_errors_dir(self, tmp_path: Path):
        entry = make_tda_deck()
        counters = RouteCounters()
        route_tda_deck(
            entry, ["illegal_crypt"], output_dir=tmp_path, overwrite=False, counters=counters
        )

        expected = tmp_path / "errors" / "illegal_crypt" / "10367_3070069.yaml"
        assert expected.exists()
        assert counters.written == 1

    def test_identical_rewrite_is_skipped(self, tmp_path: Path):
        entry = make_tda_deck()
        counters = RouteCounters()
        route_tda_deck(entry, [], output_dir=tmp_path, overwrite=False, counters=counters)
        route_tda_deck(entry, [], output_dir=tmp_path, overwrite=False, counters=counters)

        assert counters.written == 1
        assert counters.skipped == 1
        assert counters.overwrite_skipped == 1

    def test_overwrite_replaces_existing_file(self, tmp_path: Path):
        entry = make_tda_deck()
        counters = RouteCounters()
        route_tda_deck(entry, [], output_dir=tmp_path, overwrite=False, counters=counters)

        entry2 = make_tda_deck(winner="Different Winner")
        route_tda_deck(entry2, [], output_dir=tmp_path, overwrite=True, counters=counters)

        assert counters.written == 2
        expected = tmp_path / "2022" / "11" / "10367" / "3070069.yaml"
        assert "Different Winner" in expected.read_text(encoding="utf-8")
