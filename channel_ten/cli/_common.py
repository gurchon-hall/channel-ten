"""Shared helpers for all CLI subcommands."""

import argparse
from typing import Any, Protocol


class SubParsersAction(Protocol):
    """Public-facing protocol for argparse._SubParsersAction."""

    def add_parser(self, name: str, **kwargs: Any) -> argparse.ArgumentParser: ...
