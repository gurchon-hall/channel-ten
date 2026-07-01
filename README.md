# Channel 10

Scrape tournament winning decks (TWD) from the [VEKN forum](https://www.vekn.net/forum/event-reports-and-twd) and export them as YAML files.

[![Pre-commit checks](https://github.com/gurchon-hall/channel-ten/actions/workflows/pre-commit.yml/badge.svg)](https://github.com/gurchon-hall/channel-ten/actions/workflows/pre-commit.yml)
[![Scrape VTES TWD](https://github.com/gurchon-hall/channel-ten/actions/workflows/scrape.yml/badge.svg)](https://github.com/gurchon-hall/channel-ten/actions/workflows/scrape.yml)
[![TWD resync archive](https://github.com/gurchon-hall/channel-ten/actions/workflows/twda-reimport.yml/badge.svg)](https://github.com/gurchon-hall/channel-ten/actions/workflows/twda-reimport.yml)
[![Validate VTES TWD](https://github.com/gurchon-hall/channel-ten/actions/workflows/validate.yml/badge.svg)](https://github.com/gurchon-hall/channel-ten/actions/workflows/validate.yml)
[![Publish TWD Deck PRs](https://github.com/gurchon-hall/channel-ten/actions/workflows/publish.yml/badge.svg)](https://github.com/gurchon-hall/channel-ten/actions/workflows/publish.yml)

## Data format

Each tournament produces one YAML file named `{event_id}.yaml` where `event_id` is the numeric id from the VEKN event calendar URL (e.g. `/event/8470` → `8470.yaml`).

Data files are stored in the dedicated repository [gurchon-hall/eternal-vigilance](https://github.com/gurchon-hall/eternal-vigilance), organized as `YYYY/MM/<event_id>.yaml`.

This convention mirrors the [GiottoVerducci/TWD](https://github.com/GiottoVerducci/TWD) archive, which uses `decks/{event_id}.txt`.

The forum is not the complete record: some TWDs only ever made it into the GiottoVerducci/TWD archive. The `import` command backfills those — it imports every `decks/{event_id}.txt` whose `event_id` is **not already present in the base**, running each through the same enrichment/validation pipeline as `scrape`.

## Installation

```bash
git clone https://github.com/gurchon-hall/channel-ten.git
cd channel-ten
uv sync --group dev
pre-commit install              # register git hooks (ruff, pytest, CLI smoke tests)
```

Requires Python ≥ 3.14.

## Usage

### CLI

```bash
# Scrape all pages (starting from page 0)
channel-ten scrape

# Scrape pages 0–4 only (--last-page is inclusive, 0-indexed)
channel-ten scrape --last-page 4

# Start scraping from page 5 and stop at page 6
channel-ten scrape --start-page 5 --last-page 6

# Overwrite existing YAML files
channel-ten scrape --overwrite

# Write output to a custom directory (e.g. a local clone of eternal-vigilance)
channel-ten scrape --twds-dir ../eternal-vigilance

# Import TWDs from GiottoVerducci/TWD that are not already in the base
channel-ten import --twds-dir ../eternal-vigilance

# Use a token (raises the GitHub deck-listing rate limit) and cap the run for testing
GITHUB_TOKEN=ghp_xxx channel-ten import --limit 5

# Parse a single local .txt file to YAML (prints to stdout)
channel-ten parse decks/8470.txt

# Parse a .txt file and write YAML to a directory
channel-ten parse decks/8470.txt --twds-dir twds

# Convert a YAML file back to .txt (prints to stdout)
channel-ten parse twds/2023/03/9999.yaml

# Re-validate the 25 most recent published YAML files (fast, default)
channel-ten validate

# Re-validate every YAML file in twds/ (slow, rescrapes the forum)
channel-ten validate --full-validation

# Report only — do not move or update any files
channel-ten validate --dry-run

# Publish new decks as a single PR to GiottoVerducci/TWD
GITHUB_TOKEN=ghp_xxx channel-ten publish

# Publish including pre-2020 decks (skipped by default)
GITHUB_TOKEN=ghp_xxx channel-ten publish --include-pre-2020

# Simulate publish without opening a PR (branch is deleted afterwards)
GITHUB_TOKEN=ghp_xxx channel-ten publish --dry-run
```

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

The GitHub Actions workflow `pre-commit.yml` runs the same hooks on every push and pull request as a safety net in case local hooks are not installed.

## GitHub Actions

The workflow in `.github/workflows/scrape.yml`:

- Runs daily at 06:00 UTC
- Also triggered on push to `main` when source files change
- Can be triggered manually with optional `start_page`, `last_page`, and `overwrite` inputs
- Scrapes the forum and commits new YAML files to [eternal-vigilance](https://github.com/gurchon-hall/eternal-vigilance)

The workflow in `.github/workflows/import.yml`:

- Runs every Monday at 07:00 UTC
- Can be triggered manually with optional `limit` and `overwrite` inputs
- Imports decks from [GiottoVerducci/TWD](https://github.com/GiottoVerducci/TWD) whose `event_id` is not yet in [eternal-vigilance](https://github.com/gurchon-hall/eternal-vigilance) and commits the new YAML files

The workflow in `.github/workflows/validate.yml`:

- Runs every Sunday at 20:00 UTC
- Can be triggered manually with an optional `full_validation` boolean input
- Re-validates all published YAML files in eternal-vigilance, enriches them via krcg, and commits any updates

The workflow in `.github/workflows/publish.yml`:

- Runs every Monday at 08:00 UTC
- Can be triggered manually
- Reads decks from eternal-vigilance, publishes new decks to [GiottoVerducci/TWD](https://github.com/GiottoVerducci/TWD) as a single PR from a fork under the `gurchon-hall` organization
- Closes any PR (and deletes its branch) left open on the fork from a previous run before opening the new one, so at most one TWD PR is open at a time
- Commits a Markdown publish report to `eternal-vigilance/publish/YYYY/MM/`

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
│   └── validate.py        # CLI command: re-validate published YAML files
├── output/
│   ├── __init__.py
│   ├── _common.py         # Output shared utilities
│   ├── txt.py             # TXT serializer
│   └── yaml.py            # YAML serializer + reorder_tournament_dict
├── parser/
│   ├── __init__.py
│   ├── _deck.py           # Deck section parser
│   ├── _header.py         # Tournament header parser
│   ├── _helpers.py        # Parser utilities
│   └── _twd.py            # Top-level TWD text format parser
├── scraper/
│   ├── __init__.py
│   ├── _forum.py          # Forum index traversal and TWD extraction
│   ├── _http.py           # Low-level HTTP helpers and constants
│   ├── _icons.py          # Topic icon detection
│   ├── _twda.py           # GiottoVerducci/TWD archive listing and fetching
│   └── _vekn.py           # VEKN event calendar and player registry lookups
├── _krcg_helper.py        # krcg card-database wrappers (lookup, enrichment, canonicalization)
├── _logger.py             # Logging configuration (setup_logging)
├── github.py              # GitHub REST API helpers and TWDA-specific operations
├── models.py              # Pydantic data models (Card, CryptCard, LibraryCard, Deck, Tournament)
├── pipeline.py            # Shared scraping pipeline (process_tournament, route_tournament)
├── publisher.py           # GitHub PR orchestration (publish_all_as_single_pr, BatchPRResult)
└── validator.py           # YAML validation logic
scripts/
└── migrate_card_names.py  # One-time migration: rename cards and backfill IDs in eternal-vigilance
tests/
├── conftest.py            # Shared test factories (make_tournament, etc.)
├── test_cli_common.py
├── test_cli_parse.py
├── test_cli_publish.py
├── test_cli_scrape.py
├── test_cli_validate.py
├── test_krcg_helper.py
├── test_models.py
├── test_output.py
├── test_parser.py
├── test_parser_extras.py
├── test_publisher.py
├── test_scraper.py
├── test_scraper_icons.py
└── test_validator.py
                               # TWD data and publish reports live in gurchon-hall/eternal-vigilance
.github/
└── workflows/
    ├── scrape.yml         # CRON scrape at 06:00 UTC every day
    ├── import.yml         # CRON import from GiottoVerducci/TWD at 07:00 UTC every Monday
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
- Use `--start-page` / `--last-page` to target a specific page range. Both are 0-indexed; `--last-page` is inclusive (page 0 = `limitstart=0`, page 1 = `limitstart=20`, etc.).
- Winner lookup against the VEKN member database is applied automatically during scraping. `vekn_number` is written to the file. Unresolvable names are flagged but not blocked.
- Content validation routes tournaments with errors to `twds/errors/<error_type>/` automatically.
- Forum posts marked with the "merged" icon are written to `twds/changes_required/` instead of the normal date tree, so they can be reviewed before merging.
- `validate` (fast mode) re-validates only the 25 most recent files that are neither stored in errors nor changes required; `--full-validation` rescrapes every published file.
- To permanently protect a manually edited file from being overwritten by `validate`, add its event ID to `skip_events.txt` at the root of the eternal-vigilance checkout (one ID per line, `#` for comments). The file is optional; absent means no events are skipped.
- `publish --dry-run` commits all files to a temporary branch to verify behaviour, then deletes the branch without opening a PR. A dry-run report is saved to `publish/YYYY/MM/dry-run-{date}-{HH-MM-SS}.md`.
- The `User-Agent` header identifies the bot to the server.
- Always verify `robots.txt` and VEKN forum terms before large-scale scraping.
