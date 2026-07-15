"""Low-level HTTP helpers and shared constants."""

import logging
import re
import time

import httpx
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FORUM_BASE = "https://www.vekn.net"
FORUM_INDEX = "https://www.vekn.net/forum/event-reports-and-twd"
VEKN_PLAYERS_URL = "https://www.vekn.net/event-calendar/players"
VEKN_PLAYER_REGISTRY_URL = "https://www.vekn.net/player-registry/player"

# Kunena paginates with ?limitstart=N
TOPICS_PER_PAGE = 20
POSTS_PER_THREAD_PAGE = 6

DEFAULT_DELAY_SECONDS = 1.5

HEADERS = {
    "User-Agent": (
        "channel-ten/0.2 "
        "(tournament data archiver; contact via github.com/gurchon-hall/channel-ten)"
    )
}

# Matches thread URLs like /forum/event-reports-and-twd/12345-some-title
THREAD_HREF_RE = re.compile(r"^/forum/event-reports-and-twd/(\d+)-[^\"'?#]+$")

# Thread slugs that are meta/admin posts, not TWD reports — skip them
SKIP_SLUGS = {
    "2119-how-to-report-a-twd",
    "79623-contributing-to-the-twd",
    "63835-howto-use-the-archon-correctly",
}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def get_soup(client: httpx.Client, url: str, delay: float = DEFAULT_DELAY_SECONDS) -> BeautifulSoup:
    """Fetch a URL and return parsed HTML. Raises on HTTP errors."""
    logger.debug("GET %s", url)
    response = client.get(url, follow_redirects=True)
    response.raise_for_status()
    time.sleep(delay)
    # Parse the raw bytes (not response.text) so BeautifulSoup/UnicodeDammit can
    # detect the document's real charset from the <meta charset>/BOM. Passing the
    # pre-decoded response.text relies on httpx's charset guess, which mangles
    # UTF-8 pages served without a charset header into mojibake (e.g. "GÃ¤deke").
    return BeautifulSoup(response.content, "lxml")


def kunena_div_to_text(div: Tag) -> str:
    """
    Convert a Kunena <div class="kmsg"> to plain text.

    Kunena uses <br> for line breaks and <hr> as section separators.
    BeautifulSoup's get_text() ignores both by default — we handle them
    explicitly before extraction.
    """
    # Replace <hr> with an empty line marker (section separator in library blocks)
    for hr in div.find_all("hr"):
        hr.replace_with("\n")

    # Replace <br> with newline markers
    for br in div.find_all("br"):
        br.replace_with("\n")

    # Normalise URLs: some posts omit the scheme, e.g. "www.vekn.net/event-calendar/..."
    text = div.get_text()
    text = re.sub(r"(?<![:/])www\.vekn\.net", "https://www.vekn.net", text)

    return text
