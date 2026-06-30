# claude.md — channel-ten

Guidelines for Claude (or any AI coding assistant) working on this repository.

---

## Project at a glance

`channel-ten` is a Python CLI + library that scrapes VTES Tournament Winning Decks
from the VEKN forum and exports them as structured YAML files.  The pipeline is:

```text
scrape / import → parse → enrich (krcg) → validate → output (YAML / TXT) → publish (GitHub PR)
```

Data lives in the sibling repository `gurchon-hall/eternal-vigilance`.
Card data comes from the `krcg` library (≥ 5.0).

---

## Code style

### Compact, functional over OO ceremony

- Keep changes minimal and tight — shorter and denser beats longer and more abstract.
- Prefer plain data and free functions to classes-with-methods; lean functional rather than OO.
- Don't split out a function used in only one place — inline it. Reserve helpers for genuine reuse.
- The existing `ParserRegex` / `ParserHelpers` classes in `parser/_helpers.py` are namespace
  containers, not OO design. Follow the same pattern if you need to group related constants.

### Comments

Default to none. Write a comment only to supply indispensable context that cannot be read
from the code: an external constraint, a data-format/protocol quirk, a citation, or reasoning
that is genuinely surprising. If in doubt, leave it out.

Public functions and classes get a **Google-style docstring**; keep it to the minimum that
serves the reader. Module-level docstrings are
short: one paragraph stating the module's purpose and how it fits the pipeline.

Do not write:

```python
# sort last
cards.sort()
```

Do write (external constraint worth recording):

```python
# Parse raw bytes, not response.text — httpx's charset guess mangles UTF-8 pages
# served without a charset header into mojibake (e.g. "GÃ¤deke").
return BeautifulSoup(response.content, "lxml")
```

### Imports

- Import whole modules; reference qualified: `import re` → `re.compile(...)`.
- Use `from channel_ten import models` or `from channel_ten.models import Tournament`
  for first-party symbols — **absolute imports only**, never `from . import …`.
- Never import inside a function body; all imports live at module top.
- Exception: `from typing import ...` and the standard library are imported by name as usual.

### Logging

Every module that emits log output defines:

```python
import logging
logger = logging.getLogger(__name__)
```

Use `logger` (not `_logger`). Pass arguments lazily:

```python
logger.debug("fetching %s", url)   # good
logger.debug(f"fetching {url}")    # bad — interpolates even when DEBUG is off
```

Logging configuration lives in `channel_ten/_logger.py` (a dedicated config module);
modules never call `logging.basicConfig` themselves.

### Typing

Use builtin generics and union syntax throughout:

```python
list[str]        # not typing.List[str]
dict[str, Any]   # not typing.Dict[str, Any]
str | None       # not Optional[str]
```

`ty` is the type checker (see `[tool.ty]` in `pyproject.toml`). Every public function must have
complete type annotations. Prefer typed wrapper functions to suppression comments.

### Models

The codebase has two parallel representations that are debt to eliminate:

- **Pydantic models** (`CryptCard`, `LibraryCard`, `LibrarySection`, `Deck`, `Tournament`)
  in `models.py` — the canonical, validated form.
- **TypedDicts** (`Crypt_Card_Dict`, `Tournament_Dict`, …) — raw YAML dict shapes used
  in `validator.py` and `_krcg_helper.py` because those modules operate on unvalidated data.

When touching code that uses a `TypedDict`, check whether the caller could instead receive
a validated Pydantic model. Remove the `TypedDict` when the migration is complete for that
path. Do not introduce new `TypedDict`s.

---

## Testing

Tests live in `tests/`. Run:

```bash
pytest                        # full suite
pytest -m "not integration"   # fast unit tests only
```

Rules:

- Every new public function gets at least one unit test.
- Tests that call the network or write to disk are marked `@pytest.mark.integration`.
- `slow` is reserved for tests that take > 5 s even offline.
- The markers `api`, `db`, `performance` are defined but unused — do not add tests with those.
- Use `conftest.py` factories (`make_tournament`, etc.) rather than constructing fixtures inline.
- No `print()` in tests; use `caplog` if you need to assert on log output.

---

## What not to do

- Do not call `logging.basicConfig` in library code.
- Do not import inside a function body.
- Do not use relative imports (`from . import …`).
- Do not add new `TypedDict`s — use Pydantic models.
- Do not introduce new design-pattern classes (Strategy, Factory, Builder…); prefer free functions.
- Do not add `# type: ignore` without a comment explaining why.
- Do not write comments that restate the code (`# sort cards`, `# return result`).
- Do not use `typing.List`, `typing.Dict`, `typing.Optional` — use the builtin forms.
