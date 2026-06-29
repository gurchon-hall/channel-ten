# agents.md — channel-ten

Guidelines for automated agents (CI, coding, PR review) working on this repository.

---

## Repository map

```text
channel_ten/
├── cli/             CLI entry points (one file per subcommand)
├── output/          Serializers: YAML and TXT writers
├── parser/          TWD text-format parsers (header, deck, helpers)
├── scraper/         HTTP scraping (forum, TWDA archive, VEKN calendar)
├── _krcg_helper.py  krcg card-database wrappers
├── _logger.py       Logging configuration (single source of truth)
├── models.py        Pydantic data models (canonical representation)
├── publisher.py     GitHub PR publisher
└── validator.py     Pure validation logic (no I/O)
tests/               pytest suite — mirrors channel_ten/ structure
.github/workflows/   CI definitions (see below)
```

Data repository: `gurchon-hall/eternal-vigilance` — YAML files organised as `YYYY/MM/<event_id>.yaml`.
Upstream TWD archive: `GiottoVerducci/TWD` — TXT files under `decks/<event_id>.txt`.

---

## CI agent

### Workflows and their triggers

| Workflow | Trigger | Purpose |
| - | - | - |
| `pre-commit.yml` | push to `main`, all PRs | ruff lint/format + full pytest suite |
| `scrape.yml` | daily 06:00 UTC, push to `main` (src change), manual | Scrape VEKN forum → commit YAML to eternal-vigilance |
| `twda-reimport.yml` | Monday 07:00 UTC, manual | Backfill from GiottoVerducci/TWD |
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

- **ruff failure** → formatting or lint issue. Run `ruff check --fix && ruff format` locally, then re-commit.
- **pytest failure** → check `reports/pytest/` (HTML coverage report) and `--tb=short` output. Do not suppress with `filterwarnings` without understanding the cause.
- **CLI smoke failure** → a subcommand import or argparse registration broke. The smoke tests only call `--help`; if they fail, the error is in `cli/__init__.py` or the subcommand's top-level imports.
- **mypy failure** (run locally, not in CI) → fix types; do not add `# type: ignore` without a comment explaining why.

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
- [ ] `mypy channel_ten/` passes locally (strict mode, see `pyproject.toml`).

### Layer contracts

**`validator.py`** — pure functions only. Takes dicts, returns lists of error strings.
No imports from `cli/`, no I/O, no side effects.

**`parser/`** — takes raw strings, returns Pydantic models. No HTTP, no filesystem.

**`scraper/`** — takes an `httpx.Client`, returns data. Logs at DEBUG. Respects `DEFAULT_DELAY_SECONDS`.

**`output/`** — takes Pydantic models, returns strings or writes files. No validation logic.

**`cli/`** — wires everything together, handles I/O, user messages via `rich`. No business logic inline.

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
  - Integration-touching tests (`httpx`, filesystem, GitHub API) are marked `@pytest.mark.integration`.
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
