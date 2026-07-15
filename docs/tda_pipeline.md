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
fails, `resolve_author`'s `archon_name` argument — the participant's `Name` from their
own Standings row, which `cli/tda_scrape.py` passes in from the same Target Rank join
described below — is used instead of the raw `Author:` value, since a bare VEKN number
is not a name; this needs no extra network call, since the name is already sitting in
the same `archon.xlsx` the Standings join already reads. Only when no Standings row
matched either (`archon_name` is `None`) does the raw value get kept as-is. Either way,
the deck is still written (never dropped) — under a slugified filename
(`models.TdaDeck.yaml_filename`) when no VEKN number was resolvable at all. The
resolved `(name, vekn_number)` becomes `deck.player.name` / `deck.player.vekn_number`
(see below); `process_tda_deck` clears `deck.created_by` (the parser only ever sets it
to the raw `Author:` line, e.g. `"1003838"`, superseded by the richer `deck.player`).

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
| `Standings` | every participant's final rank, GW/VP/TP; the winner is the `Final Rank == 1` row | header row `Final Rank, Target Rank, #, Name, Prelim GWs, Prelim VPs, Final VPs, TPs` |
| `Methuselahs` | seat number → VEKN member number | header row whose first cell is `"Num."`; data rows below map column 0 (seat/player number) to column 4 (`V:EKN Num.`) |

`Number of Rounds (including final):` counts the final round, e.g. `4` for a
`3R+F` tournament — `_normalize_rounds` subtracts one before formatting as `NR+F`.

`scraper._tda._parse_standings` reads every `Standings` row (not just the winner) into
a `TdaStandingRow`, joining in `vekn_number` via `Methuselahs`' seat-to-VEKN-number map —
the two sheets do not use the same column position for "seat number" (`Standings` col 2,
`Methuselahs` col 0), so they cannot be read positionally against each other directly.
The winner is simply the row where `final_rank == 1`.

`vp` sums `Prelim VPs` + `Final VPs` (0 when a player didn't reach the final, i.e. that
cell is blank) — this matches the total each deck's own `Description:` line already
encodes, e.g. `2GW8.5+3` for a player with 2 GW, 8.5 prelim VP and 3 final VP (confirmed
against a live archive, smeea/vdb's `10367.zip`). `gw` is `Prelim GWs` — no separate
final-round GW is tracked in this sheet.

### Joining a deck file to its Standings row

Each deck `.txt` filename is `<slug>_<N>.txt`. `N` looks like it should be the seat
number or `Final Rank`, but empirically (checked against `10367.zip`) it is neither:

- **Not the seat number** — a deck's `Author:` VEKN number resolves (via Methuselahs)
  to a seat that usually differs from `N`.
- **Not `Final Rank`** — VTES only ranks the final's winner outright; every other
  finalist ties at the same `Final Rank` (e.g. four players all recorded as rank `2`),
  so `Final Rank` cannot uniquely identify one deck file.
- **It is `Target Rank`** — Standings' pre-final seeding-plus-tiebreak column, which is
  unique per participant. `scraper._tda.target_rank_from_deck_filename` extracts `N`
  from the filename; `standing_for_target_rank` looks up the matching row. If a filename
  doesn't match the expected pattern (e.g. some online-event archive), the lookup is
  skipped and that deck's `rank`/`gw`/`vp`/`tp` are left `None` — the deck is still
  written (never dropped).

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

The raw `archon.xlsx` itself is also saved, once per event, to
`tda/YYYY/MM/<event_id>/archon.xlsx` (`output.tda_yaml.write_archon_xlsx`) — for
traceability against smeea/vdb, which could change format or remove an archive.

### `deck.player`

A deck's participant identity and this event's placement data live under
`deck.player` (`models.TdaPlayer`), not as top-level `TdaDeck` fields:

```yaml
deck:
  player:
    name: Teemu Sainomaa       # resolve_author's canonical name
    vekn_number: 3070069       # resolve_author's VEKN number
    rank: 1                    # Standings' Final Rank, via the Target Rank join above
    gw: 2                      # Prelim GWs
    vp: 11.5                   # Prelim VPs + Final VPs
    tp: 156                    # TPs
  name: ...
  crypt: ...
```

`rank`/`gw`/`vp`/`tp` are `None` when the Standings join didn't find a match (see
above). `deck.player` is a field on the shared `Deck` model (reused by TWD's
`Tournament.deck` too) but is only ever populated for TDA — TWD leaves it unset, so it
never appears in TWD's YAML output. `TdaDeck.yaml_filename` uses
`deck.player.vekn_number` when resolved, else a slug of `deck.player.name`.
`TdaDeck` no longer has top-level `author`/`author_vekn_number` fields — this is a
breaking schema change from the original TDA output shape.

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
and `pipeline.RouteCounters`. `TdaPlayer` (`deck.player`) is the one TDA-only field
added to the shared `Deck` model itself — optional and unset for TWD, so it never
appears in TWD's YAML output.
