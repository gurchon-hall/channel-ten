"""Tests for the ``publish`` CLI subcommand."""

import argparse
import tempfile
from pathlib import Path
from unittest.mock import patch

from conftest import make_tournament

from channel_ten.cli import publish as publish_cmd
from channel_ten.publisher import BatchPRResult

# ---------------------------------------------------------------------------
# publish command
# ---------------------------------------------------------------------------


class TestPublishCommand:
    def test_register(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        publish_cmd.register(sub)
        args = parser.parse_args(["publish"])
        assert args.command == "publish"

    def test_run_no_token(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            args = argparse.Namespace(
                twds_dir=Path(tmpdir),
                delay=1.0,
                github_token=None,
                publish_dir=Path(tmpdir) / "publish",
                verbose=False,
            )
            with patch.dict("os.environ", {}, clear=True):
                with patch("channel_ten.cli.publish.os.environ.get", return_value=""):
                    ret = publish_cmd.run(args)
            assert ret == 1

    def test_run_no_yaml_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            args = argparse.Namespace(
                twds_dir=Path(tmpdir),
                delay=1.0,
                github_token="mytoken",
                publish_dir=Path(tmpdir) / "publish",
                verbose=False,
            )
            ret = publish_cmd.run(args)
            assert ret == 0

    def test_run_with_yaml_files(self):
        t = make_tournament()
        result = BatchPRResult(pr_url="https://github.com/pr/1", published=["9999"])

        with tempfile.TemporaryDirectory() as tmpdir:
            from channel_ten.output.yaml import write_tournament_yaml

            write_tournament_yaml(t, Path(tmpdir), overwrite=True)

            args = argparse.Namespace(
                twds_dir=Path(tmpdir),
                delay=0,
                github_token="mytoken",
                publish_dir=Path(tmpdir) / "publish",
                include_pre_2020=False,
                verbose=False,
            )
            with patch(
                "channel_ten.cli.publish.publish_all_as_single_pr",
                return_value=result,
            ):
                ret = publish_cmd.run(args)
            assert ret == 0

    def test_run_skipped_all(self):
        t = make_tournament()
        result = BatchPRResult(skipped_all=True, skipped=["9999"])

        with tempfile.TemporaryDirectory() as tmpdir:
            from channel_ten.output.yaml import write_tournament_yaml

            write_tournament_yaml(t, Path(tmpdir), overwrite=True)

            args = argparse.Namespace(
                twds_dir=Path(tmpdir),
                delay=0,
                github_token="mytoken",
                publish_dir=Path(tmpdir) / "publish",
                include_pre_2020=False,
                verbose=False,
            )
            with patch(
                "channel_ten.cli.publish.publish_all_as_single_pr",
                return_value=result,
            ):
                ret = publish_cmd.run(args)
            assert ret == 0

    def test_run_with_errors(self):
        t = make_tournament()
        result = BatchPRResult(
            pr_url="https://github.com/pr/2",
            published=["9999"],
            errors=[("bad_id", "some error")],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            from channel_ten.output.yaml import write_tournament_yaml

            write_tournament_yaml(t, Path(tmpdir), overwrite=True)

            args = argparse.Namespace(
                twds_dir=Path(tmpdir),
                delay=0,
                github_token="mytoken",
                publish_dir=Path(tmpdir) / "publish",
                include_pre_2020=False,
                verbose=False,
            )
            with patch(
                "channel_ten.cli.publish.publish_all_as_single_pr",
                return_value=result,
            ):
                ret = publish_cmd.run(args)
            assert ret == 1

    def test_run_no_pr_url(self):
        t = make_tournament()
        result = BatchPRResult(published=["9999"])  # no pr_url

        with tempfile.TemporaryDirectory() as tmpdir:
            from channel_ten.output.yaml import write_tournament_yaml

            write_tournament_yaml(t, Path(tmpdir), overwrite=True)

            args = argparse.Namespace(
                twds_dir=Path(tmpdir),
                delay=0,
                github_token="mytoken",
                publish_dir=Path(tmpdir) / "publish",
                include_pre_2020=False,
                verbose=False,
            )
            with patch(
                "channel_ten.cli.publish.publish_all_as_single_pr",
                return_value=result,
            ):
                ret = publish_cmd.run(args)
            assert ret == 0

    def test_run_nothing_to_publish_after_load(self):
        """Test when all YAML files fail to load."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_yaml = Path(tmpdir) / "bad.yaml"
            bad_yaml.write_text(": : : invalid yaml {{{{", encoding="utf-8")

            args = argparse.Namespace(
                twds_dir=Path(tmpdir),
                delay=0,
                github_token="mytoken",
                publish_dir=Path(tmpdir) / "publish",
                verbose=False,
            )
            ret = publish_cmd.run(args)
            # No valid tournaments loaded
            assert ret == 0

    def test_run_skips_error_decks(self):
        """Decks inside twds/errors/ must not be submitted to the publisher."""
        t = make_tournament()
        result = BatchPRResult(pr_url="https://github.com/pr/1", published=["9999"])

        with tempfile.TemporaryDirectory() as tmpdir:
            from channel_ten.output.yaml import write_tournament_yaml

            # Place a valid YAML in the errors subdirectory
            errors_dir = Path(tmpdir) / "errors" / "unconfirmed_winner"
            errors_dir.mkdir(parents=True)
            write_tournament_yaml(t, errors_dir, overwrite=True)

            args = argparse.Namespace(
                twds_dir=Path(tmpdir),
                delay=0,
                github_token="mytoken",
                publish_dir=Path(tmpdir) / "publish",
                include_pre_2020=False,
                verbose=False,
            )
            with patch(
                "channel_ten.cli.publish.publish_all_as_single_pr",
                return_value=result,
            ) as mock_publish:
                ret = publish_cmd.run(args)
            # No valid tournaments outside errors/ — nothing to publish
            assert ret == 0
            mock_publish.assert_not_called()

    def test_write_publish_report_with_pr_url(self):
        t = make_tournament()
        result = BatchPRResult(pr_url="https://github.com/pr/1", published=["9999"])
        with tempfile.TemporaryDirectory() as tmpdir:
            path = publish_cmd._write_publish_report(  # pyright: ignore[reportPrivateUsage]
                result,
                Path(tmpdir),
                "2023-03-25",
                [t],
            )
            assert path.exists()
            content = path.read_text()
            assert "https://github.com/pr/1" in content

    def test_write_publish_report_skipped_all(self):
        result = BatchPRResult(skipped_all=True)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = publish_cmd._write_publish_report(  # pyright: ignore[reportPrivateUsage]
                result,
                Path(tmpdir),
                "2023-03-25",
                [],
            )
            content = path.read_text()
            assert "already present on master" in content

    def test_write_publish_report_no_pr(self):
        result = BatchPRResult()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = publish_cmd._write_publish_report(  # pyright: ignore[reportPrivateUsage]
                result,
                Path(tmpdir),
                "2023-03-25",
                [],
            )
            content = path.read_text()
            assert "No PR opened" in content

    def test_write_publish_report_with_errors(self):
        result = BatchPRResult(
            published=["9999"],
            errors=[("bad_id", "Failed to commit")],
        )
        t = make_tournament()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = publish_cmd._write_publish_report(  # pyright: ignore[reportPrivateUsage]
                result,
                Path(tmpdir),
                "2023-03-25",
                [t],
            )
            content = path.read_text()
            assert "bad_id" in content

    def test_write_publish_report_with_skipped(self):
        result = BatchPRResult(skipped=["8888"])
        with tempfile.TemporaryDirectory() as tmpdir:
            path = publish_cmd._write_publish_report(  # pyright: ignore[reportPrivateUsage]
                result,
                Path(tmpdir),
                "2023-03-25",
                [],
            )
            content = path.read_text()
            assert "8888" in content

    def test_write_publish_report_dry_run_with_timestamp(self):
        result = BatchPRResult(dry_run=True, published=["9999"])
        with tempfile.TemporaryDirectory() as tmpdir:
            path = publish_cmd._write_publish_report(  # pyright: ignore[reportPrivateUsage]
                result,
                Path(tmpdir),
                "2023-03-25",
                [],
                timestamp="2023-03-25-10-30-00",
            )
            content = path.read_text()
        assert "dry-run" in path.name
        assert "DRY RUN" in content
        assert "10-30-00" in path.name

    def test_write_publish_report_dry_run_no_timestamp(self):
        result = BatchPRResult(dry_run=True)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = publish_cmd._write_publish_report(  # pyright: ignore[reportPrivateUsage]
                result,
                Path(tmpdir),
                "2023-03-25",
                [],
                timestamp=None,
            )
        assert "dry-run" in path.name

    def test_write_publish_report_published_without_event_url(self):
        """Tournament with no event_url: name appears without a hyperlink."""
        t = make_tournament()
        t2 = t.model_copy(update={"event_url": None})
        result = BatchPRResult(published=[t2.event_id or "unknown"])
        with tempfile.TemporaryDirectory() as tmpdir:
            path = publish_cmd._write_publish_report(  # pyright: ignore[reportPrivateUsage]
                result,
                Path(tmpdir),
                "2023-03-25",
                [t2],
            )
            content = path.read_text()
        assert "Test Event" in content

    def test_run_nothing_after_year_filter(self):
        """When all loaded tournaments pre-date 2020, nothing to publish."""
        from datetime import date as _date

        t_old = make_tournament()
        t_old = t_old.model_copy(update={"date_start": _date(2019, 1, 1)})

        with tempfile.TemporaryDirectory() as tmpdir:
            from channel_ten.output.yaml import write_tournament_yaml

            write_tournament_yaml(t_old, Path(tmpdir), overwrite=True)

            args = argparse.Namespace(
                twds_dir=Path(tmpdir),
                delay=0,
                github_token="mytoken",
                publish_dir=Path(tmpdir) / "publish",
                include_pre_2020=False,
                verbose=False,
            )
            with patch("channel_ten.cli.publish.publish_all_as_single_pr") as mock_pub:
                ret = publish_cmd.run(args)
            mock_pub.assert_not_called()
        assert ret == 0

    def test_run_dry_run_prints_summary(self):
        t = make_tournament()
        result = BatchPRResult(dry_run=True, published=["9999"])

        with tempfile.TemporaryDirectory() as tmpdir:
            from channel_ten.output.yaml import write_tournament_yaml

            write_tournament_yaml(t, Path(tmpdir), overwrite=True)

            args = argparse.Namespace(
                twds_dir=Path(tmpdir),
                delay=0,
                github_token="mytoken",
                publish_dir=Path(tmpdir) / "publish",
                include_pre_2020=True,
                dry_run=True,
                verbose=False,
            )
            with patch(
                "channel_ten.cli.publish.publish_all_as_single_pr",
                return_value=result,
            ):
                ret = publish_cmd.run(args)
        assert ret == 0

    def test_run_skipped_entries_printed(self):
        t = make_tournament()
        result = BatchPRResult(published=["9999"], skipped=["8888"])

        with tempfile.TemporaryDirectory() as tmpdir:
            from channel_ten.output.yaml import write_tournament_yaml

            write_tournament_yaml(t, Path(tmpdir), overwrite=True)

            args = argparse.Namespace(
                twds_dir=Path(tmpdir),
                delay=0,
                github_token="mytoken",
                publish_dir=Path(tmpdir) / "publish",
                include_pre_2020=True,
                dry_run=False,
                verbose=False,
            )
            with patch(
                "channel_ten.cli.publish.publish_all_as_single_pr",
                return_value=result,
            ):
                ret = publish_cmd.run(args)
        assert ret == 0

    def test_run_report_write_failure_is_swallowed(self):
        """A crash in _write_publish_report must not abort the command."""
        t = make_tournament()
        result = BatchPRResult(pr_url="https://github.com/pr/1", published=["9999"])

        with tempfile.TemporaryDirectory() as tmpdir:
            from channel_ten.output.yaml import write_tournament_yaml

            write_tournament_yaml(t, Path(tmpdir), overwrite=True)

            args = argparse.Namespace(
                twds_dir=Path(tmpdir),
                delay=0,
                github_token="mytoken",
                publish_dir=Path(tmpdir) / "publish",
                include_pre_2020=True,
                dry_run=False,
                verbose=False,
            )
            with patch(
                "channel_ten.cli.publish.publish_all_as_single_pr",
                return_value=result,
            ):
                with patch(
                    "channel_ten.cli.publish._write_publish_report",
                    side_effect=OSError("disk full"),
                ):
                    ret = publish_cmd.run(args)
        assert ret == 0
