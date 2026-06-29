# Plan: Add card IDs

## Context

First suggested by [@Zavierazo](https://github.com/Zavierazo) in
[#14](https://github.com/gurchon-hall/channel-ten/pull/14). This is implemented separately
from the pull request because project bumped from v0.5.0 to v0.8.0 and upgrading to the new
version is non-trivial. The plan is to add card IDs to the deck output, which will allow for
more stable references to cards even if their names change in the future.

VTES cards each have a unique numeric ID in the krcg database. Storing these IDs in the
YAML output enables stable card references that survive name changes (e.g. "Mind Rape" →
"Puppet Master"). Once attributed from krcg, an ID must never be cleared (a None returned
by a later offline run should not overwrite an already-known ID). Missing an ID after
enrichment is a data-quality error (`missing_card_id`).

---

## Files to change

### 1. `channel_ten/models.py`

Introduce a `Card` base class carrying the four fields shared by every card kind:

```python
class Card(BaseModel):
    count: int
    name: str
    id: int | None = None
    comment: str | None = None

class CryptCard(Card):
    capacity: int
    disciplines: str
    title: str | None = None
    clan: str
    grouping: int | str
    path: str | None = None

class LibraryCard(Card):
    pass
```

Pydantic v2 inherits fields in parent-first order, so the YAML field order for CryptCard
becomes `count, name, id, comment, capacity, disciplines, title, clan, grouping, path`.
LibraryCard becomes `count, name, id, comment`. Field order in YAML is cosmetic only;
parsers are order-independent.

`_filter_none` in `output/yaml.py` already strips `None` values, so `id` only appears in
YAML when set. TXT output never references `id`, so no change there.

---

### 2. `channel_ten/_krcg_helper.py`

**a) Set `id` in `get_all_vamp_variants()`** — add `id=int(candidate.id)` to the
`CryptCard(...)` constructor inside the loop. Each returned variant carries the correct
krcg id for its specific grouping.

No `OLD_TO_NEW_NAME` here — see §4 below.

---

### 3. `channel_ten/validator.py`

**a) Update module docstring** — add `missing_card_id` to the error-type catalogue.

**b) Add a comment on `_ENRICH_FIELDS`** explaining why `id` is excluded:

```python
# id is excluded from _ENRICH_FIELDS intentionally: fields listed here are
# always overwritten from krcg on every enrichment pass (enabling safe
# re-enrichment as krcg data evolves). id follows a stricter rule — once
# attributed it must never be cleared — so it is handled separately with
# an explicit "set only if None" guard.
_ENRICH_FIELDS: frozenset[str] = frozenset({...})
```

**c) Set `id` in `enrich_crypt_cards()`** — after the per-field loop, conditionally copy
`best.id` (now populated by `get_all_vamp_variants()`):

```python
if card.id is None and best.id is not None:
    card.id = best.id
```

**d) Add `enrich_card_ids(deck: Deck) -> list[str]`** — sets ids for library cards (and
any crypt card not yet attributed by `enrich_crypt_cards()`). Guards on `is_krcg_loaded()`.
For each card whose `id is None`, calls `krcg_card_search(card.name)`; if found, sets
`card.id = int(krcg_card.id)`. Returns list of change descriptions (empty when nothing
changed or krcg unavailable).

**e) Add `missing_card_id_errors(deck: Deck) -> list[str]`** — returns
`["missing_card_id"]` if any crypt or library card has `id is None` after enrichment.
Returns `[]` when krcg is unavailable (same guard pattern as `unresolved_card_errors()`).

```python
def missing_card_id_errors(deck: Deck) -> list[str]:
    if not is_krcg_loaded():
        return []
    all_cards: list[CryptCard | LibraryCard] = list(deck.crypt) + _iter_library_cards(deck)
    if any(c.id is None for c in all_cards):
        return ["missing_card_id"]
    return []
```

---

### 4. One-time migration script (separate from the regular pipeline)

`OLD_TO_NEW_NAME` and any logic that applies it must live in a **standalone migration
script** (e.g. `scripts/migrate_card_names.py`), not in `_krcg_helper.py` or the regular
validator pipeline. The script:

- Reads all YAML files in the eternal-vigilance storage folder.
- Applies `OLD_TO_NEW_NAME` renames (e.g. `"Mind Rape" → "Puppet Master"`) to any card
  whose name matches an old key, then re-enriches to set correct ids.
- Writes the updated YAML back in-place.
- Is run **once** after this feature is deployed; afterwards old names no longer appear in
  storage and the script is no longer needed.

The constant itself (`OLD_TO_NEW_NAME`) lives in the migration script and is not imported
by library code.

---

### 5. Tests

**`tests/conftest.py`**

- Add an `id` integer to each entry in `FAKE_CRYPT_KRCG_BASE` so mock krcg objects expose
  `.id`. Existing factories (`make_deck`, `make_tournament`) need no change — `CryptCard`
  and `LibraryCard` ids default to `None`.

**`tests/test_validator.py`**

- `enrich_card_ids()`: sets id on library cards when krcg returns a card with `.id`.
- `enrich_card_ids()`: skips cards whose `id` is already set (immutability guard).
- `enrich_card_ids()`: returns `[]` when krcg unavailable.
- `missing_card_id_errors()`: returns `[]` when all ids are set.
- `missing_card_id_errors()`: returns `["missing_card_id"]` when any id is `None`.
- `missing_card_id_errors()`: returns `[]` when krcg unavailable.
- `enrich_crypt_cards()`: verify `card.id` is set from the best version's id after enrichment.

---

## Pipeline call order (regular, not migration)

```text
enrich_crypt_cards(deck)       # fills capacity, disciplines, … + sets crypt card ids
enrich_card_ids(deck)          # sets library card ids (+ crypt fallback for unmatched cards)
missing_card_id_errors(deck)   # returns ["missing_card_id"] if any id still None
```

`canonicalize_card_names()` is not listed here — it is a migration-only step called by
the migration script, not by the regular ingestion pipeline.

---

## Verification

1. `pytest -m "not integration"` — full unit suite green.
2. Manually verify a YAML output includes `id:` on each card after enrichment.
3. Verify that a deck with an unrecognised card name surfaces `missing_card_id`.
4. Verify that re-running enrichment on a YAML that already has ids leaves them unchanged.
