"""
GitHub Pull Request publisher for TWD decks.

Forks GiottoVerducci/TWD into the gurchon-hall organisation (if not already
forked), closes any PRs/branches left over from previous runs, pushes new
deck files to a branch on the fork, and opens a **single** Pull Request back
into the upstream repository.

Authentication:
  Requires a GitHub Personal Access Token (PAT) with 'public_repo' scope,
  supplied as the GITHUB_TOKEN environment variable or passed explicitly.
  The token's user must have permission to create repositories in
  gurchon-hall.

API surface used (GitHub REST v3):
  - GET   /user                                         → authenticated user login
  - POST  /repos/{owner}/{repo}/forks                   → fork upstream repo into gurchon-hall
  - GET   /repos/{owner}/{repo}/git/refs/heads/{branch} → base SHA (upstream)
  - GET   /repos/{owner}/{repo}/contents/{path}         → check file existence (upstream)
  - GET   /repos/{owner}/{repo}/pulls                   → list stale open PRs from the fork
  - PATCH /repos/{owner}/{repo}/pulls/{number}          → close a stale PR
  - POST  /repos/{fork_owner}/{repo}/git/refs           → create branch on fork
  - PUT   /repos/{fork_owner}/{repo}/contents/{path}    → create/update file on fork
  - POST  /repos/{owner}/{repo}/pulls                   → open PR into upstream
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

from channel_ten.github import (
    close_pull_request,
    create_branch,
    delete_branch,
    ensure_fork,
    file_exists_on_branch,
    get_branch_sha,
    list_open_prs_from_fork,
    open_pull_request,
    push_files_to_branch,
)
from channel_ten.models import Tournament
from channel_ten.output import tournament_to_txt
from channel_ten.scraper._twda import TWDA_BRANCH, TWDA_DECKS_FOLDER

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class BatchPRResult:
    """Outcome of a single batch publish run."""

    pr_url: str | None = None
    """URL of the opened (or already-open) PR, None if nothing was published."""

    published: list[int | str] = field(default_factory=list[int | str])
    """event_ids successfully committed to the PR branch."""

    skipped: list[int | str] = field(default_factory=list[int | str])
    """event_ids already present on master — not included in the PR."""

    errors: list[tuple[int | str, str]] = field(default_factory=list[tuple[int | str, str]])
    """(event_id, error_message) pairs for decks that could not be committed."""

    skipped_all: bool = False
    """True when every tournament was already in the target repo (no PR created)."""

    dry_run: bool = False
    """True when this result comes from a dry-run (branch deleted, no PR opened)."""

    closed_prs: list[str] = field(default_factory=list[str])
    """HTML URLs of stale PRs from previous runs that were closed before this PR."""


def sanitize_branch_name(text: str) -> str:
    """Convert arbitrary text to a valid git branch name segment."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:50]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def publish_all_as_single_pr(
    tournaments: list[Tournament],
    token: str | None = None,
    branch_prefix: str = "twd/weekly-decks",
    delay: float = 1.0,
    dry_run: bool = False,
) -> BatchPRResult:
    """
    Publish all new tournaments in a **single** Pull Request against
    GiottoVerducci/TWD.

    Steps:
      1. Filter tournaments: skip any deck whose file already exists on master.
      2. If nothing is new, return early (BatchPRResult.skipped_all = True).
      3. Close any open PRs (and delete their branches) left over from
         previous runs, so only one PR is ever open at a time. Skipped
         entirely on dry_run.
      4. Create one branch named ``{branch_prefix}-{YYYY-MM-DD}`` off master.
      5. Commit each new deck's TXT file to that branch.
      6. Open one PR with a summary table of all included decks.
         (dry_run: skip PR creation and delete the branch instead)

    Args:
        tournaments: All Tournament objects scraped this run.
        token: GitHub PAT with *public_repo* (or *repo*) scope.
        branch_prefix: Prefix for the feature branch name.
        delay: Seconds to wait between consecutive GitHub API file commits.
        dry_run: When True, create branch and commit files to verify behaviour,
            then delete the branch instead of opening a PR.

    Returns:
        A BatchPRResult describing the outcome.
    """
    result = BatchPRResult(dry_run=dry_run)

    with httpx.Client(timeout=30) as client:
        # ── Step 0: ensure fork exists ───────────────────────────────────────
        try:
            fork_owner = ensure_fork(client, token)
        except httpx.HTTPStatusError as exc:
            for t in tournaments:
                result.errors.append((t.event_id or "unknown", f"Fork creation failed: {exc}"))
            return result

        # ── Step 1: filter out already-published decks ──────────────────────
        new_tournaments: list[Tournament] = []
        for t in tournaments:
            event_id = t.event_id or "unknown"
            file_path = f"{TWDA_DECKS_FOLDER}/{event_id}.txt"
            if file_exists_on_branch(client, file_path, TWDA_BRANCH, token):
                logger.debug("Deck %s already on master — skipping.", event_id)
                result.skipped.append(event_id)
            else:
                new_tournaments.append(t)

        # ── Step 2: early exit if nothing new ───────────────────────────────
        if not new_tournaments:
            result.skipped_all = True
            return result

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        branch = f"{branch_prefix}-{today}"

        # ── Step 3: close stale PRs/branches from previous runs ──────────────
        if not dry_run:
            try:
                stale_prs = list_open_prs_from_fork(client, fork_owner, token)
            except httpx.HTTPStatusError as exc:
                logger.warning("Could not list existing PRs for cleanup: %s", exc)
                stale_prs = []
            for pr in stale_prs:
                stale_branch = str(pr["branch"])
                if stale_branch == branch:
                    continue
                try:
                    close_pull_request(client, int(pr["number"]), token)
                    result.closed_prs.append(str(pr["html_url"]))
                    logger.info("Closed stale PR #%s: %s", pr["number"], pr["html_url"])
                except httpx.HTTPStatusError as exc:
                    logger.warning("Could not close PR #%s: %s", pr["number"], exc)
                if stale_branch:
                    delete_branch(client, stale_branch, token, owner=fork_owner)

        # ── Step 4: create one branch on the fork ───────────────────────────
        try:
            base_sha = get_branch_sha(client, TWDA_BRANCH, token)
            create_branch(client, branch, base_sha, token, owner=fork_owner)
        except httpx.HTTPStatusError as exc:
            for t in new_tournaments:
                result.errors.append((t.event_id or "unknown", f"Branch creation failed: {exc}"))
            return result

        # ── Step 5: commit each deck file to the fork ────────────────────────
        files = [
            (
                f"{TWDA_DECKS_FOLDER}/{t.event_id or 'unknown'}.txt",
                tournament_to_txt(t),
                f"feat: add TWD deck {t.event_id or 'unknown'} - {t.name}",
            )
            for t in new_tournaments
        ]
        path_to_id: dict[str, int | str] = {
            f"{TWDA_DECKS_FOLDER}/{t.event_id or 'unknown'}.txt": t.event_id or "unknown"
            for t in new_tournaments
        }
        committed_paths, commit_errors = push_files_to_branch(
            client, files, branch, fork_owner, token, delay
        )
        for path in committed_paths:
            result.published.append(path_to_id.get(path, path))
        for path, err in commit_errors:
            result.errors.append((path_to_id.get(path, path), err))

        # ── Step 6: open PR or (dry-run) delete the branch ───────────────────
        if not result.published:
            if dry_run:
                delete_branch(client, branch, token, owner=fork_owner)
            return result

        if dry_run:
            logger.info("Dry-run: deleting branch %r instead of opening a PR.", branch)
            delete_branch(client, branch, token, owner=fork_owner)
            return result

        pr_title = f"Add {len(result.published)} TWD deck(s) — {today}"

        pr_body_lines = [
            f"Automated weekly import of **{len(result.published)}** new "
            f"tournament winning deck(s) scraped from [vekn.net](https://www.vekn.net/forum/event-reports-and-twd).",
            "",
            "| Event ID | Event Name | Location | Date | Winner |",
            "| -------- | ---------- | -------- | ---- | ------ |",
        ]
        for t in new_tournaments:
            if (t.event_id or "unknown") in result.published:
                name_link = f"[{t.name}]({t.event_url})" if t.event_url else t.name
                pr_body_lines.append(
                    f"| {t.event_id} | {name_link} | {t.location} | {t.date_start} | {t.winner} |"
                )

        pr_body_lines += [
            "",
            (
                "_Automatically submitted by "
                "[Channel 10](https://github.com/gurchon-hall/channel-ten)._"
            ),
        ]

        try:
            pr_url = open_pull_request(
                client,
                branch,
                pr_title,
                "\n".join(pr_body_lines),
                token,
                fork_owner=fork_owner,
            )
            result.pr_url = pr_url
            logger.info("PR opened: %s", pr_url)
        except httpx.HTTPStatusError as exc:
            err = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            logger.error("Failed to open PR: %s", err)
            # published list is still populated so the caller can report progress

    return result
