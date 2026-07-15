# claude.md — channel-ten

Guidelines for Claude (or any AI coding assistant) working on this repository.

---

## Project at a glance

`channel-ten` is a Python CLI + library that scrapes VTES Tournament Winning Decks
from the VEKN forum and exports them as structured YAML files.  The pipeline is:

```text
scrape / import → parse → enrich (krcg) → validate → output (YAML / TXT) → publish (GitHub PR)
```

It also runs a second, parallel pipeline for TDA (Tournament Deck Archive — every
participant's deck, not just the winner's), sourced from `smeea/vdb` instead of the VEKN
forum: `tda-scrape → parse (parser/_tda.py) → enrich (krcg, reused) → validate
(validator.tda_deck_errors) → output (output/tda_yaml.py)`. TDA has no `publish` step.
See `docs/tda_pipeline.md` for the source archive format and `AGENTS.md`'s repo map for
which modules are TWD-only, TDA-only, or shared.

Data lives in the sibling repository `gurchon-hall/eternal-vigilance`, TWD under
`YYYY/MM/<event_id>.yaml` and TDA under `tda/YYYY/MM/<event_id>/<author_id>.yaml`.
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

After every non-trivial change, update documentation:

- `CLAUDE.md` — add or amend "What not to do" rules or project-level notes.
- `AGENTS.md` — add or amend the change checklist, common pitfalls, or layer contracts.
- `docs/` — update or create a topic document when the change affects an API contract,
  a pipeline step, or a non-obvious behaviour that future contributors need to know.
- `CHANGELOG.rst` and `README.md` — update for **significant** changes: new or renamed
  CLI flags/subcommands, changed pipeline behaviour, changed external integrations
  (GitHub API surface, fork/publish targets), or anything a user or downstream contributor
  would need to know about to keep working correctly. Add the entry under `Unreleased` in
  `CHANGELOG.rst`; update the relevant `README.md` section (workflow description, CLI
  reference, or repo map) only where it is now stale. Skip both for internal refactors with
  no user-visible or contract-level effect.

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
- Do not change `fetch_event_winner` to return a plain `str` — it returns
  `tuple[str, int | None] | None`. The VEKN ID must be extracted from the standings
  link so ambiguous name lookups in the player registry are bypassed. See
  `docs/player_name_extraction.md`.
- Do not fork `GiottoVerducci/TWD` under the token's personal account. `ensure_fork`
  (`channel_ten/github.py`) always forks into the `gurchon-hall` org (`FORK_OWNER`)
  via the `organization` param on `POST /forks`; the token's user must have repo-creation
  permission in that org.
- Do not assume the fork's repo name matches `TWDA_REPO` (upstream's name, `"TWD"`).
  The fork is named independently via `FORK_REPO` (`"twd-fork"`) — `ensure_fork` checks
  for it first and only creates it via `POST /forks` (with `"name": FORK_REPO`) when
  missing, since calling that endpoint unconditionally previously caused GitHub to create
  a second, differently-named duplicate fork under a race condition. `create_branch`,
  `put_file`, and `delete_branch` take an explicit `repo=` param for this reason — always
  pass `repo=FORK_REPO` at fork-side call sites, never rely on their `TWDA_REPO` default.
- Do not trust the forum-parsed tournament `name` as final. A poster can prepend a note
  before the TWD header, shifting every line down and turning the note into `name`. Both
  `pipeline._check_calendar_name` (scrape/import) and `cli/validate.py::_check_and_update_name`
  (validate) override `name` with the VEKN event calendar's title (`fetch_event_name`) — do not
  remove either check.
- Do not change `_check_calendar_name` back to returning a plain `Tournament`. It returns
  `tuple[Tournament, bool]` — the bool is `calendar_name_missing`, which
  `pipeline.process_tournament` turns into an `"unconfirmed_name"` validation error so a
  first-scrape deck whose name the calendar can't confirm gets routed to
  `errors/unconfirmed_name/` for review instead of silently publishing an unverified (and
  possibly forum-note-corrupted) name.
- Do not open a new publish PR without first closing stale ones. `publish_all_as_single_pr`
  closes every open upstream PR headed from the fork (and deletes its branch) before
  creating this run's branch, except the branch matching today's run — this keeps at most
  one open TWD PR at a time. This step is skipped on `--dry-run`.
- Do not bend `Tournament`/`pipeline.py`/`output/yaml.py` to fit TDA's shape (one event
  → many decks, `event_id` that can be non-numeric like `"online1"`, no mandatory
  `event_url`). Use `TdaDeck` (`models.py`), `pipeline_tda.py`, and `output/tda_yaml.py`
  instead — they already reuse everything that *is* shape-compatible (`Deck`,
  `parser._deck.parse_deck_block`, the krcg enrichment functions, `scraper.fetch_player`,
  `pipeline.RouteCounters`). See `docs/tda_pipeline.md`.
- Do not treat a TDA archive's numeric zip filename as a *confirmed* VEKN calendar event
  id, and do not add a VEKN-calendar cross-check step to the TDA pipeline to "confirm"
  it the way TWD does for `name`/`winner`. It is a reasonable, documented assumption
  (see `docs/tda_pipeline.md`) used only to build an informational `event_url` — TDA's
  authoritative source is `archon.xlsx`, not a forum post, so it doesn't have the
  mis-parse failure mode that makes the TWD cross-check necessary.
- Do not treat a numeric TDA `Author:` value as proof of a real VEKN member number. The
  Archon tool assigns small placeholder numbers (seen: 101–125) for participants without
  VEKN registration in recurring online events. This is a source data-quality limitation,
  not a bug in `pipeline_tda.resolve_author` — the user-specified rule (numeric → use
  directly, non-numeric → resolve via the player registry) is implemented as given.
