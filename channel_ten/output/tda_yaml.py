import io
from datetime import date
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString

from channel_ten.models import TdaDeck
from channel_ten.output._common import reorder_dict, to_serializable

_TDA_FIELD_ORDER = list(TdaDeck.model_fields.keys())


def tda_deck_to_yaml_str(entry: TdaDeck) -> str:
    """Serialize a TdaDeck to a YAML string."""
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.allow_unicode = True

    ordered = reorder_dict(to_serializable(entry), _TDA_FIELD_ORDER)

    deck = ordered.get("deck")
    if isinstance(deck, dict):
        desc = deck.get("description")
        if isinstance(desc, str) and "\n" in desc:
            deck["description"] = LiteralScalarString(desc)

    buf = io.StringIO()
    yaml.dump(ordered, buf)  # pyright: ignore[reportUnknownMemberType]
    return buf.getvalue()


def _event_dir(output_dir: Path, date_start: date, event_id: str) -> Path:
    return output_dir / f"{date_start.year:04d}" / f"{date_start.month:02d}" / event_id


def tda_event_dir(output_dir: Path, entry: TdaDeck) -> Path:
    """Return output_dir/YYYY/MM/<event_id>, the folder holding every deck of one event."""
    return _event_dir(output_dir, entry.date_start, entry.event_id)


def write_archon_xlsx(
    xlsx_bytes: bytes,
    output_dir: Path,
    date_start: date,
    event_id: str,
    overwrite: bool = False,
) -> Path:
    """Write the archive's raw archon.xlsx alongside its per-participant deck YAML
    files, at output_dir/YYYY/MM/<event_id>/archon.xlsx, for traceability against
    smeea/vdb (the source could change or disappear).

    Same identical-content-skip semantics as :func:`write_tda_deck_yaml`.
    """
    dest_dir = _event_dir(output_dir, date_start, event_id)
    path = dest_dir / "archon.xlsx"

    if path.exists() and not overwrite and path.read_bytes() == xlsx_bytes:
        return path

    dest_dir.mkdir(parents=True, exist_ok=True)
    path.write_bytes(xlsx_bytes)
    return path


def write_tda_deck_yaml(
    entry: TdaDeck,
    output_dir: Path,
    overwrite: bool = False,
) -> Path:
    """
    Write a TdaDeck to {output_dir}/YYYY/MM/{event_id}/{author_id}.yaml

    Same identical-content-skip / overwrite semantics as
    :func:`channel_ten.output.yaml.write_tournament_yaml`, but the existing-file
    search is scoped to the event's own folder — unlike a TWD ``event_id``,
    which is globally unique, a TDA ``author_id`` is only unique within one event.

    Raises:
        FileExistsError: if an identical file already exists and overwrite=False
    """
    new_content = tda_deck_to_yaml_str(entry)
    dest_dir = tda_event_dir(output_dir, entry)
    path = dest_dir / entry.yaml_filename

    if path.exists():
        if path.read_text(encoding="utf-8") == new_content and not overwrite:
            raise FileExistsError(
                f"Output file already exists with identical content: {path}. "
                "Use --overwrite to replace."
            )

    dest_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(new_content, encoding="utf-8")
    return path
