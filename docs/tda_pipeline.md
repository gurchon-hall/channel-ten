# TDA pipeline (Tournament Deck Archive)

Describes the `smeea/vdb` archive format the TDA scraper depends on, how event and
author metadata is derived from it, and the assumptions worth re-checking if VDB ever
changes its export format.

---

## Source

[`smeea/vdb`](https://github.com/smeea/vdb)'s `frontend/public/tournaments/*.zip` is the
only available source of full tournament decklists (every participant, not just the
winner) — no official VEKN archive of them exists. Each zip is one tournament:

```text
<archive_id>.zip
├── archon.xlsx              # VEKN "Archon" tournament-report spreadsheet
├── <slug>_1.txt              # one deck per participant, TWD deck-block format
├── <slug>_2.txt
└── ...
```

`<archive_id>` (the zip filename stem) is numeric for events that have a VEKN calendar
id (e.g. `10367.zip`) and a short slug for recurring online events that never got one
(e.g. `online1.zip`, `online2.zip`). **Assumption**: a numeric archive id is treated as
a VEKN calendar event id (`https://www.vekn.net/event-calendar/event/<id>`) — this could
not be directly confirmed against `vekn.net` in the environment this pipeline was
written in, but is consistent with every other convention in this codebase (VDB itself
being VEKN-affiliated tooling; The Archon being the official VEKN tournament-reporting
tool). If wrong for some archive, the consequence is only a dead `event_url` link — all
other fields come from `archon.xlsx`, not from fetching that URL. This is intentionally
different from TWD, where the VEKN calendar is cross-checked and can override `name`/
`winner` (see `docs/player_name_extraction.md`) — TDA does not do this cross-check at
all, since `archon.xlsx` is itself the report organizers already submit to VEKN.

## Deck `.txt` format

Identical to a TWD post's deck block — `Deck Name:` / `Author:` / `Description:` /
`Crypt (N cards, min=X max=Y avg=Z.ZZ)` / `Library (N cards)`. This is why
`parser._tda.parse_tda_deck_text` is a thin wrapper around the same
`parser._deck.parse_deck_block` TWD uses — no TDA-specific deck-body parsing exists.

`Author:` is usually a VEKN member number already (e.g. `3070069`) but is sometimes a
non-numeric placeholder for a participant without one (e.g. `100WD1`, seen in a real
archive for a walk-in player). `pipeline_tda.resolve_author` treats a numeric value as
a VEKN number and resolves the canonical player name from it via
`scraper.fetch_player_by_id` (`https://www.vekn.net/player-registry/player/<id>`,
confirmed against a live page — see below); a non-numeric value is resolved via the
by-name lookup (`scraper.fetch_player`) TWD uses for winners. Either way, if the lookup
fails the raw string is kept as the name and the deck is still written (never dropped) —
under a slugified filename (`models.TdaDeck.yaml_filename`) when no VEKN number was
resolvable at all. `process_tda_deck` syncs `deck.created_by` to the resolved name
(the parser only ever sets it to the raw `Author:` line, e.g. `"1003838"`, which isn't
human-readable on its own).

**Caveat**: a numeric `Author:` value being present is not proof that it is *actually*
a registered VEKN member number — see the Archon placeholder-number quirk below, where
small ids like `101` can collide with an unrelated real player's genuinely low id. The
resolved name is only as trustworthy as the source id.

### `fetch_player_by_id` page structure

Confirmed via a real page fetch (`.../player-registry/player/1003838`): the name lives
in the same Joomla `componentheading` convention `fetch_event_name` already reads the
event title from — `<div class="componentheading"><h3>Tom Lindberg (#1003838)</h3></div>`.
The `" (#<id>)"` suffix is stripped to get the bare name. If VEKN ever changes this
template, `fetch_player_by_id` will start returning `None` for every id (logged at
debug level) rather than a wrong name — it does not fall back to a different selector
the way `fetch_event_name` falls back through JSON-LD/`<h1>`, since only this one
structure has been observed.

## `archon.xlsx` sheet layout

`scraper._tda.parse_archon_xlsx` reads three sheets by scanning for label text rather
than fixed row/column indices, so minor row-order drift between Archon versions doesn't
break parsing:

| Sheet | Used for | Lookup strategy |
| - | - | - |
| `Tournament Info` | name, location, date, rounds, players count | first-cell label match (`"Event Name:"`, `"City:"`, `"Event Date (DD-MON-YY):"`, `"Number of Players:"`, `"Number of Rounds (including final):"`) |
| `Standings` | winner name + seat number | row where the `Final Rank` column is `1`; seat number is the `#` column |
| `Methuselahs` | seat number → VEKN member number | header row whose first cell is `"Num."`; data rows below map column 0 (seat/player number) to column 4 (`V:EKN Num.`) |

`Number of Rounds (including final):` counts the final round, e.g. `4` for a
`3R+F` tournament — `_normalize_rounds` subtracts one before formatting as `NR+F`.

The winner's VEKN number is resolved by joining `Standings`' seat number (`#` column)
against `Methuselahs`' seat-to-VEKN-number map — the two sheets do not use the same
column position for "seat number" (`Standings` col 2, `Methuselahs` col 0), so they
cannot be read positionally against each other directly.

**Known Archon quirk**: for recurring online events (no VEKN-registered players), the
Archon tool still requires a numeric "V:EKN Num." per player and fills in small
placeholder numbers (seen: `101`–`125` for one archive) rather than leaving it blank.
These are *not* real VEKN member numbers. This pipeline has no way to distinguish a
placeholder from a real number — it is a data-quality limitation of the source, not
something `parse_archon_xlsx` can detect or correct.

## Output shape

One YAML file per participant deck, at
`tda/YYYY/MM/<event_id>/<author_id>.yaml` — see `models.TdaDeck` for the full field
list. Event-level fields (`name`, `location`, `date_start`, `rounds_format`,
`players_count`, `winner`, `winner_vekn_number`) are duplicated across every deck file
of the same event; this is deliberate (each file is self-contained, matching the
existing TWD convention of one fully-populated YAML per file) rather than a normalized
event/decks split.

## Why TDA has its own models, pipeline and output modules

`Tournament.event_id` is `int | None` and required for `yaml_filename`; `event_url` is
mandatory; and the model represents exactly one deck per event. None of these hold for
TDA (`event_id` can be `"online1"`, `event_url` can be absent, and one event has many
decks). Rather than relax `Tournament`'s contract — which several TWD-specific "what not
to do" rules in `CLAUDE.md` depend on staying exactly as documented — TDA has its own
`TdaDeck` model, `pipeline_tda.py`, and `output/tda_yaml.py`, while reusing everything
that *is* shape-compatible: `Deck`/`CryptCard`/`LibraryCard`/`LibrarySection`,
`parser._deck.parse_deck_block`, the krcg enrichment functions in `validator.py`
(`enrich_crypt_cards`, `fix_card_sections`, `enrich_card_ids`), `scraper.fetch_player`,
and `pipeline.RouteCounters`.
