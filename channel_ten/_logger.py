"""Logging configuration for channel_ten.

Call ``setup_logging(verbose)`` once from a CLI entry point; never call
``logging.basicConfig`` directly in library or CLI subcommand modules.
"""

import logging
import logging.handlers
from pathlib import Path

from rich.logging import RichHandler

_LOG_DIR = Path(".log")
_LOG_FILE = _LOG_DIR / "channel_ten.log"
_MAX_BYTES = 100 * 1024 * 1024  # 100 MB
_BACKUP_COUNT = 5


def setup_logging(verbose: bool) -> None:
    """Configure root logging with a Rich console handler and a rotating file handler.

    The console handler (Rich) is set to ERROR for third-party loggers and
    INFO (or DEBUG when *verbose*) for ``channel_ten``.  The rotating file
    handler always captures DEBUG and above for ``channel_ten``, writing to
    ``.log/channel_ten.log`` with up to 5 × 100 MB backup files.
    """
    _LOG_DIR.mkdir(exist_ok=True)

    console_handler = RichHandler(rich_tracebacks=True, show_path=False)
    logging.basicConfig(
        level=logging.ERROR,
        format="%(message)s",
        handlers=[console_handler],
    )

    file_handler = logging.handlers.RotatingFileHandler(
        _LOG_FILE,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-8s %(name)s  %(message)s")
    )

    channel_ten_logger = logging.getLogger("channel_ten")
    level = logging.DEBUG if verbose else logging.INFO
    channel_ten_logger.setLevel(level)
    channel_ten_logger.addHandler(file_handler)
