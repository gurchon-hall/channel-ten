"""Logging configuration for channel_ten.

Call ``setup_logging(verbose)`` once from a CLI entry point; never call
``logging.basicConfig`` directly in library or CLI subcommand modules.
"""

import logging

from rich.logging import RichHandler


def setup_logging(verbose: bool) -> None:
    """Configure root logging with a Rich handler.

    Sets the root level to ERROR; sets ``channel_ten`` to INFO by default
    and DEBUG when *verbose* is True.
    """
    handler = RichHandler(rich_tracebacks=True, show_path=False)
    logging.basicConfig(
        level=logging.ERROR,
        format="%(message)s",
        handlers=[handler],
    )
    level = logging.DEBUG if verbose else logging.INFO
    logging.getLogger("channel_ten").setLevel(level)
