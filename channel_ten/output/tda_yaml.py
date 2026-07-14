import io
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

    if (
        "deck" in ordered
        and ordered["deck"]
        and isinstance(ordered["deck"], dict)
        and isinstance(ordered["deck"].get("description"), str)
    ):
        desc = ordered["deck"]["description"]
        if desc and "\n" in desc:
            ordered["deck"]["description"] = LiteralScalarString(desc)

    buf = io.StringIO()
    yaml.dump(ordered, buf)  # pyright: ignore[reportUnknownMemberType]
    return buf.getvalue()


def tda_event_dir(output_dir: Path, entry: TdaDeck) -> Path:
    """Return output_dir/YYYY/MM/<event_id>, the folder holding every deck of one event."""
    d = entry.date_start
    return output_dir / f"{d.year:04d}" / f"{d.month:02d}" / entry.event_id


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
