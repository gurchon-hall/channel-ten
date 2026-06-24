=========
Changelog
=========

All notable changes to Channel 10 are documented here.
Versioning follows `Semantic Versioning <https://semver.org/>`_ (major.minor.patch),
starting from v0.1.0.

.. contents:: Versions
   :local:
   :depth: 1

----

Unreleased — 2026-06-20
======================

This release captures changes that are now available but not yet published as a
formal tagged version.

Added
-----
- Crypt and library cards now carry their krcg ``id`` in the YAML output,
  resolved during krcg enrichment (crypt ids are group-specific). Cards krcg
  cannot identify are left without an id.
- Vampire path support for crypt cards, including enrichment and text output.
- Configurable minimum-player threshold via the ``MIN_PLAYERS`` environment
  variable for validation checks.
- Improved handling for card metadata and output formatting when path data is
  available.

Changed
-------
- Validation logic now respects environment-based configuration for tournament
  thresholds.
- Card output now preserves path information for supported vampires.

Fixed
-----
- Resolved edge cases around card enrichment and metadata display for path-aware
  vampires.

----

v0.5.0 — 2026-06-19
====================

Major architectural shift: TWD data is now hosted externally in the
``eternal-vigilance`` repository.  The project itself was also renamed from its
working title to **Channel 10**.

Added
-----
- Import layer for ``GiottoVerducci/TWD`` backfill (``29ffab7``).
- Canonicalization of crypt card names during the enrichment step (``c4b4728``).
- Enhanced KRCG card-name handling: fuzzy lookup, ADV/non-ADV disambiguation,
  and grouping-aware vampire resolution (``100fe13``).

Changed
-------
- Project renamed to **Channel 10**; repository moved to
  ``gurchon-hall/channel-ten`` (``027e3e6``, ``f421bd9``).
- TWD YAML data externalised to the ``eternal-vigilance`` repository
  (``97a0f0b``).
- Publish reports moved to ``eternal-vigilance`` (``3536f28``).
- Workflow names updated for consistency (``d1dbd97``, ``c117bef``).

----

v0.4.0 — 2026-04-06
====================

Validation is now a first-class CLI command with support for full (slow) checks,
automatic winner/VEKN-number back-fill, and forum-post URL verification.

Added
-----
- ``validate`` CLI command for tournament YAML files with error routing
  (``d7aca47``).
- ``--full`` flag on ``validate`` to enable network-heavy checks (``ceae459``).
- Automatic update of ``winner`` and ``vekn_number`` fields during validation
  (``1d16f4f``).
- Forum-post URL checks and improved event-date fetching in the validation
  pipeline (``3030b46``).
- Retry mechanism on ``git push`` to handle race conditions in CI (``ee7adff``).
- Test coverage increase (``8f6df0f``).

Fixed
-----
- Validation job conditions in GitHub Actions workflow (``e1cf6b5``,
  ``0bca85a``).
- Tournament model field ordering: ``deck`` moved to end of YAML output
  (``d8b540a``).
- Handling of missing ``winner`` and ``vekn_number`` in calendar lookups
  (``06ebda6``, ``21b7996``).
- ``unconfirmed_winner`` error key renamed from previous identifier; tests
  updated (``5fe911c``).
- Crypt card output alignment and spacing (``47b3d7a``).
- Fast-validation YAML file threshold reduced; skip directories updated
  (``19d0de7``).
- Ruff version pinned and linting configuration adjusted (``7290dac``).
- Workflow name and commit-step description clarified (``5cc2521``).
- Issue #11 resolved (``d684013``).

----

v0.3.0 — 2026-03-30
====================

Automated winner look-up via the VEKN event calendar, ``--dry-run`` publish
mode, fast/slow scrape checks, and pre-commit quality gates.

Added
-----
- VEKN calendar integration for automatic winner look-up and ``krcg``-section
  validation (``d42fef8``).
- ``--fast-check`` / ``--slow-check`` flags on the ``scrape`` command
  (``4a50ec0``); corresponding ``--last-page`` option (replacing
  ``--max-pages``) (``035dfae``).
- ``--dry-run`` flag on ``publish``: simulates the full GitHub PR flow without
  leaving visible side-effects (``9716ee5``).
- Player-identity validation step applied automatically during scraping
  (``d2e2d17``).
- ``--check-players`` flag on ``validate`` (``44e8621``).
- Coercions cache for player-name normalisation in the CLI (``2dbb4c7``).
- Player-identity validation step in the ``publish`` workflow (``8162d16``).
- ``start_page`` argument for resumable scraping (``544e03c``, ``763bda4``).
- Pre-commit hooks (ruff, mypy) wired into CI workflows (``6733d74``,
  ``25c874a``).
- Automated validation step after each scrape run (``888a146``, ``cec05a8``).
- GitHub workflows for feature-request reviews (``ecac5d1``).

Changed
-------
- Scraper refactored and enhanced: topic-icon detection, improved routing,
  better logging levels (``e239def``, ``e51093c``, ``f5e479f``).
- ``_check_calendar_winner`` refactored to return a tuple (``8f2a835``).
- Tests split into one file per CLI command (``6749ee5``); public helpers
  exposed; branch-name sanitisation logic updated (``71460e2``).
- Default YAML formatter switched to Ruff (``25c874a``).
- Pre-2020 tournaments filtered out of publish workflow (``19e5afe``).
- Dry-run report path and naming convention updated (``6acb492``).

Fixed
-----
- Field ordering restored for ``event_id``, ``vp_comment``,
  ``forum_post_url`` after accidental reordering (``76ae9d8``).
- ``event_url`` normalised to canonical form; ``event_id`` kept in sync
  (``2a7a069``).
- Crypt-card grouping: correct vampire version selected when a card exists in
  multiple groups (``a092569``).
- ADV/non-ADV enrichment handled separately (``b0c87ee``).
- Error subfolders searched when checking for duplicate ``event_id`` files
  (``3eda3b7``).
- Last-page handling in ``scrape`` command corrected (``e8a0292``).
- ``errors/`` directory skipped during publishing (``ebff336``).
- VTES title regex updated to match proper casing (``6e38beb``).
- Coercions output directory created before saving (``570af43``).
- JSON decode errors handled separately in ``fetch_event_date`` (``2aaf5a6``).
- CLI usage examples and Python API integration documentation fixed
  (``f08224a``).
- Scraping allowed to continue on non-fatal errors (``27d58d2``).
- ``vekn_number`` type coerced to integer throughout (``08a46b7``).

----

v0.2.0 — 2026-03-11
====================

Expanded validation pipeline, near-complete test coverage, and richer scraping
with clan/title parsing and pagination support.

Added
-----
- Extended YAML validation logic (required fields, cross-field coherence)
  (``8bd92eb``).
- Multi-word clan name and title parsing in crypt-line processing (``8f536d4``).
- Compact crypt-line format support (``787d9c6``).
- ``rescrape`` CLI subcommand to re-fetch decks from the ``errors/`` directory
  (``a5cc4f8``).
- Enhanced ``publish`` workflow: improved deck management and text reporting
  (``f6831c6``).
- Validation step for scraped decks added to the scrape workflow (``cec05a8``).
- Test coverage raised from 27 % to 96 % (``6d7f63f``).
- Topic-icon detection and routing in the scraper (``79b1b7d``).
- Pagination with ``start_page`` support (``544e03c``).
- Coercions cache for player validation (``2dbb4c7``).
- Player-identity validation in the ``publish`` workflow (``8162d16``).

Changed
-------
- Text output format for event data updated (``94b1871``).
- Logging levels changed from ``DEBUG`` to ``INFO`` for scraping actions
  (``e51093c``).
- Obsolete test file for tournament YAML processing removed (``d4a3c30``).

Fixed
-----
- Scraping continues on error (``27d58d2``).
- JSON decode errors in ``fetch_event_date`` handled separately (``2aaf5a6``).

----

v0.1.0 — 2026-03-09
====================

First working release.  Scrapes VTES tournament winning decks from the VEKN
forum, validates them, and publishes them as YAML files via a GitHub PR.

Added
-----
- Project initialised with ``pyproject.toml`` and package skeleton
  (``a5ed444``).
- Data models (``Tournament``, crypt/library cards) backed by Pydantic
  (``a5ed444``).
- HTML parser for VEKN forum tournament threads (``c52303e``, ``275b7fe``).
- YAML and TXT output serialisers for ``Tournament`` objects (``e2c0fc9``,
  ``fd60d47``).
- CLI with ``scrape``, ``parse``, and ``publish`` subcommands (``66328ce``).
- ``validate`` subcommand: checks YAML file integrity and moves errors
  (``569c84d``).
- ``fix-date`` subcommand: corrects tournament dates and validates date
  coherence (``667b623``).
- GitHub PR publisher for TWD decks and automated publishing workflow
  (``4538178``).
- GitHub Actions workflow for automated scraping (``cefbac4``).
- README with installation instructions and directory structure (``e7df89c``).
