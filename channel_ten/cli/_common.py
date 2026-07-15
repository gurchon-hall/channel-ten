"""Shared helpers for all CLI subcommands."""

import argparse
import logging
import os
from typing import Any, Protocol

import httpx

from channel_ten.scraper import DEFAULT_DELAY_SECONDS, login

logger = logging.getLogger(__name__)


class SubParsersAction(Protocol):
    """Public-facing protocol for argparse._SubParsersAction."""

    def add_parser(self, name: str, **kwargs: Any) -> argparse.ArgumentParser: ...


def vekn_login_from_env(client: httpx.Client, delay: float = DEFAULT_DELAY_SECONDS) -> None:
    """Log *client* into vekn.net using ``$VEKN_USERNAME``/``$VEKN_PASSWORD``, if set.

    The player registry (:func:`~channel_ten.scraper.fetch_player`,
    :func:`~channel_ten.scraper.fetch_player_by_id`) is login-gated — without an
    authenticated session every registry lookup silently returns ``None`` and the
    caller falls back to the raw, unresolved name or id. Never raises: logs a
    warning and leaves *client* unauthenticated if the env vars are unset or the
    login attempt fails.
    """
    username = os.environ.get("VEKN_USERNAME")
    password = os.environ.get("VEKN_PASSWORD")
    if not username or not password:
        logger.warning(
            "VEKN_USERNAME/VEKN_PASSWORD not set — player registry lookups "
            "will fail for every deck (falling back to raw names/ids)."
        )
        return
    if not login(client, username, password, delay=delay):
        logger.warning(
            "VEKN login failed — player registry lookups will fail for every deck "
            "(falling back to raw names/ids)."
        )
