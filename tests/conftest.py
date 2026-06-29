"""Shared test factories and fixtures for channel_ten tests."""

import copy
from datetime import date
from typing import Any

import pytest

from channel_ten.models import (
    CryptCard,
    Deck,
    LibraryCard,
    LibrarySection,
    Tournament,
)

# ---------------------------------------------------------------------------
# Fake krcg crypt data shared between test_validator and any future test that
# needs a deterministic card database without the real krcg package.
# ---------------------------------------------------------------------------

FAKE_CRYPT_KRCG_BASE: dict[str, dict[str, Any] | list[dict[str, Any]]] = {
    "Nathan Turner": {
        "id": 200848,
        "capacity": 4,
        "disciplines": "PRO ani",
        "title": None,
        "clan": "Gangrel",
        "grouping": 6,
        "path": None,
    },
    "Antón de Concepción": {
        "id": 200956,
        "capacity": 8,
        "disciplines": "AUS DOM OBF for",
        "title": "Prince",
        "clan": "Lasombra",
        "grouping": 6,
        "path": None,
    },
    "Anarch Convert": {
        "id": 200077,
        "capacity": 1,
        "disciplines": "",
        "title": None,
        "clan": "Caitiff",
        "grouping": "ANY",
        "path": None,
    },
    "Aaradhya, The Callous Tyrant": {
        "id": 201390,
        "capacity": 10,
        "disciplines": "ANI DOM FOR POT PRE",
        "title": "Cardinal",
        "clan": "Ventrue",
        "grouping": 6,
        "path": "Power and the Inner Voice",
    },
    "Xaviar": {
        "id": 201400,
        "capacity": 11,
        "disciplines": "ANI CEL FOR PRO",
        "title": "Justicar",
        "clan": "Gangrel",
        "grouping": 3,
        "path": None,
    },
    "Xaviar (ADV)": {
        "id": 201401,
        "capacity": 10,
        "disciplines": "aus cel pot ABO ANI FOR PRO",
        "title": "Justicar",
        "clan": "Gangrel",
        "grouping": 3,
        "path": None,
    },
}


@pytest.fixture
def fake_crypt_krcg() -> dict[str, Any]:
    """Return a per-test deep copy of FAKE_CRYPT_KRCG_BASE — safe to mutate."""
    return copy.deepcopy(FAKE_CRYPT_KRCG_BASE)


def make_deck(**kwargs: Any) -> Deck:
    """Return a minimal Deck with Nathan Turner + Blood Doll, overridable via kwargs."""
    defaults: dict[str, Any] = dict(
        crypt=[
            CryptCard(
                count=2,
                name="Nathan Turner",
                capacity=4,
                disciplines="PRO ani",
                clan="Gangrel",
                grouping=6,
            )
        ],
        crypt_count=2,
        crypt_min=4,
        crypt_max=4,
        crypt_avg=4.0,
        library_sections=[
            LibrarySection(
                name="Master",
                count=1,
                cards=[LibraryCard(count=1, name="Blood Doll")],
            )
        ],
        library_count=1,
    )
    defaults.update(kwargs)
    return Deck(**defaults)


def make_tournament(**kwargs: Any) -> Tournament:
    defaults = dict(
        name="Test Event",
        location="Paris, France",
        date_start=date(2023, 3, 25),
        rounds_format="3R+F",
        players_count=15,
        winner="Jane Doe",
        event_url="https://www.vekn.net/event-calendar/event/9999",
        deck=Deck(
            crypt=[
                CryptCard(
                    count=2,
                    name="Nathan Turner",
                    capacity=4,
                    disciplines="PRO ani",
                    clan="Gangrel",
                    grouping=6,
                )
            ],
            crypt_count=2,
            crypt_min=4,
            crypt_max=4,
            crypt_avg=4.0,
            library_sections=[
                LibrarySection(
                    name="Master",
                    count=1,
                    cards=[LibraryCard(count=1, name="Blood Doll")],
                )
            ],
            library_count=1,
        ),
    )
    defaults.update(kwargs)
    return Tournament.model_validate(defaults)
