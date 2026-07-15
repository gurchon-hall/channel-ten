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

Unreleased
==========

Added
-----

- New ``channel-ten tda-scrape`` subcommand and monthly
  ``.github/workflows/tda-scrape.yml`` workflow: scrapes TDA (Tournament Deck
  Archive — every participant's deck, not just the winner's) from
  `smeea/vdb <https://github.com/smeea/vdb>`_'s
  ``frontend/public/tournaments/*.zip`` archives, the only available source
  for full tournament decklists. Writes one YAML file per deck to
  ``eternal-vigilance/tda/YYYY/MM/<event_id>/<author_id>.yaml``, alongside
  (not merged with) the existing TWD tree. New modules:
  ``models.TdaDeck``, ``parser/_tda.py``, ``scraper/_tda.py``,
  ``pipeline_tda.py``, ``output/tda_yaml.py``,
  ``validator.tda_deck_errors``. See ``docs/tda_pipeline.md`` for the source
  archive format and design rationale. New dependency: ``openpyxl`` (reads
  the archive's ``archon.xlsx`` tournament report).
- ``scraper.fetch_player_by_id``: resolves a player's canonical name from their
  VEKN member number via ``https://www.vekn.net/player-registry/player/<id>``
  (same ``componentheading`` convention as ``fetch_event_name``). Used by
  ``pipeline_tda.resolve_author`` so a numeric TDA ``Author:`` value (the
  common case) produces a human-readable ``deck.created_by``/``author``
  instead of the bare VEKN number.

Changed
-------

- ``channel-ten parse``: ``--twds-dir`` now defaults to ``twds/``, matching
  every other subcommand — previously it defaulted to ``None`` and printed to
  stdout. Pass the new ``--stdout`` flag to get the old print-to-stdout
  behavior explicitly.
- The ``gurchon-hall`` fork of GiottoVerducci/TWD was renamed from ``TWD`` to
  ``twd-fork``, matching the ``-fork`` suffix convention already used by
  ``krcg-fork`` and ``vdb-fork``. ``github.py`` now tracks the fork's name via
  a new ``FORK_REPO`` constant, decoupled from ``TWDA_REPO`` (upstream's own
  name, which never changes) — ``create_branch``, ``put_file``, and
  ``delete_branch`` take an explicit ``repo=`` parameter for this instead of
  assuming the fork shares upstream's name.

Fixed
-----

- ``scraper/_vekn.py`` (``fetch_event_name``): the calendar name-lookup only tried
  JSON-LD structured data and ``<h1>``, but VEKN's event-calendar pages (Joomla/JEvents)
  actually render the title in ``<div class="componentheading">`` — neither JSON-LD nor
  ``<h1>`` are present on most event pages. This made ``fetch_event_name`` fail almost
  universally in production (confirmed via a live ``scrape`` run — nearly every event
  logged ``"Could not extract event title"``), which meant the new ``unconfirmed_name``
  check added above was firing on nearly every scraped tournament instead of only the
  rare mis-parse case it was meant to catch. Added ``componentheading`` as a second
  strategy, tried before the ``<h1>`` fallback.
- ``parser/_helpers.py`` (``LineHelpers._repair_mojibake``) and ``_krcg_helper.py``
  (``get_crypt_card``, ``get_library_card_type``): three ``except`` clauses used the
  Python 2 multi-exception form (``except FooError, BarError:``), a syntax error under
  Python 3 that made the entire package — and therefore every CLI subcommand and the
  full test suite — fail to import.
- ``parser/_header.py`` (``parse_header_lenient``): the venue/location was
  assumed to always be a single line, so multi-line venues (e.g. "Venue
  Name" on one line, "City, Country" on the next — common on the forum)
  pushed every following field one slot out of place, feeding the location's
  continuation line into ``date_start`` and raising a confusing
  ``Cannot parse date`` error. The parser now scans for the line that
  actually looks like a date (``parser/_helpers.py::looks_like_date``) and
  joins everything before it into ``location``, regardless of how many
  lines the venue spans. This was silently dropping a large fraction of
  scraped tournaments (e.g. all four "Week of Nightmares"/Origins posts in
  a single scrape run).
- ``README.md``: the CLI reference was restructured into one argument table
  per subcommand and was missing several real flags — ``--delay`` on
  ``scrape``/``import``/``publish``, the explicit ``--github-token`` flag on
  ``import``/``publish``, ``--publish-dir`` on ``publish``, and ``--overwrite``
  on ``parse``. Also corrected a wrong claim that ``import --limit`` requires
  a GitHub token — only ``--create-issue`` does; ``--github-token`` merely
  raises the deck-listing rate limit.
- ``pipeline.py`` (``scrape``/``import``): a first-scrape deck whose name the VEKN event
  calendar could not confirm (``fetch_event_name`` returns ``None``) was published
  silently with whatever the forum-post parser produced — including a poster's preamble
  note mistaken for the tournament name. ``_check_calendar_name`` now returns
  ``tuple[Tournament, bool]`` (mirroring ``_check_calendar_winner``), and
  ``process_tournament`` appends a new ``unconfirmed_name`` error when the calendar has no
  name data, routing the deck to ``errors/unconfirmed_name/`` for review instead.
- ``cli/validate.py``: the weekly re-validation pass rescraped the forum post
  (step 1) but never re-checked the tournament name against the VEKN event
  calendar, so a name mis-parsed from the original forum post (e.g. a
  poster's preamble note swallowed as the tournament name, shifting every
  following header line by one) stayed wrong forever — rescraping just
  reproduced the same mis-parse from the same source text. Added
  ``_check_and_update_name``, mirroring the existing ``_check_and_update_winner``
  calendar check, so ``validate`` now overrides the name with the canonical
  one from the event calendar page (``fetch_event_name``), matching what
  ``scrape``/``import`` already do via ``pipeline._check_calendar_name``.
- ``github.py`` (``ensure_fork``): every ``publish`` run called
  ``POST /forks`` unconditionally, trusting GitHub to treat it as a no-op
  when ``gurchon-hall/TWD`` already existed. That assumption doesn't always
  hold — if a same-named repo exists under the org for any reason other than
  a clean prior fork, GitHub creates a second, differently-named fork
  instead of erroring, which is how ``gurchon-hall`` ended up with two forks
  of GiottoVerducci/TWD. ``ensure_fork`` now checks whether the fork already
  exists first and only calls ``POST /forks`` when it's missing.

----

v0.9.1 — 2026-07-01
====================

CI hotfix: the ``publish`` and ``validate`` workflows were failing with
``command not found`` (missing ``uv run`` wrapper), and ``scrape`` /
``twda-reimport`` were failing with "unrecognized arguments" (stale
``--output-dir`` flag left over from the v0.9.0 rename).

Fixed
-----

- ``.github/workflows/publish.yml`` and ``validate.yml``: the ``channel-ten
  publish`` / ``channel-ten validate`` invocations ran the bare command
  instead of ``uv run --project ./channel-ten channel-ten ...``.  ``uv sync``
  only creates the venv at ``channel-ten/.venv``; without the wrapper the
  ``channel-ten`` binary is not on ``PATH`` and the step fails with
  ``command not found``.
- ``.github/workflows/scrape.yml`` and ``twda-reimport.yml``: still passed
  the removed ``--output-dir`` flag instead of ``--twds-dir`` (see the
  v0.9.0 flag rename), which would fail with "unrecognized arguments" on
  their next scheduled run.

----

v0.9.0 — 2026-07-01
====================

Card ID support, event exclusion from validation, ``ANY``-grouping crypt
parsing, rotating log files, a one-time card-rename migration script, a
module-responsibility refactor separating pipeline and GitHub API logic into
dedicated modules, the ``--twds-dir`` flag rename, ``--force-date`` and
``--errors-only`` validate flags, a ``fetch_event_winner`` VEKN ID fix, and a
publish-workflow hardening pass (forks now land in ``gurchon-hall``; stale
PRs and branches are closed before a new one is opened).
Card ID feature first implemented by
`@Zavierazo <https://github.com/Zavierazo>`_; refactored here due to the
growing version gap since `PR #14 <https://github.com/gurchon-hall/channel-ten/pull/14>`_.

Added
-----

- ``channel_ten/pipeline.py``: new module owning the shared scraping pipeline.
  Contains ``RouteCounters`` (dataclass), ``process_tournament``,
  ``route_tournament``, and the step helpers ``_check_calendar_name``,
  ``_check_calendar_winner``, ``_lookup_player``, ``_enrich_with_krcg``,
  ``_validate_content``.  Previously this code lived in ``cli/scrape.py``,
  which violated the rule that CLI modules must not act as libraries for other
  CLI modules (``cli/reimport.py`` imported from it).
- ``channel_ten/github.py``: new module owning all GitHub REST API logic.
  Consolidates generic helpers (``headers``, ``get_authenticated_user``), TWDA
  low-level helpers previously scattered in ``publisher.py``
  (``ensure_fork``, ``get_branch_sha``, ``create_branch``,
  ``file_exists_on_branch``, ``put_file``, ``open_pull_request``,
  ``find_existing_pr``, ``delete_branch``), the batch file-commit loop
  ``push_files_to_branch``, and ``post_twda_issue`` (previously in
  ``publisher.py``).
- ``reorder_tournament_dict`` added as a public function in
  ``channel_ten/output/yaml.py`` (moved from the private
  ``_reorder_tournament_dict`` in ``cli/validate.py``, which was the wrong
  module for output-formatting logic).
- ``list_open_prs_from_fork`` and ``close_pull_request`` in
  ``channel_ten/github.py``: used by ``publish_all_as_single_pr`` to close
  stale PRs (and delete their branches) left over from previous publish runs
  before opening a new one.

Changed
-------

- ``--output-dir`` / ``-o`` flag renamed to ``--twds-dir`` on the ``scrape``,
  ``parse``, and ``reimport`` subcommands, and on
  ``scripts/single_url_full_pipeline.py``.  The ``dest`` attribute is likewise
  renamed from ``output_dir`` to ``twds_dir`` for consistency.
- ``cli/scrape.py`` is now a pure CLI entry point: argument registration and
  ``run()`` wiring only.  All pipeline helpers moved to ``channel_ten/pipeline.py``.
- ``cli/reimport.py`` now imports ``RouteCounters``, ``process_tournament``,
  and ``route_tournament`` from ``channel_ten.pipeline`` (was ``cli.scrape``);
  imports ``post_twda_issue`` from ``channel_ten.github`` (was ``publisher``).
- ``cli/validate.py`` now imports ``reorder_tournament_dict`` from
  ``channel_ten.output.yaml`` (was a private local function).
- ``publisher.py`` reduced to domain orchestration: ``BatchPRResult``,
  ``sanitize_branch_name``, and ``publish_all_as_single_pr`` only.  All
  low-level GitHub REST calls delegated to ``channel_ten.github``.
- ``ensure_fork`` (``channel_ten/github.py``) now forks ``GiottoVerducci/TWD``
  into the ``gurchon-hall`` organisation via the ``organization`` parameter on
  ``POST /forks``, instead of the token's personal account.  New
  ``FORK_OWNER`` constant.  The token's user must have repo-creation
  permission in ``gurchon-hall``.
- ``publish_all_as_single_pr`` now closes every open upstream PR headed from
  the fork and deletes its branch before creating this run's branch (skipping
  the branch matching today's run), so at most one TWD PR is open at a time.
  Skipped entirely on ``--dry-run``.  New ``BatchPRResult.closed_prs`` field
  records the closed PR URLs, surfaced in the publish Markdown report.

Added (card ID / validation, continued)
----------------------------------------

- ``--force-date`` flag on the ``validate`` subcommand: when set, ``date_start``
  in each YAML file is overwritten with the official date fetched from the VEKN
  event calendar when the two differ.  Resolves ``incoherent_date`` errors
  caused by a wrong date in the source file (e.g. copy-paste from a different
  event).  Combines correctly with ``--dry-run``, which logs the pending change
  without writing to disk.  The calendar date is fetched even in dry-run mode
  when this flag is active so the report is complete.
- ``--errors-only`` flag on the ``validate`` subcommand: when set, only files
  under ``twds/errors/`` are processed (instead of the full published tree or
  the most-recent-25 fast path).  Useful for quickly checking whether
  previously failing decks can be recovered after a data fix.  Respects
  ``skip_events.txt`` and ``--dry-run`` like the normal ``validate`` path.
- ``validate`` now skips files whose ``forum_post_url`` contains
  ``/event-calendar/``: these are TWDA-imported events that have no forum
  thread (the event-calendar URL is used as a fallback source reference).
  Attempting to rescrape them produced a spurious ``No div.kmsg found``
  warning.  They are now silently skipped at ``DEBUG`` level; the ``import``
  subcommand remains the correct tool to refresh them from the archive.

- ``Card`` base Pydantic model in ``models.py`` with ``count``, ``name``,
  ``id``, and ``comment`` fields.  ``CryptCard`` and ``LibraryCard`` now inherit
  from it, eliminating the duplicated ``comment`` field.
- ``id: int | None`` field on every card, defaulting to ``None``.  Populated
  from the krcg database during enrichment; absent from YAML when ``None``
  (filtered by ``_filter_none``).  Never appears in TXT output.
- ``enrich_card_ids(deck)`` in ``validator.py``: sets ``id`` for library cards
  (and any crypt card not already attributed by ``enrich_crypt_cards()``).
  Skips cards whose ``id`` is already set — once attributed an ID is never
  overwritten.
- ``missing_card_id_errors(deck)`` in ``validator.py``: returns
  ``["missing_card_id"]`` if any crypt or library card still has ``id=None``
  after enrichment.  Returns ``[]`` when krcg is unavailable (no false positives
  offline).
- ``missing_card_id`` added to the ``error_types()`` validation pipeline in
  ``validator.py``; triggered when any card in the deck still has ``id=None``
  after enrichment.
- ``scripts/migrate_card_names.py``: one-time migration script that walks an
  eternal-vigilance checkout, applies ``OLD_TO_NEW_NAME`` renames, re-enriches
  decks, and writes YAML back in-place.  Includes
  ``"Mind Rape" → "Puppet Master"`` as the first entry.  Extend the dict
  manually as future VTES card renames are announced.
- **Event exclusion from validation**: the ``validate`` command now reads an
  optional ``skip_events.txt`` file at the root of the eternal-vigilance
  checkout (sibling of ``twds/``).  Any event ID listed there is silently
  skipped — no rescraping, no re-enrichment, no overwrite.  Intended for
  tournament posts that mix the TWD with contestants' decks and require a
  permanent manual edit.  File format: one integer event ID per line; lines
  starting with ``#`` are comments.
- **Rotating log files**: ``setup_logging()`` in ``_logger.py`` now attaches a
  ``RotatingFileHandler`` to the ``channel_ten`` logger in addition to the Rich
  console handler.  Logs are written to ``.log/channel_ten.log`` at ``DEBUG``
  level with up to 5 × 100 MB backup files.  The ``.log/`` directory is created
  automatically and added to ``.gitignore``.
- ``scripts/test_id_and_any.py`` rewritten to run the full scraping pipeline
  (scrape → parse → enrich → validate → route) for a single forum URL and save
  the resulting YAML under ``twds/``.  Accepts the URL as an optional positional
  argument; defaults to a known Wroclaw 2023 thread.

Changed
-------

- ``enrich_crypt_cards()`` now sets ``card.id`` from the krcg ID of the best
  grouping version selected, using the same ``if card.id is None`` guard.
- ``get_all_vamp_variants()`` in ``_krcg_helper.py`` now includes
  ``id=int(candidate.id)`` in every returned ``CryptCard`` so that the correct
  grouping-specific ID flows through enrichment.
- ``_ENRICH_FIELDS`` in ``validator.py`` gains an explanatory comment: ``id`` is
  excluded because fields in that set are always overwritten on re-enrichment,
  whereas ``id`` must never be cleared once set.
- Crypt-line regex in ``parser/_helpers.py``: disciplines group changed from
  ``+`` (one-or-more) to ``*`` (zero-or-more) so that crypt cards with no
  printed disciplines are accepted.
- Grouping field in the crypt-line regex now accepts the literal token ``ANY``
  (case-insensitive) in addition to an integer; parsed as the string ``"ANY"``
  on ``CryptCard.grouping``.
- CI workflows ``scrape.yml`` and ``twda-reimport.yml`` updated to invoke the
  CLI via ``uv run --project`` instead of a bare ``uv run``, ensuring the
  correct project environment is resolved when the working directory is a
  sibling checkout.
- Crypt-line regex in ``parser/_helpers.py``: count prefix now accepts all
  three quantity spellings seen on the forum — ``Nx`` (e.g. ``3x``), ``N x``
  (space before the ``x``), and a bare ``N`` with no ``x`` at all.  The
  grouping separator now also tolerates a space after the colon (``Clan: N``).
- ``parser/_deck.py`` crypt loop: when a line fails to parse and the next
  non-empty line looks like a bare ``Clan:N`` continuation, the two lines are
  joined before retrying.  This handles forum posts where the clan name wraps
  to a new line.

Fixed
-----

- ``fetch_event_winner`` now returns ``tuple[str, int | None] | None`` instead of
  ``str | None``.  The VEKN ID is extracted from the ``/event-calendar/player/<id>``
  href in the winner's standings-table cell, so the player-registry lookup
  (``fetch_player``) is bypassed when the ID is already available.  This prevents
  ``unconfirmed_winner`` from being set for events whose standings are published but
  whose winner name is ambiguous in the VEKN registry (e.g. two registered players
  sharing the same name).
- ``unconfirmed_winner`` is now set only when the event calendar page has no standings
  table at all.  Previously it was also triggered when ``fetch_player`` returned
  ``None`` due to name ambiguity, even though the winner's identity was known from
  the standings link.
- ``fetch_event_name`` warning log message changed from
  ``"Could not extract name from event page"`` to
  ``"Could not extract event title from event page"`` to avoid confusion with player
  name extraction.

----

v0.8.0 — 2026-06-29
====================

Toolchain migration: pip/setuptools → uv, mypy → ty, and logging-pipeline
improvements.

Added
-----

- ``AGENTS.md`` added at the repository root: guidelines for automated agents
  (CI, coding assistants, PR review bots) covering repository map, code style,
  testing, and workflow conventions.
- ``uv.lock`` lockfile added; all dependency resolutions are now reproducible.

Changed
-------

- Build backend switched from **setuptools** to **hatchling**; the
  ``[tool.setuptools.packages.find]`` section is removed (hatchling
  auto-discovers ``channel_ten``).
- Dev dependencies moved from ``[project.optional-dependencies]`` to
  ``[dependency-groups]`` (PEP 735) so they are not published with the package.
- Package manager migrated from **pip** to **uv** (``python-preference =
  "only-managed"`` in ``[tool.uv]``).  All five CI workflows updated to use
  ``astral-sh/setup-uv@v4`` and ``uv sync --group dev``.
- Type checker migrated from **mypy** to **ty**; ``[tool.mypy]`` configuration
  removed; ``[tool.ty]`` section added; ty pre-commit hook added before pytest.
- Pre-commit local hooks updated to invoke tools via ``uv run`` instead of
  ``python -m``.
- All CLI user-facing output migrated from ``rich.Console.print()`` to the
  standard ``logging`` hierarchy.  Progress, status, and error messages now
  flow through ``logger.*`` calls in each subcommand module.
- ``setup_logging()`` default level for ``channel_ten`` raised from ``ERROR``
  to ``INFO``; progress messages (written, skipped, failed, PR URL, …) are
  now visible by default without ``--verbose``.
- ``--verbose`` continues to enable ``DEBUG`` logging; card-enrichment detail
  (crypt enriched, sections fixed, names canonicalized) is demoted to
  ``DEBUG`` so it does not appear in normal runs.
- ``reconfigure_windows_stdio()`` removed from ``cli/_common.py`` and the
  ``main()`` entry point — it existed solely to work around a Rich
  ``Console`` Windows encoding issue that no longer applies.
- ``validate`` subcommand now correctly calls ``setup_logging(args.verbose)``
  at the start of ``run()``; the ``--verbose`` flag was previously registered
  but never connected to logging configuration.
- ``MIN_PLAYERS`` threshold default is changed to 10 after inquiring TWDA minimum
  requirement: 10 players and no multi-deck. Second condition is  currently not
  supported within the application but collateral should be minimum.

Fixed
-----

- ``validate`` command now includes ``errors/`` when scanning YAML files, so
  previously failing tournaments are re-checked on every run (not only with
  ``--full-validation``).
- ``validate`` command now moves recovered tournaments (files in ``errors/``
  that pass all checks) back to their canonical ``twds/YYYY/MM/`` location
  instead of leaving them stranded in the error directory.

----

v0.7.0 — 2026-06-29
====================

Full removal of TypedDict usage in favour of Pydantic models, logging
configuration centralised to ``_logger.py``, and code-style alignment with
CLAUDE.md conventions.

Added
-----
- ``channel_ten/_logger.py``: dedicated logging-configuration module
  containing ``setup_logging(verbose)``.  Modules no longer call
  ``logging.basicConfig`` themselves.

Changed
-------
- All five TypedDicts (``Crypt_Card_Dict``, ``Library_Card_Dict``,
  ``Library_Section_Dict``, ``Deck_Dict``, ``Tournament_Dict``) removed from
  ``models.py``.  Enrichment and section-fix functions now accept and mutate
  ``Deck`` / ``CryptCard`` / ``LibraryCard`` / ``LibrarySection`` Pydantic
  models directly.
- ``error_types()`` parameter type narrowed from ``Tournament_Dict`` to
  ``dict[str, Any]``, keeping raw-dict access for pre-validation YAML data.
- ``get_all_vamp_variants()`` return type changed from
  ``list[Crypt_Card_Dict]`` to ``list[CryptCard]``; entry construction uses
  ``CryptCard(...)`` instead of a plain dict literal.
- ``serialize_tournament()`` in ``cli/scrape.py`` simplified to
  ``tournament.model_dump(exclude_none=True)``; the intermediate
  ``_to_serializable`` helper removed.
- ``_enrich_with_krcg()`` in ``cli/scrape.py`` now mutates ``tournament.deck``
  in-place and returns the same object (no copy-on-return).
- ``setup_logging`` moved from ``cli/_common.py`` to ``channel_ten/_logger``;
  all CLI subcommands (``scrape``, ``parse``, ``publish``, ``reimport``) and
  tests updated to import from the new location.
- Logger names corrected: ``_logger`` → ``logger`` in ``_krcg_helper.py`` and
  ``validator.py`` per CLAUDE.md conventions.
- All imports moved to module top; no function-body imports remain.
- ``_iter_published_yaml`` annotated with ``-> Iterator[Path]``.

Fixed
-----
- Corrupted duplicate block in ``error_types()``'s library-count consistency
  check (leftover from an incomplete edit).
- ``no-any-return`` mypy errors in ``_krcg_helper.py``; ``card.printed_name``
  (typed ``Any`` from krcg's optional dependency) wrapped in ``str()``.
- Variable-reuse type conflict in ``canonicalize_card_names``; library-card
  loop renamed to ``lib_card``.

----

v0.6.0 — 2026-06-29
====================

Compatibility with krcg 5.0, path-data support for V5 Sabbat vampires, and
configurable player-count thresholds.

Added
-----
- Vampire path data (V5 Sabbat) enrichment for crypt cards: ``path`` field
  populated from krcg, included in YAML output and text reports.
- Configurable minimum-player threshold via the ``MIN_PLAYERS`` environment
  variable for validation checks.

Changed
-------
- Upgraded krcg dependency to **5.0** (``krcg>=5.0,<6.0``).  All internal
  usages updated: ``load()`` replaces the ``VTES`` singleton, ``CardDict``
  replaces ``VTES.get()``, attribute names aligned to the new model
  (``kind``, ``advanced``, ``clan``, ``printed_name``, ``group`` as StrEnum).
- ``TYPE_ORDER`` is now defined locally in ``_krcg_helper``; krcg 5.0 removed
  it from ``krcg.config``.
- i18n name resolution now builds a ``_i18n_lookup`` dict by iterating all
  cards once; ``VTES.load_from_vekn()`` (removed in krcg 5.0) is no longer
  called.

Fixed
-----
- CI failures caused by krcg 5.0 being installed via ``allow-prereleases:
  true`` in the GitHub Actions workflow while no upper bound was set on the
  krcg dependency.
- Section-ordering test failures caused by ``TYPE_ORDER`` being silently empty
  when the krcg 5.0 import failed.

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
