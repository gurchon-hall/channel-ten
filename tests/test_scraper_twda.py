"""Tests for the GiottoVerducci/TWD read-only source (channel_ten.scraper._twda)."""

import logging
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from channel_ten.scraper._twda import (
    fetch_twda_txt,
    list_twda_event_ids,
    twda_headers,
)


def _mock_response(
    status_code: int = 200,
    json_data: Any = None,
    text: str = "",
    headers: dict[str, str] | None = None,
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.text = text
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# _twda_headers
# ---------------------------------------------------------------------------


class TestTwdaHeaders:
    def test_no_token_has_no_authorization(self):
        headers = twda_headers(None)
        assert "Authorization" not in headers
        assert headers["Accept"] == "application/vnd.github+json"

    def test_with_token_sets_bearer(self):
        headers = twda_headers("ghp_secret")
        assert headers["Authorization"] == "Bearer ghp_secret"


# ---------------------------------------------------------------------------
# list_twda_event_ids
# ---------------------------------------------------------------------------


class TestListTwdaEventIds:
    def test_filters_and_sorts_deck_ids(self):
        tree = {
            "tree": [
                {"type": "blob", "path": "decks/8470.txt"},
                {"type": "blob", "path": "decks/9999.txt"},
                {"type": "blob", "path": "decks/abc.txt"},  # not numeric
                {"type": "blob", "path": "README.md"},  # not a deck
                {"type": "tree", "path": "decks"},  # directory entry
                {"type": "blob", "path": "decks/100.txt"},
            ],
            "truncated": False,
        }
        client = MagicMock()
        client.get.return_value = _mock_response(json_data=tree)

        result = list_twda_event_ids(client, token=None, delay=0)
        assert result == [100, 8470, 9999]

    def test_rate_limit_raises_runtime_error(self):
        client = MagicMock()
        client.get.return_value = _mock_response(
            status_code=403,
            headers={"X-RateLimit-Remaining": "0"},
        )
        with pytest.raises(RuntimeError, match="rate limit"):
            list_twda_event_ids(client, token=None, delay=0)

    def test_other_http_error_propagates(self):
        client = MagicMock()
        resp = _mock_response(status_code=500)
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "boom", request=MagicMock(), response=MagicMock()
        )
        client.get.return_value = resp
        with pytest.raises(httpx.HTTPStatusError):
            list_twda_event_ids(client, token=None, delay=0)

    def test_truncated_tree_logs_warning(self, caplog: pytest.LogCaptureFixture):
        tree = {"tree": [{"type": "blob", "path": "decks/1.txt"}], "truncated": True}
        client = MagicMock()
        client.get.return_value = _mock_response(json_data=tree)

        with caplog.at_level(logging.WARNING):
            result = list_twda_event_ids(client, token=None, delay=0)
        assert result == [1]
        assert any("truncated" in r.message for r in caplog.records)

    def test_passes_token_in_headers(self):
        client = MagicMock()
        client.get.return_value = _mock_response(json_data={"tree": []})
        list_twda_event_ids(client, token="ghp_x", delay=0)
        _, kwargs = client.get.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer ghp_x"
        assert kwargs["params"] == {"recursive": "1"}


# ---------------------------------------------------------------------------
# fetch_twda_txt
# ---------------------------------------------------------------------------


class TestFetchTwdaTxt:
    def test_returns_text_on_200(self):
        client = MagicMock()
        client.get.return_value = _mock_response(status_code=200, text="deck content")
        assert fetch_twda_txt(client, 8470, delay=0) == "deck content"

    def test_returns_none_on_404(self):
        client = MagicMock()
        client.get.return_value = _mock_response(status_code=404)
        assert fetch_twda_txt(client, 8470, delay=0) is None

    def test_raises_on_500(self):
        client = MagicMock()
        resp = _mock_response(status_code=500)
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "boom", request=MagicMock(), response=MagicMock()
        )
        client.get.return_value = resp
        with pytest.raises(httpx.HTTPStatusError):
            fetch_twda_txt(client, 8470, delay=0)

    def test_requests_expected_raw_url(self):
        client = MagicMock()
        client.get.return_value = _mock_response(status_code=200, text="x")
        fetch_twda_txt(client, 8470, delay=0)
        args, _ = client.get.call_args
        assert args[0].endswith("/decks/8470.txt")
