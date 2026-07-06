"""Tests for channel_ten.publisher using httpx mocking."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import httpx
import pytest
from conftest import make_tournament

from channel_ten.github import (
    FORK_REPO,
    close_pull_request,
    create_branch,
    delete_branch,
    ensure_fork,
    file_exists_on_branch,
    find_existing_pr,
    get_authenticated_user,
    get_branch_sha,
    headers,
    list_open_prs_from_fork,
    open_pull_request,
    put_file,
)
from channel_ten.publisher import (
    BatchPRResult,
    publish_all_as_single_pr,
    sanitize_branch_name,
)

# ---------------------------------------------------------------------------
# headers
# ---------------------------------------------------------------------------


class TestHeaders:
    def test_raises_without_token(self):
        with patch("channel_ten.github._GITHUB_TOKEN", None):
            with pytest.raises(ValueError, match="GitHub token"):
                headers(token=None)

    def test_returns_dict_with_token(self):
        h = headers(token="mytoken")
        assert h["Authorization"] == "Bearer mytoken"
        assert "Accept" in h

    def test_uses_env_token_when_not_passed(self):
        with patch("channel_ten.github._GITHUB_TOKEN", "env_token"):
            h = headers(token=None)
        assert h["Authorization"] == "Bearer env_token"


# ---------------------------------------------------------------------------
# sanitize_branch_name
# ---------------------------------------------------------------------------


class TestSanitizeBranchName:
    def test_lowercase(self):
        assert sanitize_branch_name("Hello World") == "hello-world"

    def test_special_chars_replaced(self):
        assert sanitize_branch_name("test!@#$name") == "test-name"

    def test_truncated_at_50(self):
        long_name = "a" * 100
        result = sanitize_branch_name(long_name)
        assert len(result) <= 50

    def test_strips_leading_trailing_dashes(self):
        result = sanitize_branch_name("--hello--")
        assert not result.startswith("-")
        assert not result.endswith("-")


# ---------------------------------------------------------------------------
# Low-level API helpers
# ---------------------------------------------------------------------------


class TestGetAuthenticatedUser:
    def test_returns_login(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"login": "testuser"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp

        result = get_authenticated_user(mock_client, token="mytoken")
        assert result == "testuser"


class TestGetBranchSha:
    def test_returns_sha(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"object": {"sha": "abc123"}}
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp

        sha = get_branch_sha(mock_client, "master", token="mytoken")
        assert sha == "abc123"


class TestCreateBranch:
    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp

        # Should not raise
        create_branch(mock_client, "new-branch", "abc123", token="mytoken")

    def test_already_exists_422(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 422
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp

        # Should not raise even if 422
        create_branch(mock_client, "existing-branch", "abc123", token="mytoken")


class TestFileExistsOnBranch:
    def test_returns_true_when_200(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp

        result = file_exists_on_branch(mock_client, "decks/test.txt", "master", token="t")
        assert result is True

    def test_returns_false_when_404(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp

        result = file_exists_on_branch(mock_client, "decks/test.txt", "master", token="t")
        assert result is False


class TestPutFile:
    def test_creates_new_file(self):
        # GET returns 404 (no existing file), PUT succeeds
        get_resp = MagicMock()
        get_resp.status_code = 404

        put_resp = MagicMock()
        put_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = get_resp
        mock_client.put.return_value = put_resp

        put_file(mock_client, "decks/test.txt", "content", "branch", "msg", token="t")
        mock_client.put.assert_called_once()

    def test_updates_existing_file(self):
        # GET returns 200 with existing sha
        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.json.return_value = {"sha": "existing_sha"}

        put_resp = MagicMock()
        put_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = get_resp
        mock_client.put.return_value = put_resp

        put_file(mock_client, "decks/test.txt", "content", "branch", "msg", token="t")
        # PUT was called with sha in body
        call_kwargs = mock_client.put.call_args[1]
        assert call_kwargs["json"]["sha"] == "existing_sha"


class TestOpenPullRequest:
    def test_returns_pr_url(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"html_url": "https://github.com/owner/repo/pull/1"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp

        url = open_pull_request(mock_client, "branch", "Title", "Body", token="t")
        assert url == "https://github.com/owner/repo/pull/1"

    def test_existing_pr_422(self):
        # 422 with "pull request already exists"
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 422
        mock_post_resp.json.return_value = {
            "errors": [{"message": "A pull request already exists for this head"}]
        }
        mock_post_resp.raise_for_status = MagicMock()

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = [{"html_url": "https://github.com/owner/repo/pull/2"}]

        mock_client = MagicMock()
        mock_client.post.return_value = mock_post_resp
        mock_client.get.return_value = mock_get_resp

        url = open_pull_request(mock_client, "branch", "Title", "Body", token="t")
        assert url == "https://github.com/owner/repo/pull/2"

    def test_other_422_raises(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 422
        mock_resp.json.return_value = {"errors": [{"message": "Unrelated validation error"}]}
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "422", request=MagicMock(), response=MagicMock()
        )

        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp

        with pytest.raises(httpx.HTTPStatusError):
            open_pull_request(mock_client, "branch", "Title", "Body", token="t")


class TestFindExistingPr:
    def test_returns_url_when_found(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"html_url": "https://github.com/owner/repo/pull/5"}]

        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp

        url = find_existing_pr(mock_client, "branch", token="t")
        assert url == "https://github.com/owner/repo/pull/5"

    def test_returns_none_when_empty(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []

        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp

        url = find_existing_pr(mock_client, "branch", token="t")
        assert url is None

    def test_returns_none_on_non_200(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = []

        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp

        url = find_existing_pr(mock_client, "branch", token="t")
        assert url is None


# ---------------------------------------------------------------------------
# BatchPRResult
# ---------------------------------------------------------------------------


class TestDeleteBranch:
    def test_success_204(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 204

        mock_client = MagicMock()
        mock_client.delete.return_value = mock_resp

        # Should not raise
        delete_branch(mock_client, "my-branch", token="mytoken", owner="testuser")
        mock_client.delete.assert_called_once()

    def test_non_204_logs_warning(self, caplog: pytest.LogCaptureFixture):
        import logging

        mock_resp = MagicMock()
        mock_resp.status_code = 404

        mock_client = MagicMock()
        mock_client.delete.return_value = mock_resp

        with caplog.at_level(logging.WARNING, logger="channel_ten.github"):
            delete_branch(mock_client, "missing-branch", token="mytoken", owner="testuser")

        assert any("Could not delete branch" in r.message for r in caplog.records)


class TestListOpenPrsFromFork:
    def test_filters_by_fork_owner(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = [
            {
                "number": 1,
                "html_url": "https://github.com/owner/repo/pull/1",
                "head": {
                    "ref": "twd/weekly-decks-2026-06-01",
                    "repo": {"owner": {"login": "gurchon-hall"}},
                },
            },
            {
                "number": 2,
                "html_url": "https://github.com/owner/repo/pull/2",
                "head": {"ref": "some-other-branch", "repo": {"owner": {"login": "someone-else"}}},
            },
        ]

        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp

        prs = list_open_prs_from_fork(mock_client, "gurchon-hall", token="t")
        assert prs == [
            {
                "number": 1,
                "branch": "twd/weekly-decks-2026-06-01",
                "html_url": "https://github.com/owner/repo/pull/1",
            }
        ]

    def test_returns_empty_when_no_matches(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = []

        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp

        prs = list_open_prs_from_fork(mock_client, "gurchon-hall", token="t")
        assert prs == []


class TestClosePullRequest:
    def test_sends_closed_state(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.patch.return_value = mock_resp

        close_pull_request(mock_client, 42, token="t")

        call_kwargs = mock_client.patch.call_args[1]
        assert call_kwargs["json"] == {"state": "closed"}


class TestBatchPRResult:
    def test_defaults(self):
        result = BatchPRResult()
        assert result.pr_url is None
        assert result.published == []
        assert result.skipped == []
        assert result.errors == []
        assert result.skipped_all is False
        assert result.dry_run is False
        assert result.closed_prs == []

    def test_dry_run_flag(self):
        result = BatchPRResult(dry_run=True)
        assert result.dry_run is True


# ---------------------------------------------------------------------------
# publish_all_as_single_pr
# ---------------------------------------------------------------------------


class TestPublishAllAsSinglePr:
    def test_all_skipped_returns_skipped_all(self):
        t = make_tournament()

        with (
            patch("channel_ten.publisher.ensure_fork", return_value="testuser"),
            patch("channel_ten.publisher.file_exists_on_branch", return_value=True),
        ):
            result = publish_all_as_single_pr([t], token="mytoken", delay=0)

        assert result.skipped_all is True
        assert result.pr_url is None

    def test_fork_failure_returns_errors(self):
        t = make_tournament()

        err = httpx.HTTPStatusError("403", request=MagicMock(), response=MagicMock())
        with patch("channel_ten.publisher.ensure_fork", side_effect=err):
            result = publish_all_as_single_pr([t], token="mytoken", delay=0)

        assert len(result.errors) == 1

    def test_successful_publish(self):
        t = make_tournament()

        with (
            patch("channel_ten.publisher.ensure_fork", return_value="testuser"),
            patch("channel_ten.publisher.file_exists_on_branch", return_value=False),
            patch("channel_ten.publisher.list_open_prs_from_fork", return_value=[]),
            patch("channel_ten.publisher.get_branch_sha", return_value="abc123"),
            patch("channel_ten.publisher.create_branch"),
            patch(
                "channel_ten.publisher.push_files_to_branch",
                return_value=(["decks/9999.txt"], []),
            ),
            patch(
                "channel_ten.publisher.open_pull_request",
                return_value="https://github.com/pr/1",
            ),
        ):
            result = publish_all_as_single_pr([t], token="mytoken", delay=0)

        assert result.pr_url == "https://github.com/pr/1"
        assert len(result.published) == 1

    def test_branch_creation_failure(self):
        t = make_tournament()
        err = httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock())

        with (
            patch("channel_ten.publisher.ensure_fork", return_value="testuser"),
            patch("channel_ten.publisher.file_exists_on_branch", return_value=False),
            patch("channel_ten.publisher.list_open_prs_from_fork", return_value=[]),
            patch("channel_ten.publisher.get_branch_sha", side_effect=err),
        ):
            result = publish_all_as_single_pr([t], token="mytoken", delay=0)

        assert len(result.errors) == 1
        assert "Branch creation failed" in result.errors[0][1]

    def test_put_file_http_error(self):
        t = make_tournament()

        with (
            patch("channel_ten.publisher.ensure_fork", return_value="testuser"),
            patch("channel_ten.publisher.file_exists_on_branch", return_value=False),
            patch("channel_ten.publisher.list_open_prs_from_fork", return_value=[]),
            patch("channel_ten.publisher.get_branch_sha", return_value="abc123"),
            patch("channel_ten.publisher.create_branch"),
            patch(
                "channel_ten.publisher.push_files_to_branch",
                return_value=([], [("decks/9999.txt", "HTTP 422: Unprocessable")]),
            ),
        ):
            result = publish_all_as_single_pr([t], token="mytoken", delay=0)

        assert len(result.errors) == 1
        assert result.pr_url is None  # no PR if nothing published

    def test_put_file_generic_error(self):
        t = make_tournament()

        with (
            patch("channel_ten.publisher.ensure_fork", return_value="testuser"),
            patch("channel_ten.publisher.file_exists_on_branch", return_value=False),
            patch("channel_ten.publisher.list_open_prs_from_fork", return_value=[]),
            patch("channel_ten.publisher.get_branch_sha", return_value="abc123"),
            patch("channel_ten.publisher.create_branch"),
            patch(
                "channel_ten.publisher.push_files_to_branch",
                return_value=([], [("decks/9999.txt", "oops")]),
            ),
        ):
            result = publish_all_as_single_pr([t], token="mytoken", delay=0)

        assert len(result.errors) == 1

    def test_pr_open_http_error_does_not_raise(self):
        t = make_tournament()
        err = httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock())

        with (
            patch("channel_ten.publisher.ensure_fork", return_value="testuser"),
            patch("channel_ten.publisher.file_exists_on_branch", return_value=False),
            patch("channel_ten.publisher.list_open_prs_from_fork", return_value=[]),
            patch("channel_ten.publisher.get_branch_sha", return_value="abc123"),
            patch("channel_ten.publisher.create_branch"),
            patch(
                "channel_ten.publisher.push_files_to_branch",
                return_value=(["decks/9999.txt"], []),
            ),
            patch("channel_ten.publisher.open_pull_request", side_effect=err),
        ):
            result = publish_all_as_single_pr([t], token="mytoken", delay=0)

        # Published but no PR URL
        assert len(result.published) == 1
        assert result.pr_url is None

    def test_multiple_tournaments_with_mix(self):
        t1 = make_tournament(event_url="https://www.vekn.net/event-calendar/event/9001")
        t2 = make_tournament(event_url="https://www.vekn.net/event-calendar/event/9002")

        def file_exists(client: httpx.Client, path: Path, branch: str, token: str):
            return "9001" in str(path)  # t1 already exists

        with (
            patch("channel_ten.publisher.ensure_fork", return_value="testuser"),
            patch("channel_ten.publisher.file_exists_on_branch", side_effect=file_exists),
            patch("channel_ten.publisher.list_open_prs_from_fork", return_value=[]),
            patch("channel_ten.publisher.get_branch_sha", return_value="abc123"),
            patch("channel_ten.publisher.create_branch"),
            patch(
                "channel_ten.publisher.push_files_to_branch",
                return_value=(["decks/9002.txt"], []),
            ),
            patch(
                "channel_ten.publisher.open_pull_request",
                return_value="https://github.com/pr/1",
            ),
        ):
            result = publish_all_as_single_pr([t1, t2], token="mytoken", delay=0)

        assert 9001 in result.skipped
        assert 9002 in result.published

    def test_closes_stale_prs_and_branches_before_publishing(self):
        t = make_tournament()

        stale_prs = [
            {"number": 7, "branch": "twd/weekly-decks-2026-05-01", "html_url": "https://gh/pr/7"}
        ]

        with (
            patch("channel_ten.publisher.ensure_fork", return_value="gurchon-hall"),
            patch("channel_ten.publisher.file_exists_on_branch", return_value=False),
            patch("channel_ten.publisher.list_open_prs_from_fork", return_value=stale_prs),
            patch("channel_ten.publisher.close_pull_request") as mock_close,
            patch("channel_ten.publisher.delete_branch") as mock_del,
            patch("channel_ten.publisher.get_branch_sha", return_value="abc123"),
            patch("channel_ten.publisher.create_branch"),
            patch(
                "channel_ten.publisher.push_files_to_branch",
                return_value=(["decks/9999.txt"], []),
            ),
            patch(
                "channel_ten.publisher.open_pull_request",
                return_value="https://github.com/pr/new",
            ),
        ):
            result = publish_all_as_single_pr([t], token="mytoken", delay=0)

        mock_close.assert_called_once_with(ANY, 7, "mytoken")
        mock_del.assert_called_once_with(
            ANY, "twd/weekly-decks-2026-05-01", "mytoken", owner="gurchon-hall", repo=FORK_REPO
        )
        assert result.closed_prs == ["https://gh/pr/7"]

    def test_does_not_close_own_run_branch(self):
        t = make_tournament()
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        own_branch = f"twd/weekly-decks-{today}"
        stale_prs = [{"number": 7, "branch": own_branch, "html_url": "https://gh/pr/7"}]

        with (
            patch("channel_ten.publisher.ensure_fork", return_value="gurchon-hall"),
            patch("channel_ten.publisher.file_exists_on_branch", return_value=False),
            patch("channel_ten.publisher.list_open_prs_from_fork", return_value=stale_prs),
            patch("channel_ten.publisher.close_pull_request") as mock_close,
            patch("channel_ten.publisher.get_branch_sha", return_value="abc123"),
            patch("channel_ten.publisher.create_branch"),
            patch(
                "channel_ten.publisher.push_files_to_branch",
                return_value=(["decks/9999.txt"], []),
            ),
            patch(
                "channel_ten.publisher.open_pull_request",
                return_value="https://github.com/pr/new",
            ),
        ):
            result = publish_all_as_single_pr([t], token="mytoken", delay=0)

        mock_close.assert_not_called()
        assert result.closed_prs == []

    def test_dry_run_skips_stale_pr_cleanup(self):
        t = make_tournament()

        with (
            patch("channel_ten.publisher.ensure_fork", return_value="gurchon-hall"),
            patch("channel_ten.publisher.file_exists_on_branch", return_value=False),
            patch("channel_ten.publisher.list_open_prs_from_fork") as mock_list,
            patch("channel_ten.publisher.get_branch_sha", return_value="abc123"),
            patch("channel_ten.publisher.create_branch"),
            patch(
                "channel_ten.publisher.push_files_to_branch",
                return_value=(["decks/9999.txt"], []),
            ),
            patch("channel_ten.publisher.delete_branch"),
        ):
            publish_all_as_single_pr([t], token="mytoken", delay=0, dry_run=True)

        mock_list.assert_not_called()

    def test_stale_pr_listing_failure_does_not_block_publish(self):
        t = make_tournament()
        err = httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock())

        with (
            patch("channel_ten.publisher.ensure_fork", return_value="gurchon-hall"),
            patch("channel_ten.publisher.file_exists_on_branch", return_value=False),
            patch("channel_ten.publisher.list_open_prs_from_fork", side_effect=err),
            patch("channel_ten.publisher.get_branch_sha", return_value="abc123"),
            patch("channel_ten.publisher.create_branch"),
            patch(
                "channel_ten.publisher.push_files_to_branch",
                return_value=(["decks/9999.txt"], []),
            ),
            patch(
                "channel_ten.publisher.open_pull_request",
                return_value="https://github.com/pr/new",
            ),
        ):
            result = publish_all_as_single_pr([t], token="mytoken", delay=0)

        assert result.pr_url == "https://github.com/pr/new"
        assert result.closed_prs == []

    def test_dry_run_deletes_branch_and_no_pr(self):
        t = make_tournament()

        with (
            patch("channel_ten.publisher.ensure_fork", return_value="testuser"),
            patch("channel_ten.publisher.file_exists_on_branch", return_value=False),
            patch("channel_ten.publisher.get_branch_sha", return_value="abc123"),
            patch("channel_ten.publisher.create_branch"),
            patch(
                "channel_ten.publisher.push_files_to_branch",
                return_value=(["decks/9999.txt"], []),
            ),
            patch("channel_ten.publisher.open_pull_request") as mock_pr,
            patch("channel_ten.publisher.delete_branch") as mock_del,
        ):
            result = publish_all_as_single_pr([t], token="mytoken", delay=0, dry_run=True)

        assert result.dry_run is True
        assert result.pr_url is None
        assert len(result.published) == 1
        mock_pr.assert_not_called()
        mock_del.assert_called_once()

    def test_dry_run_all_skipped_no_branch_deleted(self):
        t = make_tournament()

        with (
            patch("channel_ten.publisher.ensure_fork", return_value="testuser"),
            patch("channel_ten.publisher.file_exists_on_branch", return_value=True),
            patch("channel_ten.publisher.delete_branch") as mock_del,
        ):
            result = publish_all_as_single_pr([t], token="mytoken", delay=0, dry_run=True)

        assert result.skipped_all is True
        mock_del.assert_not_called()

    def test_dry_run_all_commits_failed_deletes_branch(self):
        t = make_tournament()

        with (
            patch("channel_ten.publisher.ensure_fork", return_value="testuser"),
            patch("channel_ten.publisher.file_exists_on_branch", return_value=False),
            patch("channel_ten.publisher.get_branch_sha", return_value="abc123"),
            patch("channel_ten.publisher.create_branch"),
            patch(
                "channel_ten.publisher.push_files_to_branch",
                return_value=([], [("decks/9999.txt", "HTTP 500: Server Error")]),
            ),
            patch("channel_ten.publisher.delete_branch") as mock_del,
        ):
            result = publish_all_as_single_pr([t], token="mytoken", delay=0, dry_run=True)

        assert len(result.errors) == 1
        assert result.pr_url is None
        mock_del.assert_called_once()

    def test_422_existing_pr_not_found_raises(self):
        """
        422 with 'pull request already exists'
        but find_existing_pr returns None → raise_for_status.
        """
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 422
        mock_post_resp.json.return_value = {
            "errors": [{"message": "A pull request already exists for this head"}]
        }
        mock_post_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "422", request=MagicMock(), response=MagicMock()
        )

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = []  # find_existing_pr returns None

        mock_client = MagicMock()
        mock_client.post.return_value = mock_post_resp
        mock_client.get.return_value = mock_get_resp

        with pytest.raises(httpx.HTTPStatusError):
            open_pull_request(mock_client, "branch", "Title", "Body", token="t")

    def test_with_errors_in_pr_body(self):
        """Partial success: one published, one errored; PR is still opened."""
        t1 = make_tournament(event_url="https://www.vekn.net/event-calendar/event/9001")
        t2 = make_tournament(event_url="https://www.vekn.net/event-calendar/event/9002")

        with (
            patch("channel_ten.publisher.ensure_fork", return_value="testuser"),
            patch("channel_ten.publisher.file_exists_on_branch", return_value=False),
            patch("channel_ten.publisher.list_open_prs_from_fork", return_value=[]),
            patch("channel_ten.publisher.get_branch_sha", return_value="abc123"),
            patch("channel_ten.publisher.create_branch"),
            patch(
                "channel_ten.publisher.push_files_to_branch",
                return_value=(
                    ["decks/9001.txt"],
                    [("decks/9002.txt", "HTTP 422: Bad")],
                ),
            ),
            patch(
                "channel_ten.publisher.open_pull_request",
                return_value="https://github.com/pr/3",
            ),
        ):
            result = publish_all_as_single_pr([t1, t2], token="mytoken", delay=0)

        assert len(result.published) == 1
        assert len(result.errors) == 1
        assert result.pr_url == "https://github.com/pr/3"


# ---------------------------------------------------------------------------
# ensure_fork
# ---------------------------------------------------------------------------


class TestEnsureFork:
    def test_fork_already_exists_skips_post(self):
        """When the fork already exists, no POST /forks is issued at all.

        This is the fix for duplicate forks: calling POST unconditionally on
        every run risked GitHub creating a second, differently-named fork if
        a same-named repo existed under the org for any reason other than a
        clean prior fork.
        """
        mock_client = MagicMock()
        fork_resp = MagicMock()
        fork_resp.status_code = 200
        mock_client.get.return_value = fork_resp

        result = ensure_fork(mock_client, token="mytoken")

        assert result == "gurchon-hall"
        mock_client.post.assert_not_called()
        assert mock_client.get.call_count == 1

    def test_fork_created_when_missing(self):
        """When the fork doesn't exist yet (pre-check 404), it's created via POST."""
        mock_client = MagicMock()
        user_resp = MagicMock()
        user_resp.json.return_value = {"login": "testuser"}
        fork_not_found = MagicMock()
        fork_not_found.status_code = 404
        fork_ready = MagicMock()
        fork_ready.status_code = 200
        mock_client.get.side_effect = [fork_not_found, user_resp, fork_ready]
        mock_client.post.return_value = MagicMock()

        result = ensure_fork(mock_client, token="mytoken")
        assert result == "gurchon-hall"
        mock_client.post.assert_called_once()

    def test_forks_into_gurchon_hall_org_as_twd_fork(self):
        """The fork request targets the gurchon-hall org, under the twd-fork name."""
        mock_client = MagicMock()
        user_resp = MagicMock()
        user_resp.json.return_value = {"login": "testuser"}
        fork_not_found = MagicMock()
        fork_not_found.status_code = 404
        fork_ready = MagicMock()
        fork_ready.status_code = 200
        mock_client.get.side_effect = [fork_not_found, user_resp, fork_ready]
        mock_client.post.return_value = MagicMock()

        ensure_fork(mock_client, token="mytoken")

        call_kwargs = mock_client.post.call_args[1]
        assert call_kwargs["json"] == {"organization": "gurchon-hall", "name": FORK_REPO}

    def test_pre_check_and_poll_target_fork_repo_name(self):
        """Both the pre-check and the readiness poll hit gurchon-hall/<FORK_REPO>, not TWDA_REPO."""
        mock_client = MagicMock()
        fork_resp = MagicMock()
        fork_resp.status_code = 200
        mock_client.get.return_value = fork_resp

        ensure_fork(mock_client, token="mytoken")

        checked_url = mock_client.get.call_args[0][0]
        assert checked_url.endswith(f"/repos/gurchon-hall/{FORK_REPO}")

    def test_fork_polls_until_ready(self):
        """Polls until the fork becomes available (first 404, then 200)."""
        mock_client = MagicMock()
        user_resp = MagicMock()
        user_resp.json.return_value = {"login": "testuser"}
        fork_not_found = MagicMock()
        fork_not_found.status_code = 404
        fork_ready = MagicMock()
        fork_ready.status_code = 200
        mock_client.get.side_effect = [
            fork_not_found,  # pre-check: not created yet
            user_resp,
            fork_not_found,  # poll attempt 1: still not ready
            fork_ready,  # poll attempt 2: ready
        ]
        mock_client.post.return_value = MagicMock()

        with patch("channel_ten.github.time") as mock_time:
            result = ensure_fork(mock_client, token="mytoken")

        assert result == "gurchon-hall"
        mock_time.sleep.assert_called_once_with(1)
