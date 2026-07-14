# agents.md — channel-ten

Guidelines for automated agents (CI, coding, PR review) working on this repository.

---

## Repository map

```text
channel_ten/
├── cli/             CLI entry points (one file per subcommand; no business logic)
├── output/          Serializers: YAML (TWD), TXT, and TDA YAML writers
├── parser/          Text-format parsers (header, deck, helpers) — deck parser is TWD/TDA-shared
├── scraper/         HTTP scraping (forum, TWDA archive, VDB TDA archive, VEKN calendar)
├── _krcg_helper.py  krcg card-database wrappers
├── _logger.py       Logging configuration (single source of truth)
├── github.py        GitHub REST API helpers and TWDA-specific operations
├── models.py        Pydantic data models: Tournament (TWD) + TdaDeck (TDA), shared Deck/CryptCard/...
├── pipeline.py      Shared TWD pipeline (process_tournament, route_tournament)
├── pipeline_tda.py  TDA pipeline (resolve_author, process_tda_deck, route_tda_deck)
├── publisher.py     GitHub PR orchestration (publish_all_as_single_pr, BatchPRResult) — TWD only
└── validator.py     Pure validation logic (no I/O) — TWD's error_types + TDA's tda_deck_errors
tests/               pytest suite — mirrors channel_ten/ structure
.github/workflows/   CI definitions (see below)
```

Data repository: `gurchon-hall/eternal-vigilance` — TWD YAML files organised as
`YYYY/MM/<event_id>.yaml`; TDA YAML files (one per participant deck, not just the winner)
organised as `tda/YYYY/MM/<event_id>/<author_id>.yaml`. Upstream TWD archive:
`GiottoVerducci/TWD` — TXT files under `decks/<event_id>.txt`. TDA source archive:
`smeea/vdb` — zips under `frontend/public/tournaments/<archive_id>.zip`, see
`docs/tda_pipeline.md`. TDA has no `publish` step — it is never sent upstream anywhere.

---

## CI agent

### Workflows and their triggers

| Workflow | Trigger | Purpose |
| - | - | - |
| `pre-commit.yml` | push to `main`, all PRs | ruff lint/format + full pytest suite |
| `scrape.yml` | daily 06:00 UTC, push to `main` (src change), manual | Scrape VEKN forum → commit YAML to eternal-vigilance |
| `twda-reimport.yml` | Monday 07:00 UTC, manual | Backfill from GiottoVerducci/TWD |
| `tda-scrape.yml` | monthly (1st) 06:00 UTC, push to `main` (src change), manual | Scrape smeea/vdb TDA archives → commit YAML to eternal-vigilance/tda |
| `validate.yml` | Sunday 20:00 UTC, manual | Re-validate + enrich YAML in eternal-vigilance |
| `publish.yml` | Monday 08:00 UTC, manual | Open PR to GiottoVerducci/TWD |
| `feature-review.yml` | issue opened with `enhancement` label | Copilot feasibility comment |

### What CI checks

`pre-commit.yml` runs `pre-commit run --all-files`, which covers:

1. `ruff check --fix` — lint (E, F, W, I, UP rules)
2. `ruff format` — formatting (line length 100)
3. `pytest` — full suite including coverage
4. CLI smoke tests: `channel-ten {scrape,import,parse,publish,validate} --help`

A commit must pass all five before merging. There are no exceptions.

### CI failure triage

- **ruff failure** → formatting or lint issue. Run `ruff check --fix && ruff format` locally,
  then re-commit.
- **pytest failure** → check `reports/pytest/` (HTML coverage report) and `--tb=short` output.
  Do not suppress with `filterwarnings` without understanding the cause.
- **CLI smoke failure** → a subcommand import or argparse registration broke. The smoke tests only
  call `--help`; if they fail, the error is in `cli/__init__.py` or the subcommand's top-level
  imports.
- **ty failure** (run locally, not in CI) → fix types; do not add a `ty: ignore` comment without
  explaining why.

### Environment variables

| Variable | Used by | Source in CI |
| - | - | - |
| `GITHUB_TOKEN` | `publish`, `import` commands | GitHub Actions secret |
| `MIN_PLAYERS` | validator | env, defaults to `12` |
| `KRCG_*` | krcg library internals | set by krcg at runtime |

---

## Coding agent

### Before writing code

1. Read `claude.md` for style rules (imports, logging, typing, comments).
2. Identify which layer the change belongs to: scraping, parsing, validation, output, or CLI.
   Keep layers separate — `validator.py` has no I/O; `cli/` has no business logic.
3. Check whether the affected path still uses a `TypedDict`; migrate to the Pydantic model
   if the change makes it natural to do so.

### Change checklist

- [ ] All new public functions have complete type annotations and a Google-style docstring.
- [ ] `logger = logging.getLogger(__name__)` at module top (not `_logger`).
- [ ] All imports are absolute (`channel_ten.models`, not `.models`).
- [ ] No new `TypedDict`s introduced; existing ones reduced where possible.
- [ ] New behaviour covered by at least one test in `tests/test_<module>.py`.
- [ ] Network or filesystem tests marked `@pytest.mark.integration`.
- [ ] `ruff check --fix && ruff format` passes locally.
- [ ] `ty check channel_ten/` passes locally (see `[tool.ty]` in `pyproject.toml`).
- [ ] `CLAUDE.md`, `AGENTS.md`, and any relevant file under `docs/` updated to reflect
  the change — API contracts, pitfalls, pipeline steps, or "What not to do" rules.
- [ ] For significant changes (new/renamed CLI flags or subcommands, changed pipeline
  behaviour, changed external integrations) — add an entry under `Unreleased` in
  `CHANGELOG.rst` and update the affected `README.md` section. Skip for internal
  refactors with no user-visible or contract-level effect.

### Layer contracts

**`validator.py`** — pure functions only. Takes dicts, returns lists of error strings.
No imports from `cli/`, no I/O, no side effects.

**`parser/`** — takes raw strings, returns Pydantic models. No HTTP, no filesystem.

**`scraper/`** — takes an `httpx.Client`, returns data. Logs at DEBUG.
Respects `DEFAULT_DELAY_SECONDS`.

**`output/`** — takes Pydantic models, returns strings or writes files. No validation logic.

**`cli/`** — wires everything together, handles I/O, user messages via `rich`.
No business logic inline.

### Common pitfalls

- **Charset**: always pass `response.content` (bytes) to BeautifulSoup, not `response.text`.
  httpx's charset guess mangles UTF-8 pages served without a `charset` header.
- **TypedDict casting**: `validator.py` uses `cast()` heavily because it operates on raw
  YAML dicts. When migrating a path to Pydantic, remove the casts — do not add new ones.
- **krcg availability**: `is_krcg_loaded()` may return `False` in offline environments.
  Functions that call krcg must guard with this check and return empty results, not raise.
- **Date parsing**: VEKN forum dates appear in many locale-dependent formats. Use
  `Tournament.parse_date()` (the Pydantic field validator), not `datetime.strptime` directly.
- **Grouping rule**: all non-ANY crypt card groups must form a set of at most 2 consecutive
  integers. The `_pick_best_crypt_version` helper in `validator.py` encodes this logic; do
  not reimplement it elsewhere.
- **`fetch_event_winner` return type**: this function returns `tuple[str, int | None] | None`,
  not a plain string. The tuple carries `(winner_name, vekn_id)` where `vekn_id` is parsed
  from the player's profile link in the standings table. Callers unpack the tuple; test mocks
  must return a tuple or `None`. Returning a plain string will raise `TypeError` at unpack.
  `unconfirmed_winner` is set only when the function returns `None` (standings absent), not
  when the player-registry lookup is ambiguous. See `docs/player_name_extraction.md`.
- **Tournament name is calendar-derived, not forum-derived**: a forum poster can prepend a
  free-text note before the actual TWD header, shifting every header line down by one — the
  note gets parsed as `name`, and the real name bleeds into `location`. Rescraping the forum
  post (`validate` step 1) reproduces the same mis-parse, since the source text hasn't
  changed. The only fix is overriding `name` from the VEKN event calendar
  (`fetch_event_name`), which both `pipeline._check_calendar_name` (scrape/import) and
  `cli/validate.py::_check_and_update_name` (validate) do. Do not remove either call in favor
  of trusting the forum-parsed name.
- **`fetch_event_name` selector order**: VEKN's event-calendar pages rarely have
  JSON-LD or an `<h1>` — the title is almost always in
  `<div class="componentheading">` (a Joomla/JEvents template class), confirmed via a
  live `scrape` run where nearly every event logged `"Could not extract event title"`
  before this strategy was added. Keep `componentheading` checked before the `<h1>`
  fallback; removing or reordering it makes `unconfirmed_name` fire on almost every
  scraped tournament instead of only the rare forum mis-parse case.
- **`_check_calendar_name` return type**: like `_check_calendar_winner`, this returns
  `tuple[Tournament, bool]`, not a plain `Tournament` — the second element is
  `calendar_name_missing`, `True` when the calendar page has no name data at all. Only
  `pipeline.process_tournament` (scrape/import) threads this into an `"unconfirmed_name"`
  error; `cli/validate.py` intentionally does not, so a transient fetch failure on an
  already-published, previously-confirmed file doesn't bounce it into `errors/` on a later
  `validate` run. See `docs/player_name_extraction.md`.
- **Fork ownership**: `ensure_fork` always forks `GiottoVerducci/TWD` into the `gurchon-hall`
  org (`FORK_OWNER` in `channel_ten/github.py`), never the token's personal account. The
  token's user needs repo-creation rights in that org.
- **Stale PR cleanup**: `publish_all_as_single_pr` lists open upstream PRs headed from the
  fork (`list_open_prs_from_fork`), closes them, and deletes their branches before creating
  this run's branch — except a branch that happens to match today's run. This runs every
  non-dry-run publish, so at most one TWD PR is ever open at a time. Mocks for
  `publish_all_as_single_pr` tests must patch `list_open_prs_from_fork` (return `[]` if the
  test doesn't care about cleanup) or the real function will attempt a live GitHub call.
- **`except A, B:` is not a Python 2 leftover — it's valid Python 3.14 (PEP 758)**:
  `_krcg_helper.py` and `parser/_helpers.py` use the unparenthesized multi-exception form
  (`except TypeError, ValueError:`), which only parses on Python ≥ 3.14 (`requires-python`
  in `pyproject.toml`). Any tool or agent running on an older interpreter (its own `ast`
  module, an IDE, a stale local venv) will report a `SyntaxError` here — that is a tooling
  limitation, not a bug in the file. `ruff format` (target-version `py314`) actively
  rewrites `except (A, B):` *into* this unparenthesized form, so do not "fix" it back to
  parenthesized — the next `ruff format` run reintroduces the unparenthesized style anyway.
  If you cannot get a real Python 3.14 locally to test against, patch a throwaway copy of
  the file (never the committed one) instead of changing the syntax.

---

## PR review agent

### What to check

- Correctness
  - Does the changed layer respect its contract (see above)?
  - Are new Pydantic validators tested with both valid and invalid inputs?
  - Do scraper changes still respect the 1.5 s delay and the `robots.txt` note in the README?
- Style (non-negotiable)
  - Absolute imports only.
  - `logger` (not `_logger`), lazy argument passing.
  - Builtin generic types (`list`, `dict`, `str | None`), not `typing.*`.
  - No new `TypedDict`s.
  - No comments that restate the code.
- Tests
  - Integration-touching tests (`httpx`, filesystem, GitHub API) are marked
    `@pytest.mark.integration`.
  - `conftest.py` factories are used rather than hand-rolled fixtures.
- Debt direction
  - Does the PR reduce or at least not increase the number of `TypedDict` usages?
  - Does it reduce or maintain the number of `# type: ignore` comments?

### What not to block on

- Module-level docstring length, as long as purpose and pipeline position are stated.
- Choice between `dataclass` and Pydantic for internal-only result containers (`BatchPRResult`
  in `publisher.py` is a `dataclass` — that is fine for non-validated output types).
- Test verbosity; fixtures may be descriptive.

### Comment format

Prefix review comments with one of:

- `[blocker]` — must be fixed before merge (correctness, missing tests, style rule violation).
- `[suggestion]` — improvement that is not required (refactor opportunity, doc clarity).
- `[question]` — genuine uncertainty; do not block until answered.

Do not leave comments without a prefix.
