"""Generic GitHub API helpers shared across channel-ten subcommands."""

import base64
import logging
import os
import time
from datetime import date

import httpx
from dotenv import load_dotenv

from channel_ten.scraper._twda import (
    TWDA_BRANCH,
    TWDA_DECKS_FOLDER,
    TWDA_OWNER,
    TWDA_REPO,
)

load_dotenv()

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
_GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")


def headers(token: str | None = None) -> dict[str, str]:
    """Build GitHub API request headers for *token* (falls back to $GITHUB_TOKEN)."""
    if not token:
        token = _GITHUB_TOKEN
    if not token:
        raise ValueError(
            "GitHub token not provided. "
            "Set the GITHUB_TOKEN environment variable or pass it explicitly."
        )
    return {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {token}",
    }


def get_authenticated_user(client: httpx.Client, token: str | None = None) -> str:
    """Return the login of the token's owner via GET /user."""
    resp = client.get(f"{GITHUB_API}/user", headers=headers(token))
    resp.raise_for_status()
    return str(resp.json()["login"])


def post_twda_issue(
    client: httpx.Client,
    failures: list[tuple[int, str]],
    token: str | None = None,
) -> str:
    """Open a GitHub issue on GiottoVerducci/TWD listing import failures.

    Each entry in *failures* is ``(event_id, reason)``.  Returns the URL of
    the created issue.  Raises ``httpx.HTTPStatusError`` on API errors and
    ``ValueError`` when no token is available.
    """
    today = date.today().isoformat()
    file_base = (
        f"https://github.com/{TWDA_OWNER}/{TWDA_REPO}/blob/{TWDA_BRANCH}/{TWDA_DECKS_FOLDER}"
    )
    rows = "\n".join(f"| [{eid}]({file_base}/{eid}.txt) | `{reason}` |" for eid, reason in failures)
    body = (
        f"The following events from the archive could not be imported by "
        f"[channel-ten](https://github.com/gurchon-hall/channel-ten) on {today}:\n\n"
        f"| Event | Reason |\n"
        f"|-------|--------|\n"
        f"{rows}\n"
    )
    url = f"{GITHUB_API}/repos/{TWDA_OWNER}/{TWDA_REPO}/issues"
    resp = client.post(
        url,
        headers=headers(token),
        json={"title": f"Import failures — {today}", "body": body},
    )
    resp.raise_for_status()
    issue_url: str = resp.json()["html_url"]
    logger.info("Issue created: %s", issue_url)
    return issue_url


# ---------------------------------------------------------------------------
# Low-level GitHub REST helpers for the TWD repo
# ---------------------------------------------------------------------------


def ensure_fork(client: httpx.Client, token: str | None = None) -> str:
    """Fork GiottoVerducci/TWD if needed and return the fork owner's login.

    POST /forks is idempotent — GitHub returns the existing fork when one
    already exists.  Fork creation is asynchronous, so we poll until the
    fork's API endpoint responds 200 (up to 10 seconds).
    """
    fork_owner = get_authenticated_user(client, token)
    resp = client.post(
        f"{GITHUB_API}/repos/{TWDA_OWNER}/{TWDA_REPO}/forks",
        headers=headers(token),
    )
    resp.raise_for_status()
    logger.debug("Fork ensured for %s/%s under %s.", TWDA_OWNER, TWDA_REPO, fork_owner)
    fork_url = f"{GITHUB_API}/repos/{fork_owner}/{TWDA_REPO}"
    for _ in range(10):
        if client.get(fork_url, headers=headers(token)).status_code == 200:
            break
        time.sleep(1)
    return fork_owner


def get_branch_sha(
    client: httpx.Client,
    branch: str,
    token: str | None = None,
) -> str:
    """Return the current HEAD commit SHA of *branch*."""
    url = f"{GITHUB_API}/repos/{TWDA_OWNER}/{TWDA_REPO}/git/refs/heads/{branch}"
    resp = client.get(url, headers=headers(token))
    resp.raise_for_status()
    return str(resp.json()["object"]["sha"])


def create_branch(
    client: httpx.Client,
    branch: str,
    sha: str,
    token: str | None = None,
    owner: str = TWDA_OWNER,
) -> None:
    """Create a new git ref (branch) pointing at *sha* (idempotent)."""
    url = f"{GITHUB_API}/repos/{owner}/{TWDA_REPO}/git/refs"
    resp = client.post(
        url,
        headers=headers(token),
        json={"ref": f"refs/heads/{branch}", "sha": sha},
    )
    if resp.status_code == 422:
        # Branch already exists — reuse it
        logger.debug("Branch %r already exists, reusing it.", branch)
        return
    resp.raise_for_status()


def file_exists_on_branch(
    client: httpx.Client,
    path: str,
    branch: str,
    token: str | None = None,
) -> bool:
    """Return True if *path* exists on *branch* in the target repo."""
    url = f"{GITHUB_API}/repos/{TWDA_OWNER}/{TWDA_REPO}/contents/{path}"
    resp = client.get(url, headers=headers(token), params={"ref": branch})
    return resp.status_code == 200


def put_file(
    client: httpx.Client,
    path: str,
    content: str,
    branch: str,
    commit_message: str,
    token: str | None = None,
    owner: str = TWDA_OWNER,
) -> None:
    """Create or update a file on *branch* via the Contents API."""
    url = f"{GITHUB_API}/repos/{owner}/{TWDA_REPO}/contents/{path}"
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")

    body: dict[str, str] = {
        "message": commit_message,
        "content": encoded,
        "branch": branch,
    }

    # If the file already exists on this branch we must supply its current SHA
    resp = client.get(url, headers=headers(token), params={"ref": branch})
    if resp.status_code == 200:
        body["sha"] = str(resp.json()["sha"])

    resp = client.put(url, headers=headers(token), json=body)
    resp.raise_for_status()


def open_pull_request(
    client: httpx.Client,
    head_branch: str,
    title: str,
    body: str,
    token: str | None = None,
    fork_owner: str = TWDA_OWNER,
) -> str:
    """Open a PR from *fork_owner*:*head_branch* into upstream and return its HTML URL."""
    url = f"{GITHUB_API}/repos/{TWDA_OWNER}/{TWDA_REPO}/pulls"
    head = f"{fork_owner}:{head_branch}"
    resp = client.post(
        url,
        headers=headers(token),
        json={
            "title": title,
            "head": head,
            "base": TWDA_BRANCH,
            "body": body,
        },
    )
    if resp.status_code == 422:
        data = resp.json()
        errors = data.get("errors", [])
        for err in errors:
            if "pull request already exists" in str(err.get("message", "")).lower():
                existing = find_existing_pr(client, head_branch, token, fork_owner)
                if existing:
                    logger.debug("PR already open for branch %r: %s", head_branch, existing)
                    return existing
    resp.raise_for_status()
    return str(resp.json()["html_url"])


def find_existing_pr(
    client: httpx.Client,
    head_branch: str,
    token: str | None = None,
    fork_owner: str = TWDA_OWNER,
) -> str | None:
    """Find an already-open PR for *fork_owner*:*head_branch* and return its HTML URL."""
    url = f"{GITHUB_API}/repos/{TWDA_OWNER}/{TWDA_REPO}/pulls"
    resp = client.get(
        url,
        headers=headers(token),
        params={"state": "open", "head": f"{fork_owner}:{head_branch}"},
    )
    if resp.status_code == 200 and resp.json():
        return str(resp.json()[0]["html_url"])
    return None


def delete_branch(
    client: httpx.Client,
    branch: str,
    token: str | None = None,
    owner: str = TWDA_OWNER,
) -> None:
    """Delete a git ref (branch) on *owner*'s fork (best-effort)."""
    url = f"{GITHUB_API}/repos/{owner}/{TWDA_REPO}/git/refs/heads/{branch}"
    resp = client.delete(url, headers=headers(token))
    if resp.status_code == 204:
        logger.debug("Deleted branch %r on %s.", branch, owner)
    else:
        logger.warning(
            "Could not delete branch %r on %s: HTTP %s",
            branch,
            owner,
            resp.status_code,
        )


def push_files_to_branch(
    client: httpx.Client,
    files: list[tuple[str, str, str]],
    branch: str,
    fork_owner: str,
    token: str | None = None,
    delay: float = 1.0,
) -> tuple[list[str], list[tuple[str, str]]]:
    """Commit *files* to *branch* on *fork_owner*'s fork of TWDA_REPO.

    Each entry in *files* is ``(path, content, commit_message)``.  Returns
    ``(committed_paths, [(failed_path, error_message), ...])``.
    """
    committed: list[str] = []
    errors: list[tuple[str, str]] = []
    for i, (path, content, commit_msg) in enumerate(files):
        if i > 0:
            time.sleep(delay)
        try:
            put_file(client, path, content, branch, commit_msg, token, owner=fork_owner)
            committed.append(path)
            logger.debug("Committed %s to branch %s", path, branch)
        except httpx.HTTPStatusError as exc:
            err = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            errors.append((path, err))
            logger.error("Failed to commit %s: %s", path, err)
        except Exception as exc:
            errors.append((path, str(exc)))
            logger.error("Failed to commit %s: %s", path, exc)
    return committed, errors
