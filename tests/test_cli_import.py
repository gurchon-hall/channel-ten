"""Tests for the ``import`` CLI subcommand (channel_ten.cli.importer)."""

import argparse
import contextlib
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from channel_ten.cli import reimport as import_cmd

# A minimal but valid GiottoVerducci/TWD deck file (event_id 9999, dated 2024-01).
VALID_TWD = """\
The Dark Courier
Pamplona, Spain
January 13th 2024
2R+F
24 players
Pedro Millán Monje
https://www.vekn.net/event-calendar/event/9999

Crypt (12 cards, min=12, max=30, avg=5)
---------------------------------------
4x Angel Chavarria  3  THN              Samedi:6

Library (90 cards)
Master (1)
1x Channel 10
"""


def _import_namespace(**kwargs: Any) -> argparse.Namespace:
    defaults = dict(
        output_dir=Path("twds"),
        delay=0,
        overwrite=False,
        github_token=None,
        limit=None,
        create_issue=False,
        verbose=False,
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


@contextlib.contextmanager
def _patch_pipeline_externals(winner: str = "Pedro Millán Monje", errors: list[str] | None = None):
    """No-op every network call in the shared scrape pipeline.

    ``fetch_event_winner`` returns *winner* (non-None) so the deck is not flagged
    ``unconfirmed_winner``. ``error_types`` returns *errors* (default: none).
    """
    with (
        patch("channel_ten.pipeline.fetch_event_name", return_value=None),
        patch("channel_ten.pipeline.fetch_event_winner", return_value=(winner, None)),
        patch("channel_ten.pipeline.fetch_event_date", return_value=None),
        patch("channel_ten.pipeline.fetch_player", return_value=None),
        patch("channel_ten.pipeline.enrich_crypt_cards", return_value=[]),
        patch("channel_ten.pipeline.fix_card_sections", return_value=[]),
        patch("channel_ten.pipeline.error_types", return_value=errors or []),
    ):
        yield


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


class TestImportCommand:
    def test_register(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        import_cmd.register(sub)
        args = parser.parse_args(["import"])
        assert args.command == "import"

    def test_register_limit_and_token(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        import_cmd.register(sub)
        args = parser.parse_args(["import", "--limit", "5", "--github-token", "ghp_x"])
        assert args.limit == 5
        assert args.github_token == "ghp_x"


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


class TestImportRun:
    def test_imports_new_deck(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            args = _import_namespace(output_dir=Path(tmpdir))
            with (
                patch("channel_ten.cli.reimport.list_twda_event_ids", return_value=[9999]),
                patch("channel_ten.cli.reimport.fetch_twda_txt", return_value=VALID_TWD),
                _patch_pipeline_externals(),
            ):
                ret = import_cmd.run(args)
            assert ret == 0
            written = list(Path(tmpdir).rglob("*.yaml"))
            assert len(written) == 1
            assert written[0] == Path(tmpdir) / "2024" / "01" / "9999.yaml"

    def test_forum_post_url_defaults_to_event_url(self):
        """Imports have no forum thread; forum_post_url must fall back to event_url."""
        with tempfile.TemporaryDirectory() as tmpdir:
            args = _import_namespace(output_dir=Path(tmpdir))
            with (
                patch("channel_ten.cli.reimport.list_twda_event_ids", return_value=[9999]),
                patch("channel_ten.cli.reimport.fetch_twda_txt", return_value=VALID_TWD),
                _patch_pipeline_externals(),
            ):
                import_cmd.run(args)
            content = (Path(tmpdir) / "2024" / "01" / "9999.yaml").read_text(encoding="utf-8")
            assert "forum_post_url: https://www.vekn.net/event-calendar/event/9999" in content
            # And it must NOT be routed to errors/illegal_header/
            assert not (Path(tmpdir) / "errors" / "illegal_header").exists()

    def test_skips_id_already_in_base(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            existing = Path(tmpdir) / "2024" / "01" / "9999.yaml"
            existing.parent.mkdir(parents=True)
            existing.write_text("name: already here\n", encoding="utf-8")

            args = _import_namespace(output_dir=Path(tmpdir))
            with (
                patch("channel_ten.cli.reimport.list_twda_event_ids", return_value=[9999]),
                patch("channel_ten.cli.reimport.fetch_twda_txt") as mock_fetch,
                _patch_pipeline_externals(),
            ):
                ret = import_cmd.run(args)
            assert ret == 0
            mock_fetch.assert_not_called()

    def test_existing_in_errors_counts_as_base(self):
        """An id already routed to errors/ is treated as present and skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            existing = Path(tmpdir) / "errors" / "illegal_crypt" / "9999.yaml"
            existing.parent.mkdir(parents=True)
            existing.write_text("name: errored\n", encoding="utf-8")

            args = _import_namespace(output_dir=Path(tmpdir))
            with (
                patch("channel_ten.cli.reimport.list_twda_event_ids", return_value=[9999]),
                patch("channel_ten.cli.reimport.fetch_twda_txt") as mock_fetch,
                _patch_pipeline_externals(),
            ):
                ret = import_cmd.run(args)
            assert ret == 0
            mock_fetch.assert_not_called()

    def test_404_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            args = _import_namespace(output_dir=Path(tmpdir))
            with (
                patch("channel_ten.cli.reimport.list_twda_event_ids", return_value=[9999]),
                patch("channel_ten.cli.reimport.fetch_twda_txt", return_value=None),
                _patch_pipeline_externals(),
            ):
                ret = import_cmd.run(args)
            assert ret == 0
            assert list(Path(tmpdir).rglob("*.yaml")) == []

    def test_parse_error_counts_as_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            args = _import_namespace(output_dir=Path(tmpdir))
            with (
                patch("channel_ten.cli.reimport.list_twda_event_ids", return_value=[9999]),
                patch("channel_ten.cli.reimport.fetch_twda_txt", return_value="garbage"),
                _patch_pipeline_externals(),
            ):
                ret = import_cmd.run(args)
            assert ret == 1

    def test_validation_errors_route_to_errors_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            args = _import_namespace(output_dir=Path(tmpdir))
            with (
                patch("channel_ten.cli.reimport.list_twda_event_ids", return_value=[9999]),
                patch("channel_ten.cli.reimport.fetch_twda_txt", return_value=VALID_TWD),
                _patch_pipeline_externals(errors=["too_few_players"]),
            ):
                ret = import_cmd.run(args)
            assert ret == 0
            assert (Path(tmpdir) / "errors" / "too_few_players" / "9999.yaml").exists()

    def test_limit_caps_imports(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            args = _import_namespace(output_dir=Path(tmpdir), limit=1)
            with (
                patch(
                    "channel_ten.cli.reimport.list_twda_event_ids",
                    return_value=[1, 2, 3],
                ),
                patch(
                    "channel_ten.cli.reimport.fetch_twda_txt", return_value=VALID_TWD
                ) as mock_fetch,
                _patch_pipeline_externals(),
            ):
                import_cmd.run(args)
            assert mock_fetch.call_count == 1

    def test_rate_limit_returns_one(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            args = _import_namespace(output_dir=Path(tmpdir))
            with patch(
                "channel_ten.cli.reimport.list_twda_event_ids",
                side_effect=RuntimeError("rate limit exceeded"),
            ):
                ret = import_cmd.run(args)
            assert ret == 1

    def test_token_falls_back_to_env(self, monkeypatch: Any):
        monkeypatch.setenv("GITHUB_TOKEN", "env_tok")
        with tempfile.TemporaryDirectory() as tmpdir:
            args = _import_namespace(output_dir=Path(tmpdir))
            with patch(
                "channel_ten.cli.reimport.list_twda_event_ids", return_value=[]
            ) as mock_list:
                import_cmd.run(args)
            _, _kwargs_or_args = mock_list.call_args
            # token passed positionally: (client, token, ...)
            assert mock_list.call_args.args[1] == "env_tok"
