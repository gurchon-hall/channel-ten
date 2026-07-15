# Channel 10

Scrape tournament winning decks (TWD) from the
[VEKN forum](https://www.vekn.net/forum/event-reports-and-twd) and export them as YAML files.

[![Pre-commit checks](https://github.com/gurchon-hall/channel-ten/actions/workflows/pre-commit.yml/badge.svg)](https://github.com/gurchon-hall/channel-ten/actions/workflows/pre-commit.yml)
[![Scrape VTES TWD](https://github.com/gurchon-hall/channel-ten/actions/workflows/scrape.yml/badge.svg)](https://github.com/gurchon-hall/channel-ten/actions/workflows/scrape.yml)
[![TWD resync archive](https://github.com/gurchon-hall/channel-ten/actions/workflows/twda-reimport.yml/badge.svg)](https://github.com/gurchon-hall/channel-ten/actions/workflows/twda-reimport.yml)
[![Validate VTES TWD](https://github.com/gurchon-hall/channel-ten/actions/workflows/validate.yml/badge.svg)](https://github.com/gurchon-hall/channel-ten/actions/workflows/validate.yml)
[![Publish TWD Deck PRs](https://github.com/gurchon-hall/channel-ten/actions/workflows/publish.yml/badge.svg)](https://github.com/gurchon-hall/channel-ten/actions/workflows/publish.yml)
[![TDA Scrape smeea/vdb](https://github.com/gurchon-hall/channel-ten/actions/workflows/tda-scrape.yml/badge.svg)](https://github.com/gurchon-hall/channel-ten/actions/workflows/tda-scrape.yml)

## Data format

Each tournament produces one YAML file named `{event_id}.yaml` where `event_id` is the numeric id
from the VEKN event calendar URL (e.g. `/event/8470` → `8470.yaml`).

Data files are stored in the dedicated repository
[gurchon-hall/eternal-vigilance](https://github.com/gurchon-hall/eternal-vigilance), organized as
`YYYY/MM/<event_id>.yaml`.

This convention mirrors the [GiottoVerducci/TWD](https://github.com/GiottoVerducci/TWD) archive,
which uses `decks/{event_id}.txt`.

The forum is not the complete record: some TWDs only ever made it into the
GiottoVerducci/TWD archive. The `import` command backfills those: it imports every
`decks/{event_id}.txt` whose `event_id` is **not already present in the base**, running each through
the same enrichment/validation pipeline as `scrape`.

## TDA data format (Tournament Deck Archive)

TWD only ever holds the *winning* deck of a tournament. TDA (Tournament Deck Archive) is a
separate, parallel dataset holding **every participant's** deck, sourced from
[`smeea/vdb`](https://github.com/smeea/vdb)'s `frontend/public/tournaments/*.zip` archives — the
only available source for full tournament decklists, since no official VEKN archive of them exists.
Each archive is one tournament: a VEKN "Archon" tournament-report spreadsheet (`archon.xlsx`) plus
one deck `.txt` per participant, in the same textual format as a TWD post's deck block.

Because one tournament yields many decks, TDA files are stored one directory level deeper than TWD:
`eternal-vigilance/tda/YYYY/MM/<event_id>/<author_id>.yaml`, where `event_id` is the archive's zip
filename stem (numeric for events with a VEKN calendar id, e.g. `10367`; a short slug like `online1`
for recurring online events that never got one) and `author_id` is the deck author's VEKN member
number when resolvable, or a slug of the raw author string otherwise. See
[`docs/tda_pipeline.md`](docs/tda_pipeline.md) for the full archive/spreadsheet layout this
depends on.

TDA and TWD are independent datasets with different shapes (one deck vs. many decks per event) —
they are never merged into the same file or directory tree.

## Installation

```bash
git clone https://github.com/gurchon-hall/channel-ten.git
cd channel-ten
uv sync --group dev
pre-commit install          # register git hooks (ruff, pytest, CLI smoke tests)
```

Requires Python ≥ 3.14.

## Usage

### CLI

Every subcommand accepts `--verbose` / `-v` for debug logging and `--twds-dir`
pointing at the root of a TWD data checkout (default: `twds/`).

`scrape`, `validate`, and `tda-scrape` all resolve player names/VEKN numbers via
the VEKN player registry, which requires a logged-in session. Set
`$VEKN_USERNAME` and `$VEKN_PASSWORD` (a regular vekn.net account) before running
any of them — without both set, every registry lookup fails and falls back to
the raw, unresolved name or id.

#### Command `scrape`: fetch new TWDs from the VEKN forum

| Argument | Description | Mandatory | Default |
| -------- | ----------- | --------- | ------- |
| `--start-page` | 0-indexed page to start scraping from | No | `0` |
| `--last-page` | 0-indexed page to stop scraping at (inclusive) | No | `None` (scrape all pages) |
| `--delay` | Seconds between HTTP requests | No | `1.5` |
| `--overwrite` | Overwrite existing YAML files | No | `False` |
| `--twds-dir` | Directory to write YAML files to | No | `twds/` |

#### Command `import`: backfill decks that exist in GiottoVerducci/TWD

| Argument | Description | Mandatory | Default |
| -------- | ----------- | --------- | ------- |
| `--delay` | Seconds between HTTP requests | No | `1.5` |
| `--overwrite` | Re-fetch and overwrite decks already in the base too | No | `False` |
| `--twds-dir` | Directory to write YAML files to | No | `twds/` |
| `--limit` | Limit the number of decks to import (for testing) | No | `None` (import all) |
| `--github-token` | GitHub token to raise the deck-listing rate limit; falls back to `$GITHUB_TOKEN` | No | `None` |
| `--create-issue` | Open a GitHub issue on GiottoVerducci/TWD listing decks that failed to import | No | `False` |

Note: only `--create-issue` strictly requires a GitHub token (with `public_repo` scope) —
`--github-token`/`$GITHUB_TOKEN` is otherwise optional and only raises the deck-listing rate limit.

#### Command `tda-scrape`: fetch TDA archives (every participant's deck) from smeea/vdb

| Argument | Description | Mandatory | Default |
| -------- | ----------- | --------- | ------- |
| `--tda-dir` | Directory to write YAML files to (`<dir>/YYYY/MM/<event_id>/<author_id>.yaml`) | No | `tda/` |
| `--delay` | Seconds between HTTP requests | No | `1.5` |
| `--overwrite` | Overwrite existing YAML files | No | `False` |
| `--limit` | Process at most N archives (for testing) | No | `None` (process all) |
| `--github-token` | GitHub token to raise the archive-listing rate limit; falls back to `$GITHUB_TOKEN` | No | `None` |

#### Command `parse`: convert a single file between .txt and YAML

| Argument | Description | Mandatory | Default |
| -------- | ----------- | --------- | ------- |
| `<file>` | Path to a .txt or .yaml file to parse | Yes | '' |
| `--stdout` | Print the output to stdout instead of writing a file | No | `False` |
| `--twds-dir` | Directory to write YAML files to | No | `twds/` |
| `--overwrite` | Overwrite the output file if it already exists | No | `False` |

#### Command `validate`: re-run the validation pipeline on published YAML files

| Argument | Description | Mandatory | Default |
| -------- | ----------- | --------- | ------- |
| `--full-validation` | Re-validate every YAML file in twds/ (slow, rescrapes the forum) | No | `False` |
| `--errors-only` | Re-validate only the files currently under twds/errors/ | No | `False` |
| `--dry-run` | Report only — do not move or update any files | No | `False` |
| `--force-date` | Overwrite date_start when it disagrees with the VEKN event calendar | No | `False` |

#### Command `publish`: open a PR with new decks against GiottoVerducci/TWD

| Argument | Description | Mandatory | Default |
| -------- | ----------- | --------- | ------- |
| `--delay` | Seconds between GitHub API file commits | No | `1.0` |
| `--github-token` | GitHub PAT with `public_repo` scope; falls back to `$GITHUB_TOKEN` | No | `None` |
| `--publish-dir` | Directory to write Markdown publish reports | No | `publish/` |
| `--include-pre-2020` | Include decks from before 2020 (skipped by default) | No | `False` |
| `--dry-run` | Simulate publish without opening a PR (branch is deleted afterwards) | No | `False` |

Note: this command always requires a GitHub token with repo access, set via `--github-token` or
`$GITHUB_TOKEN`. It can be exported before the command or prefixed to the command itself.

### Python API

```python
import httpx
from channel_ten.scraper import scrape_forum
from channel_ten.output import write_tournament_yaml
from pathlib import Path

with httpx.Client() as client:
    for tournament, icon in scrape_forum(client, max_pages=2, start_page=5):
        write_tournament_yaml(tournament, output_dir=Path("twds"))
```

## Development

```bash
# Run tests
pytest

# Lint + format
ruff check channel_ten/ tests/
ruff format channel_ten/ tests/

# Run all pre-commit hooks manually against every file
pre-commit run --all-files
```

### Pre-commit hooks

The `.pre-commit-config.yaml` runs the following checks on every commit:

| Hook | What it does |
| --- | --- |
| `ruff lint` | Lint with auto-fix (`ruff check --fix`) |
| `ruff format` | Format with ruff |
| `pytest` | Full test suite |
| `cli smoke: scrape --help` | Verify the `scrape` subcommand loads cleanly |
| `cli smoke: import --help` | Verify the `import` subcommand loads cleanly |
| `cli smoke: parse --help` | Verify the `parse` subcommand loads cleanly |
| `cli smoke: publish --help` | Verify the `publish` subcommand loads cleanly |

The GitHub Actions workflow `pre-commit.yml` runs the same hooks on every push and pull request as
a safety net in case local hooks are not installed.

## GitHub Actions

The workflow in `.github/workflows/scrape.yml`:

- Runs daily at 06:00 UTC
- Also triggered on push to `main` when source files change
- Can be triggered manually with optional `start_page`, `last_page`, and `overwrite` inputs
- Scrapes the forum and commits new YAML files to
  [eternal-vigilance](https://github.com/gurchon-hall/eternal-vigilance)

The workflow in `.github/workflows/import.yml`:

- Runs every Monday at 07:00 UTC
- Can be triggered manually with optional `limit` and `overwrite` inputs
- Imports decks from [GiottoVerducci/TWD](https://github.com/GiottoVerducci/TWD) whose `event_id`
  is not yet in [eternal-vigilance](https://github.com/gurchon-hall/eternal-vigilance) and commits
  the new YAML files

The workflow in `.github/workflows/validate.yml`:

- Runs every Sunday at 20:00 UTC
- Can be triggered manually with an optional `full_validation` boolean input
- Re-validates all published YAML files in eternal-vigilance, enriches them via krcg, and commits
  any updates

The workflow in `.github/workflows/publish.yml`:

- Runs every Monday at 08:00 UTC
- Can be triggered manually
- Reads decks from eternal-vigilance, publishes new decks to
  [GiottoVerducci/TWD](https://github.com/GiottoVerducci/TWD) as a single PR from a fork under the
  `gurchon-hall` organization
- Closes any PR (and deletes its branch) left open on the fork from a previous run before opening
  the new one, so at most one TWD PR is open at a time
- Commits a Markdown publish report to `eternal-vigilance/publish/YYYY/MM/`

The workflow in `.github/workflows/tda-scrape.yml`:

- Runs monthly, on the 1st at 06:00 UTC (TDA archives are added far less often than TWD forum posts)
- Also triggered on push to `main` when source files change
- Can be triggered manually with optional `limit` and `overwrite` inputs
- Scrapes smeea/vdb TDA archives and commits new YAML files to
  [eternal-vigilance](https://github.com/gurchon-hall/eternal-vigilance)`/tda/`

The workflow in `.github/workflows/pre-commit.yml`:

- Runs on every push to `main` and on pull requests
- Installs the `[dev]` dependencies and runs `pre-commit run --all-files`

## YAML output example

```yaml
name: Conservative Agitation
location: Vila Velha, Brazil
date_start: October 1st 2016
rounds_format: 2R+F
players_count: 12
winner: Ravel Zorzal
vekn_number: 3200001
event_url: https://www.vekn.net/event-calendar/event/8470
event_id: '8470'
vp_comment: 5VP in final
deck:
  name: Eyes of the Insane
  created_by: Bobby Lemon
  description: A great deck that wins all the time.
  crypt_count: 12
  crypt:
    - count: 2
      name: Nathan Turner
      id: 200848
      capacity: 4
      disciplines: PRO ani
      clan: Gangrel
      grouping: 6
  library_count: 89
  library_sections:
    - name: Master
      count: 14
      cards:
        - count: 1
          name: Anarch Free Press, The
          id: 100038
          comment: does not provide a free press!
```

## Project structure

```txt
channel_ten/
├── cli/
│   ├── __init__.py        # CLI entry point (channel-ten) and argparse setup
│   ├── _common.py         # CLI shared utilities
│   ├── reimport.py        # CLI command: import decks from GiottoVerducci/TWD
│   ├── parse.py           # CLI command: parse .txt ↔ .yaml
│   ├── publish.py         # CLI command: publish decks to GitHub
│   ├── scrape.py          # CLI command: scrape the VEKN forum
│   ├── tda_scrape.py      # CLI command: scrape smeea/vdb TDA archives
│   └── validate.py        # CLI command: re-validate published YAML files
├── output/
│   ├── __init__.py
│   ├── _common.py         # Output shared utilities (to_serializable, reorder_dict, date_subdir)
│   ├── tda_yaml.py        # TDA YAML serializer
│   ├── txt.py             # TXT serializer
│   └── yaml.py            # YAML serializer + reorder_tournament_dict
├── parser/
│   ├── __init__.py
│   ├── _deck.py           # Deck section parser (shared by TWD and TDA)
│   ├── _header.py         # Tournament header parser
│   ├── _helpers.py        # Parser utilities
│   ├── _tda.py            # Top-level TDA deck text parser
│   └── _twd.py            # Top-level TWD text format parser
├── scraper/
│   ├── __init__.py
│   ├── _forum.py          # Forum index traversal and TWD extraction
│   ├── _http.py           # Low-level HTTP helpers and constants
│   ├── _icons.py          # Topic icon detection
│   ├── _tda.py            # smeea/vdb TDA archive listing, fetching and archon.xlsx parsing
│   ├── _twda.py           # GiottoVerducci/TWD archive listing and fetching
│   └── _vekn.py           # VEKN event calendar and player registry lookups
├── _krcg_helper.py        # krcg card-database wrappers (lookup, enrichment, canonicalization)
├── _logger.py             # Logging configuration (setup_logging)
├── github.py              # GitHub REST API helpers and TWDA-specific operations
├── models.py              # Pydantic data models
|                          # (Card, CryptCard, LibraryCard, Deck, Tournament, TdaDeck)
├── pipeline.py            # Shared TWD pipeline (process_tournament, route_tournament)
├── pipeline_tda.py        # TDA pipeline (resolve_author, process_tda_deck, route_tda_deck)
├── publisher.py           # GitHub PR orchestration (publish_all_as_single_pr, BatchPRResult)
└── validator.py           # YAML validation logic (TWD's error_types + TDA's tda_deck_errors)
scripts/
└── migrate_card_names.py  # One-time migration: rename cards and backfill IDs in eternal-vigilance
tests/
├── conftest.py            # Shared test factories (make_tournament, make_tda_deck, etc.)
├── test_cli_common.py
├── test_cli_parse.py
├── test_cli_publish.py
├── test_cli_scrape.py
├── test_cli_validate.py
├── test_krcg_helper.py
├── test_models.py
├── test_models_tda.py
├── test_output.py
├── test_output_tda.py
├── test_parser.py
├── test_parser_extras.py
├── test_parser_tda.py
├── test_pipeline_tda.py
├── test_publisher.py
├── test_scraper.py
├── test_scraper_icons.py
├── test_scraper_tda.py
└── test_validator.py
.github/                   # TWD/TDA data and publish reports live in gurchon-hall/eternal-vigilance
└── workflows/
    ├── scrape.yml         # CRON scrape at 06:00 UTC every day
    ├── import.yml         # CRON import from GiottoVerducci/TWD at 07:00 UTC every Monday
    ├── tda-scrape.yml     # CRON scrape smeea/vdb TDA archives at 06:00 UTC on the 1st of the month
    ├── validate.yml       # CRON re-validate at 20:00 UTC every Sunday
    ├── publish.yml        # CRON publish at 08:00 UTC every Monday
    ├── pre-commit.yml     # Pre-commit checks on push / PR
    └── feature-review.yml # Automated feature-request review
.pre-commit-config.yaml
pyproject.toml
.env.example
```

## Notes

- The scraper respects a 1.5s delay between requests by default (`--delay`).
- Use `--start-page` / `--last-page` to target a specific page range. Both are 0-indexed;
  `--last-page` is inclusive (page 0 = `limitstart=0`, page 1 = `limitstart=20`, etc.).
- Winner lookup against the VEKN member database is applied automatically during scraping.
  `vekn_number` is written to the file. Unresolvable names are flagged but not blocked.
- Content validation routes tournaments with errors to `twds/errors/<error_type>/` automatically.
- Forum posts marked with the "merged" icon are written to `twds/changes_required/` instead of the
  normal date tree, so they can be reviewed before merging.
- `validate` (fast mode) re-validates only the 25 most recent files that are neither stored in
  errors nor changes required; `--full-validation` rescrapes every published file.
- To permanently protect a manually edited file from being overwritten by `validate`, add its event
  ID to `skip_events.txt` at the root of the eternal-vigilance checkout (one ID per line, `#` for
  comments). The file is optional; absent means no events are skipped.
- `publish --dry-run` commits all files to a temporary branch to verify behaviour, then deletes the
  branch without opening a PR. A dry-run report is saved to
  `publish/YYYY/MM/dry-run-{date}-{HH-MM-SS}.md`.
- The `User-Agent` header identifies the bot to the server.
- Always verify `robots.txt` and VEKN forum terms before large-scale scraping.
