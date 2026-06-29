"""Tests for CLI entry point and shared utilities (_build_parser, main, _common)."""

import logging
import runpy
from unittest.mock import patch

import pytest

from channel_ten._logger import setup_logging
from channel_ten.cli import _build_parser, main  # pyright: ignore[reportPrivateUsage]

# ---------------------------------------------------------------------------
# _build_parser / main
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_parser_created(self):
        parser = _build_parser()
        assert parser is not None

    def test_subcommands_registered(self):
        parser = _build_parser()
        # Parse known subcommands — should not raise
        args = parser.parse_args(["parse", "somefile.txt"])
        assert args.command == "parse"

    def test_scrape_subcommand(self):
        parser = _build_parser()
        args = parser.parse_args(["scrape"])
        assert args.command == "scrape"

    def test_publish_subcommand(self):
        parser = _build_parser()
        args = parser.parse_args(["publish"])
        assert args.command == "publish"


class TestMain:
    def test_main_dispatches_and_exits(self):
        with (
            patch("sys.argv", ["channel-ten", "scrape"]),
            patch("channel_ten.cli.scrape.run", return_value=0) as mock_run,
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
            mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------


class TestDunderMain:
    """Cover channel_ten/cli/__main__.py (the `python -m channel_ten.cli` entry point)."""

    def test_main_called_via_run_module(self):
        with (
            patch("channel_ten.cli.main") as mock_main,
        ):
            mock_main.side_effect = SystemExit(0)
            with pytest.raises(SystemExit):
                runpy.run_module("channel_ten.cli", run_name="__main__")
            mock_main.assert_called_once()


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------


class TestSetupLogging:
    def test_verbose_false(self):
        setup_logging(False)
        logger = logging.getLogger("channel_ten")
        assert logger.level == logging.INFO

    def test_verbose_true(self):
        setup_logging(True)
        logger = logging.getLogger("channel_ten")
        assert logger.level == logging.DEBUG
