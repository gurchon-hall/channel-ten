from pathlib import Path
from typing import Any

from pydantic import BaseModel

from channel_ten.models import Tournament

JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


def date_subdir(tournament: Tournament) -> Path:
    """Return a Path(YYYY/MM) derived from tournament.date_start."""

    if isinstance(tournament.date_start, str):
        # Model parses str to date object on creation
        # str type is only for first assignation purposes
        raise TypeError("tournament.date_start must be a datetime.date object.")

    d = tournament.date_start
    return Path(f"{d.year:04d}/{d.month:02d}")


def to_serializable(obj: BaseModel) -> dict[str, JsonValue]:
    """Convert a Pydantic model to a plain dict, preserving Python native types.

    Uses model_dump() (not JSON round-trip) so that date objects remain as
    datetime.date instances — ruamel.yaml then renders them as bare YAML dates
    (2026-03-15) rather than quoted strings ('2026-03-15').
    """

    def _filter_none(value: JsonValue) -> JsonValue:
        if isinstance(value, dict):
            return {k: _filter_none(v) for k, v in value.items() if v is not None}
        if isinstance(value, list):
            return [_filter_none(item) for item in value]
        return value

    result = _filter_none(obj.model_dump())
    assert isinstance(result, dict)
    return result


def reorder_dict(data: dict[str, Any], field_order: list[str]) -> dict[str, Any]:
    """Return a new dict with keys ordered as per *field_order*, extras kept at the end."""
    ordered: dict[str, Any] = {k: data[k] for k in field_order if k in data}
    for k in data:
        if k not in ordered:
            ordered[k] = data[k]
    return ordered
