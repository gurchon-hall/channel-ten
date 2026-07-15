"""Tests for channel_ten.output.tda_yaml."""

from pathlib import Path

import pytest
from conftest import make_tda_deck

from channel_ten.output.tda_yaml import tda_deck_to_yaml_str, tda_event_dir, write_tda_deck_yaml


class TestTdaEventDir:
    def test_returns_year_month_event_id_path(self):
        entry = make_tda_deck()
        assert tda_event_dir(Path("tda"), entry) == Path("tda/2022/11/10367")

    def test_non_numeric_event_id(self):
        entry = make_tda_deck(event_id="online1", event_url=None)
        assert tda_event_dir(Path("tda"), entry) == Path("tda/2022/11/online1")


class TestTdaDeckToYamlStr:
    def test_round_trips_via_ruamel(self):
        entry = make_tda_deck()
        text = tda_deck_to_yaml_str(entry)
        assert "event_id: '10367'" in text
        assert "author: '3070069'" in text
        assert "name: Finnish Nationals 2022" in text

    def test_multiline_description_uses_block_scalar(self):
        entry = make_tda_deck()
        entry.deck.description = "Line one.\nLine two."
        text = tda_deck_to_yaml_str(entry)
        assert "description: |" in text


class TestWriteTdaDeckYaml:
    def test_writes_to_event_subdir(self, tmp_path: Path):
        entry = make_tda_deck()
        path = write_tda_deck_yaml(entry, tmp_path)
        assert path == tmp_path / "2022" / "11" / "10367" / "3070069.yaml"
        assert path.exists()

    def test_raises_file_exists_error_on_identical_content(self, tmp_path: Path):
        entry = make_tda_deck()
        write_tda_deck_yaml(entry, tmp_path)
        with pytest.raises(FileExistsError):
            write_tda_deck_yaml(entry, tmp_path)

    def test_overwrite_true_bypasses_identical_check(self, tmp_path: Path):
        entry = make_tda_deck()
        write_tda_deck_yaml(entry, tmp_path)
        path = write_tda_deck_yaml(entry, tmp_path, overwrite=True)
        assert path.exists()

    def test_two_authors_same_event_coexist(self, tmp_path: Path):
        entry_a = make_tda_deck(author="3070069", author_vekn_number=3070069)
        entry_b = make_tda_deck(author="1003636", author_vekn_number=1003636)
        write_tda_deck_yaml(entry_a, tmp_path)
        write_tda_deck_yaml(entry_b, tmp_path)

        event_dir = tmp_path / "2022" / "11" / "10367"
        assert (event_dir / "3070069.yaml").exists()
        assert (event_dir / "1003636.yaml").exists()
