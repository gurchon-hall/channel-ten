import io
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString

from channel_ten.models import Tournament
from channel_ten.output._common import JsonValue, date_subdir, reorder_dict, to_serializable

_TOURNAMENT_FIELD_ORDER = list(Tournament.model_fields.keys())


def reorder_tournament_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Return a new dict with keys ordered as per the Tournament model definition."""
    return reorder_dict(data, _TOURNAMENT_FIELD_ORDER)


def _prepare_yaml_dict(tournament: Tournament) -> dict[str, JsonValue]:
    """
    Build an ordered dict suitable for YAML output.
    Handles multiline description as a literal block scalar (|).
    """
    d = to_serializable(tournament)

    if (
        "deck" in d
        and d["deck"]
        and isinstance(d["deck"], dict)
        and "description" in d["deck"]
        and isinstance(d["deck"]["description"], str)
    ):
        desc = d["deck"]["description"]
        if desc and "\n" in desc:
            d["deck"]["description"] = LiteralScalarString(desc)

    return d


def tournament_to_yaml_str(tournament: Tournament) -> str:
    """Serialize a Tournament to a YAML string."""
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.allow_unicode = True

    buf = io.StringIO()
    yaml.dump(  # pyright: ignore[reportUnknownMemberType]
        _prepare_yaml_dict(tournament), buf
    )
    return buf.getvalue()


def _find_existing_yaml(output_dir: Path, filename: str) -> Path | None:
    """Search for *filename* anywhere under *output_dir* and return the first match."""
    for match in output_dir.rglob(filename):
        return match
    return None


def write_tournament_yaml(
    tournament: Tournament,
    output_dir: Path,
    overwrite: bool = False,
) -> Path:
    """
    Write a Tournament to {output_dir}/YYYY/MM/{event_id}.yaml

    Before writing, the whole output_dir tree (including error sub-folders) is
    searched for an existing file with the same event_id:

    * Same content  → skip silently (raise FileExistsError).
    * Different content → unlink the old file (wherever it lives) and write the
      new one at the canonical YYYY/MM location.
    * No prior file  → write normally.

    Raises:
        FileExistsError: if an identical file already exists and overwrite=False
    """
    new_content = tournament_to_yaml_str(tournament)

    existing = _find_existing_yaml(output_dir, tournament.yaml_filename)
    if existing is not None:
        if existing.read_text(encoding="utf-8") == new_content and not overwrite:
            raise FileExistsError(
                f"Output file already exists with identical content: {existing}. "
                "Use --overwrite to replace."
            )
        existing.unlink()

    dest = output_dir / date_subdir(tournament)
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / tournament.yaml_filename
    path.write_text(new_content, encoding="utf-8")
    return path


find_existing_yaml = _find_existing_yaml
