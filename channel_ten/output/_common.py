from pathlib import Path

from channel_ten.models import Tournament


def date_subdir(tournament: Tournament) -> Path:
    """Return a Path(YYYY/MM) derived from tournament.date_start."""

    if isinstance(tournament.date_start, str):
        # Model parses str to date object on creation
        # str type is only for first assignation purposes
        raise TypeError("tournament.date_start must be a datetime.date object.")

    d = tournament.date_start
    return Path(f"{d.year:04d}/{d.month:02d}")
