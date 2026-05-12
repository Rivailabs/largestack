"""GitHub integration — list issues, create issues, fetch PR details.

Auth: env var ``LARGESTACK_GITHUB_TOKEN`` (a Personal Access Token with
``repo`` scope, or a fine-grained token with ``Issues: read/write``
and ``Pull requests: read``).

Hits the GitHub REST API directly — no github / PyGithub dependency.
"""
from __future__ import annotations
import logging
import os

import httpx

from largestack._core.tools import tool

log = logging.getLogger("largestack.github")
_GH_API = "https://api.github.com"


def _headers() -> dict | None:
    tok = os.environ.get("LARGESTACK_GITHUB_TOKEN", "").strip()
    if not tok:
        return None
    return {
        "Authorization": f"Bearer {tok}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _validate_repo(repo: str) -> str | None:
    """Returns error string if repo is malformed, else None."""
    if not isinstance(repo, str) or "/" not in repo:
        return f"Invalid repo {repo!r} — expected 'owner/name'."
    if len(repo) > 100:
        return "Repo name too long."
    return None


@tool(timeout=15)
async def github_list_issues(repo: str, state: str = "open", limit: int = 20) -> str:
    """List GitHub issues in a repo.

    Args:
        repo: ``owner/name``, e.g. ``"anthropics/anthropic-sdk-python"``.
        state: ``open`` (default), ``closed``, or ``all``.
        limit: Max issues to return (1-100, default 20).

    Returns:
        Newline-separated ``#NUM  TITLE`` lines, or error string.
    """
    headers = _headers()
    if not headers:
        return "Error: LARGESTACK_GITHUB_TOKEN env var not set."
    err = _validate_repo(repo)
    if err:
        return f"Error: {err}"
    if state not in ("open", "closed", "all"):
        return f"Error: state must be open/closed/all, got {state!r}"

    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            f"{_GH_API}/repos/{repo}/issues",
            headers=headers,
            params={"state": state, "per_page": max(1, min(int(limit), 100))},
        )
    if r.status_code == 404:
        return f"Repo {repo} not found or token lacks access."
    if r.status_code >= 400:
        return f"GitHub API error: HTTP {r.status_code}: {r.text[:200]}"
    try:
        items = r.json()
    except Exception:
        return "GitHub API returned non-JSON."
    if not items:
        return f"No {state} issues in {repo}."
    # Filter out PRs (GitHub returns them in issues endpoint with pull_request key)
    issues_only = [i for i in items if "pull_request" not in i]
    if not issues_only:
        return f"No issues (only PRs) in {repo}."
    return "\n".join(f"#{i['number']}  {i['title']}" for i in issues_only)


@tool(timeout=15)
async def github_create_issue(
    repo: str, title: str, body: str = "", labels: str = ""
) -> str:
    """Create a new issue.

    Args:
        repo: ``owner/name``.
        title: Issue title.
        body: Markdown body (optional).
        labels: Comma-separated label names (optional).

    Returns:
        ``#NUM  url`` of the created issue, or error string.
    """
    headers = _headers()
    if not headers:
        return "Error: LARGESTACK_GITHUB_TOKEN env var not set."
    err = _validate_repo(repo)
    if err:
        return f"Error: {err}"
    if not title:
        return "Error: title is required."

    payload: dict = {"title": title}
    if body:
        payload["body"] = body
    if labels:
        payload["labels"] = [l.strip() for l in labels.split(",") if l.strip()]

    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(
            f"{_GH_API}/repos/{repo}/issues",
            headers=headers,
            json=payload,
        )
    if r.status_code == 404:
        return f"Repo {repo} not found or token lacks write access."
    if r.status_code not in (200, 201):
        return f"GitHub API error: HTTP {r.status_code}: {r.text[:200]}"
    try:
        body_json = r.json()
    except Exception:
        return "GitHub API returned non-JSON."
    return f"#{body_json.get('number')}  {body_json.get('html_url')}"


@tool(timeout=15)
async def github_get_pr(repo: str, number: int) -> str:
    """Fetch PR title, status, and summary.

    Args:
        repo: ``owner/name``.
        number: PR number.

    Returns:
        Multi-line summary or error string.
    """
    headers = _headers()
    if not headers:
        return "Error: LARGESTACK_GITHUB_TOKEN env var not set."
    err = _validate_repo(repo)
    if err:
        return f"Error: {err}"

    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            f"{_GH_API}/repos/{repo}/pulls/{int(number)}",
            headers=headers,
        )
    if r.status_code == 404:
        return f"PR #{number} not found in {repo}."
    if r.status_code >= 400:
        return f"GitHub API error: HTTP {r.status_code}: {r.text[:200]}"
    try:
        pr = r.json()
    except Exception:
        return "GitHub API returned non-JSON."

    state = pr.get("state", "")
    if pr.get("merged"):
        state = "merged"
    elif pr.get("draft"):
        state = "draft"

    return (
        f"#{pr['number']}  {pr['title']}\n"
        f"state: {state}\n"
        f"author: {pr['user']['login']}\n"
        f"branch: {pr['head']['ref']} -> {pr['base']['ref']}\n"
        f"changes: +{pr.get('additions', 0)} -{pr.get('deletions', 0)} "
        f"in {pr.get('changed_files', 0)} file(s)\n"
        f"url: {pr['html_url']}"
    )
