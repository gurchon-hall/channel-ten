"""
Scraper for https://www.vekn.net/forum/event-reports-and-twd

Submodules:
  _http   — low-level HTTP helpers and shared constants
  _icons  — topic icon detection
  _forum  — forum index traversal and per-thread TWD extraction
  _vekn   — VEKN event calendar and player registry lookups
"""

import time as time  # Ensure time module is available for patching in tests

from channel_ten.scraper._forum import (
    extract_twd_from_thread,
    iter_thread_urls,
    scrape_forum,
)
from channel_ten.scraper._http import (
    DEFAULT_DELAY_SECONDS,
    HEADERS,
    get_soup,
    kunena_div_to_text,
)
from channel_ten.scraper._icons import (
    ICON_DEFAULT,
    ICON_IDEA,
    ICON_MERGED,
    ICON_SOLVED,
    detect_topic_icon,
)
from channel_ten.scraper._twda import (
    TWDA_DECKS_FOLDER,
    TWDA_RAW_BASE,
    fetch_twda_txt,
    is_twda_import,
    list_twda_event_ids,
)
from channel_ten.scraper._vekn import (
    fetch_event_date,
    fetch_event_name,
    fetch_event_winner,
    fetch_player,
)

__all__ = [
    "time",
    # Constants
    "DEFAULT_DELAY_SECONDS",
    "HEADERS",
    "ICON_DEFAULT",
    "ICON_IDEA",
    "ICON_MERGED",
    "ICON_SOLVED",
    "TWDA_DECKS_FOLDER",
    "TWDA_RAW_BASE",
    # HTTP helpers
    "get_soup",
    "kunena_div_to_text",
    # Icons
    "detect_topic_icon",
    # Forum
    "extract_twd_from_thread",
    "iter_thread_urls",
    "scrape_forum",
    # VEKN
    "fetch_event_date",
    "fetch_event_name",
    "fetch_event_winner",
    "fetch_player",
    # GiottoVerducci/TWD archive
    "fetch_twda_txt",
    "is_twda_import",
    "list_twda_event_ids",
]
