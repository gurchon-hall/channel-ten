# Plan: CLAUDE.md compliance + TypedDict → Pydantic migration

## Context

Two goals, addressed together:

1. **Style violations** found by auditing the codebase against CLAUDE.md conventions.
2. **TypedDict debt** — CLAUDE.md explicitly calls these out as "debt to eliminate". User has asked for a full migration to Pydantic BaseModels.

---

## Part 1 — Style fixes (no structural changes)

### 1a. Python 2 exception syntax (SyntaxErrors — fix first)

These are genuine SyntaxErrors in Python 3 and prevent the module from loading.

| File | Line | Fix |
| ---- | ---- | --- |
| `channel_ten/_krcg_helper.py` | 237 | `except TypeError, ValueError:` → `except (TypeError, ValueError):` |
| `channel_ten/_krcg_helper.py` | 254 | `except KeyError, AttributeError, TypeError, ValueError:` → `except (KeyError, AttributeError, TypeError, ValueError):` |
| `channel_ten/parser/_helpers.py` | 118 | `except UnicodeEncodeError, UnicodeDecodeError:` → `except (UnicodeEncodeError, UnicodeDecodeError):` |

### 1b. Logger naming: `_logger` → `logger`

| File | Change |
| ---- | ------ |
| `channel_ten/_krcg_helper.py:7` | `_logger = logging.getLogger(...)` → `logger = ...` |
| `channel_ten/_krcg_helper.py:66,91,117` | `_logger.debug(...)` → `logger.debug(...)` |
| `channel_ten/validator.py:54` | `_logger = logging.getLogger(...)` → `logger = ...` (check for any call sites in the file) |

### 1c. Imports inside function bodies

Move to module top in every case below. No circular-import risk verified for any of them.

| File | Line | Import |
| ---- | ---- | ------ |
| `channel_ten/cli/validate.py` | 148 | `from ruamel.yaml import YAML` |
| `channel_ten/cli/validate.py` | 178 | `from channel_ten.cli.scrape import serialize_tournament` |
| `channel_ten/validator.py` | 327 | `from channel_ten.models import Tournament` (not caught by original audit) |
| `tests/test_cli_scrape.py` | 47 | `import contextlib` |

### 1d. Create `channel_ten/_logger.py` (logging config)

CLAUDE.md says logging configuration lives in `channel_ten/_logger.py`. The file does not exist; `setup_logging()` currently lives in `channel_ten/cli/_common.py` and calls `logging.basicConfig()` there.

**Action:**

- Create `channel_ten/_logger.py` containing only `setup_logging(verbose: bool) -> None`
- In `channel_ten/cli/_common.py`: remove `setup_logging`; add import from `_logger`
- Update callers that import `setup_logging` from `_common`:
  - `channel_ten/cli/publish.py`
  - `channel_ten/cli/scrape.py`
  - `channel_ten/cli/parse.py`
  - `channel_ten/cli/reimport.py`
  - `tests/test_cli_common.py` (import path update only)

---

## Part 2 — TypedDict → Pydantic migration

### Strategy

The five TypedDicts (`Library_Card_Dict`, `Library_Section_Dict`, `Crypt_Card_Dict`, `Deck_Dict`, `Tournament_Dict`) serve two distinct roles:

1. **Structured return types** for freshly-built data (`_krcg_helper.py`) — replace with Pydantic models directly.
2. **Raw YAML dict annotations** for potentially-invalid data (`validator.py`, `cli/validate.py`) — `error_types()` *must* accept arbitrary raw data so it can detect missing/invalid fields before Pydantic validation. Replace with `dict[str, Any]`.

Enrichment functions (`enrich_crypt_cards`, `fix_card_sections`, `canonicalize_card_names`, `unresolved_card_errors`) operate on structured data; they accept `Deck` after migration.

### 2a. `models.py`

- Remove all 5 TypedDict classes.
- Remove `TypedDict`, `Required` from the `typing` import (keep `Any` if still needed).
- Add a default to `Tournament.deck`: `deck: Deck | None = None` (currently no default, which forces callers to provide it even when loading partial YAML data).

### 2b. `channel_ten/_krcg_helper.py`

- `get_all_vamp_variants()` return type: `list[Crypt_Card_Dict]` → `list[CryptCard]`.
- Inside the function: replace the `entry: Crypt_Card_Dict = {…}` dict literal with `CryptCard(capacity=…, disciplines=…, …)`.
- Update import: remove `Crypt_Card_Dict`, add `CryptCard`.

### 2c. `channel_ten/validator.py`

Remove all TypedDict imports. Change each function signature:

| Old signature | New signature |
| ------------- | ------------- |
| `_pick_best_crypt_version(versions: list[Crypt_Card_Dict], …)` | `(versions: list[CryptCard], …)` |
| `enrich_crypt_cards(deck: Deck_Dict)` | `(deck: Deck)` |
| `fix_card_sections(deck: Deck_Dict)` | `(deck: Deck)` |
| `canonicalize_card_names(deck: Deck_Dict)` | `(deck: Deck)` |
| `unresolved_card_errors(deck: Deck_Dict)` | `(deck: Deck)` |
| `_iter_crypt_cards(deck: Deck_Dict)` | `(deck: Deck) → list[CryptCard]` |
| `_iter_library_cards(deck: Deck_Dict)` | `(deck: Deck) → list[LibraryCard]` |
| `error_types(data: Tournament_Dict, …)` | `(data: dict[str, Any], …)` ← stays a plain dict |

**Implementation changes:**

- `.get("crypt")` → `.crypt`; `.get("library_sections")` → `.library_sections`; etc. throughout enrichment functions.
- `_pick_best_crypt_version`: access `.grouping` instead of `.get("grouping")`.
- `enrich_crypt_cards`: replace the `cast(dict[str, Any], card)` + `card_plain[field] = value` mutation pattern with `setattr(card, field, value)`.
- `fix_card_sections`: replace `cast(Library_Section_Dict, {…})` with `LibrarySection(name=…, count=…, cards=…)`. Assign `deck.library_sections = new_sections` and `deck.library_count = …`.
- `canonicalize_card_names`: use `card.name` instead of `card.get("name")`.
- `error_types`: keep using `.get()` dict access (parameter is now `dict[str, Any]`).

### 2d. `channel_ten/cli/scrape.py`

- `_to_serializable()` / `serialize_tournament()`: return type `Tournament_Dict` → `dict[str, Any]`. Implementation becomes `tournament.model_dump(exclude_none=True)` (replaces the recursive `_filter_none`; Pydantic v2 `exclude_none=True` recurses). Remove the `# type: ignore[redundant-cast]` comment.
- `_enrich_with_krcg()`: remove the `_to_serializable` → `Deck_Dict` cast round-trip. Access `tournament.deck` directly, call enrichment functions on it (Pydantic model), return the same `tournament` (mutations are in-place).
- `_validate_content()`: call `error_types(tournament.model_dump(exclude_none=True), …)` to convert to dict before passing to `error_types`.
- Remove `Deck_Dict`, `Tournament_Dict` imports.

### 2e. `channel_ten/cli/validate.py`

- Remove `Deck_Dict`, `Tournament_Dict` imports. Add `Deck`, `Tournament` where needed.
- `run()` YAML loading: `data: dict[str, Any] = cast(dict[str, Any], raw)` — no TypedDict needed, `type: ignore` goes away.
- Winner/vekn mutation: `data["winner"] = …` works cleanly on `dict[str, Any]` — no `type: ignore`.
- Deck enrichment block: replace `deck: Deck_Dict = data.get("deck") or {}` with:

  ```python
  deck = Deck.model_validate(data.get("deck") or {})
  ```

  Call enrichment functions with this `Deck` model. Afterwards: `data["deck"] = deck.model_dump(exclude_none=True)`.
- `fresh_data` from forum rescrape: type is now `dict[str, Any]` (return of `serialize_tournament`); `fresh_data["vekn_number"] = …` works without `type: ignore`.
- `_check_and_update_winner(data: Tournament_Dict, …)` → `(data: dict[str, Any], …)`.
- `_reorder_tournament_dict(data: Tournament_Dict)` → `(data: dict[str, Any])`.

### 2f. Tests

`tests/test_validator.py` and `tests/test_cli_validate.py` use TypedDicts extensively as fixture builders.

- Functions currently building `Tournament_Dict(…)` → plain dicts: `{"name": …, "deck": …, …}`.
  `error_types()` accepts `dict[str, Any]` so test dicts work directly.
- Functions building `Deck_Dict(…)` for enrichment tests → `Deck(crypt=[…], library_sections=[…])`.
- `Crypt_Card_Dict(…)` → `CryptCard(…)` (note: must now supply required fields `count`, `name`, `capacity`, `disciplines`, `clan`, `grouping`).
- `Library_Card_Dict(…)` → `LibraryCard(…)`.
- `Library_Section_Dict(…)` → `LibrarySection(…)`.
- Helper functions like `_tournament(**overrides)` / `_deck(**overrides)` that check `if k in TypedDict.__annotations__` → adapt to use `Tournament.model_fields` / `Deck.model_fields` for filtering, or just drop the guard (simpler, unknown keys are ignored by Pydantic).

---

## Verification

```bash
# Type check (strict)
mypy channel_ten

# Full test suite
pytest

# Fast unit tests only
pytest -m "not integration"
```

All `# type: ignore` suppressions in `cli/validate.py` and `cli/scrape.py` should be gone after the migration.
