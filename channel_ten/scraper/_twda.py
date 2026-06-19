"""Read-only source for the GiottoVerducci/TWD archive.

The VEKN forum is not the complete record of tournament winning decks: some TWDs
only ever made it into the canonical community archive at
[GiottoVerducci/TWD](https://github.com/GiottoVerducci/TWD), which stores curated
decks as ``decks/<event_id>.txt`` on the ``master`` branch.

This module lists those deck ids and fetches their raw text so the ``import``
subcommand can backfill events that are missing from the base. It only *reads*
the archive — publishing back to it lives in :mod:`channel_ten.publisher`.

GitHub access:
  - Listing uses the git trees API (one request). Unauthenticated requests are
    limited to 60/hour per IP; pass a token to raise the limit.
  - Per-file fetches use raw.githubusercontent.com, which is not subject to the
    REST API rate limit, so importing many decks only costs the single tree call.
"""

import logging
import re
import time

import httpx

from channel_ten.scraper._http import DEFAULT_DELAY_SECONDS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TWDA_OWNER = "GiottoVerducci"
TWDA_REPO = "TWD"
TWDA_BRANCH = "master"
TWDA_DECKS_FOLDER = "decks"

_GITHUB_API = "https://api.github.com"
TWDA_RAW_BASE = (
    f"https://raw.githubusercontent.com/{TWDA_OWNER}/{TWDA_REPO}/{TWDA_BRANCH}/{TWDA_DECKS_FOLDER}"
)

# Matches deck blob paths like "decks/8470.txt" and captures the event id.
_DECK_PATH_RE = re.compile(rf"^{TWDA_DECKS_FOLDER}/(\d+)\.txt$")


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _twda_headers(token: str | None = None) -> dict[str, str]:
    """Build GitHub API headers. Authentication is optional but raises the limit."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


twda_headers = _twda_headers


def list_twda_event_ids(
    client: httpx.Client,
    token: str | None = None,
    delay: float = DEFAULT_DELAY_SECONDS,
) -> list[int]:
    """Return the sorted event ids of every ``decks/<id>.txt`` file in the archive.

    Uses the recursive git trees API in a single request.

    Raises:
        RuntimeError: when the request is rejected because the API rate limit has
            been exhausted (advises setting a token).
        httpx.HTTPStatusError: for other unexpected HTTP errors.
    """
    url = f"{_GITHUB_API}/repos/{TWDA_OWNER}/{TWDA_REPO}/git/trees/{TWDA_BRANCH}"
    logger.debug("GET %s (recursive)", url)
    resp = client.get(url, headers=_twda_headers(token), params={"recursive": "1"})

    if resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0":
        raise RuntimeError(
            "GitHub API rate limit exceeded while listing GiottoVerducci/TWD. "
            "Set the GITHUB_TOKEN environment variable (or pass --github-token) "
            "to raise the limit."
        )
    resp.raise_for_status()
    time.sleep(delay)

    data = resp.json()
    if data.get("truncated"):
        logger.warning(
            "GiottoVerducci/TWD git tree was truncated by the API; "
            "some deck files may be missing from the listing."
        )

    event_ids: list[int] = []
    for entry in data.get("tree", []):
        if entry.get("type") != "blob":
            continue
        match = _DECK_PATH_RE.match(entry.get("path", ""))
        if match:
            event_ids.append(int(match.group(1)))

    return sorted(event_ids)


def fetch_twda_txt(
    client: httpx.Client,
    event_id: int,
    delay: float = DEFAULT_DELAY_SECONDS,
) -> str | None:
    """Fetch the raw TWD text for *event_id*, or ``None`` if it does not exist.

    Returns the file content on HTTP 200, ``None`` on 404, and raises on other
    HTTP errors.
    """
    url = f"{TWDA_RAW_BASE}/{event_id}.txt"
    logger.debug("GET %s", url)
    resp = client.get(url, follow_redirects=True)
    if resp.status_code == 404:
        logger.debug("No TWDA deck file for event %s", event_id)
        time.sleep(delay)
        return None
    resp.raise_for_status()
    time.sleep(delay)
    return resp.text
