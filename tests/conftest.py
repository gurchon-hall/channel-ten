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
    TdaDeck,
    TdaPlayer,
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


def make_tda_deck(**kwargs: Any) -> TdaDeck:
    """Return a minimal TdaDeck, overridable via kwargs.

    ``author``/``author_vekn_number``/``rank``/``gw``/``vp``/``tp`` are shorthand for
    ``deck.player`` fields (name/vekn_number/rank/gw/vp/tp) — passed through to a
    fresh ``deck.player`` unless ``deck`` is given already carrying one.
    """
    player_fields = ("author", "author_vekn_number", "rank", "gw", "vp", "tp")
    player_kwargs = {k: kwargs.pop(k) for k in player_fields if k in kwargs}

    deck = kwargs.pop("deck", None) or make_deck()
    if deck.player is None:
        deck.player = TdaPlayer(
            name=player_kwargs.get("author", "3070069"),
            vekn_number=player_kwargs.get("author_vekn_number", 3070069),
            rank=player_kwargs.get("rank"),
            gw=player_kwargs.get("gw"),
            vp=player_kwargs.get("vp"),
            tp=player_kwargs.get("tp"),
        )

    defaults: dict[str, Any] = dict(
        event_id="10367",
        name="Finnish Nationals 2022",
        location="Espoo - Finland",
        date_start=date(2022, 11, 5),
        rounds_format="3R+F",
        players_count=45,
        winner="Teemu Sainomaa",
        winner_vekn_number=3070069,
        deck=deck,
    )
    defaults.update(kwargs)
    return TdaDeck.model_validate(defaults)
