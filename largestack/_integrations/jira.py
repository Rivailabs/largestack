"""Jira integration — search issues and add comments via REST API v3.

Auth: env vars ``LARGESTACK_JIRA_URL`` (e.g. https://yourorg.atlassian.net),
``LARGESTACK_JIRA_EMAIL``, and ``LARGESTACK_JIRA_API_TOKEN`` (from
https://id.atlassian.com/manage-profile/security/api-tokens).
"""

from __future__ import annotations
import base64
import logging
import os

import httpx

from largestack._core.tools import tool

log = logging.getLogger("largestack.jira")


def _config() -> tuple[str, dict] | None:
    base = os.environ.get("LARGESTACK_JIRA_URL", "").strip().rstrip("/")
    email = os.environ.get("LARGESTACK_JIRA_EMAIL", "").strip()
    token = os.environ.get("LARGESTACK_JIRA_API_TOKEN", "").strip()
    if not (base and email and token):
        return None
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    return base, headers


@tool(timeout=15)
async def jira_search_issues(jql: str, limit: int = 20) -> str:
    """Search Jira issues using JQL.

    Args:
        jql: Jira Query Language, e.g. ``"project = ENG AND status = 'In Progress'"``.
        limit: Max results (1-50, default 20).

    Returns:
        Newline-separated ``KEY  SUMMARY  [STATUS]`` lines, or error.
    """
    cfg = _config()
    if not cfg:
        return (
            "Error: LARGESTACK_JIRA_URL, LARGESTACK_JIRA_EMAIL, LARGESTACK_JIRA_API_TOKEN "
            "env vars must be set."
        )
    base, headers = cfg
    limit = max(1, min(int(limit), 50))

    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(
            f"{base}/rest/api/3/search/jql",
            headers=headers,
            json={
                "jql": jql,
                "maxResults": limit,
                "fields": ["summary", "status"],
            },
        )
    if r.status_code == 401:
        return "Jira authentication failed. Check email and API token."
    if r.status_code >= 400:
        return f"Jira API error: HTTP {r.status_code}: {r.text[:200]}"
    try:
        body = r.json()
    except Exception:
        return "Jira API returned non-JSON."
    issues = body.get("issues", [])
    if not issues:
        return "No issues match."
    lines = []
    for i in issues:
        key = i.get("key", "")
        fields = i.get("fields", {})
        summary = fields.get("summary", "")
        status = fields.get("status", {}).get("name", "")
        lines.append(f"{key}  {summary}  [{status}]")
    return "\n".join(lines)


@tool(timeout=15)
async def jira_add_comment(issue_key: str, body: str) -> str:
    """Add a plain-text comment to a Jira issue.

    Args:
        issue_key: e.g. ``"ENG-123"``.
        body: Comment text.

    Returns:
        Success message with comment id, or error.
    """
    cfg = _config()
    if not cfg:
        return "Error: LARGESTACK_JIRA_* env vars not set."
    base, headers = cfg
    if not issue_key or not body:
        return "Error: issue_key and body are required."

    # Jira v3 expects ADF (Atlassian Document Format)
    adf_body = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": body}],
            }
        ],
    }

    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(
            f"{base}/rest/api/3/issue/{issue_key}/comment",
            headers=headers,
            json={"body": adf_body},
        )
    if r.status_code == 404:
        return f"Issue {issue_key} not found."
    if r.status_code not in (200, 201):
        return f"Jira API error: HTTP {r.status_code}: {r.text[:200]}"
    try:
        data = r.json()
    except Exception:
        return "Jira API returned non-JSON."
    return f"Comment added to {issue_key} (id={data.get('id')})"
