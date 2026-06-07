"""Linear integration — query and create issues via GraphQL.

Auth: env var ``LARGESTACK_LINEAR_API_KEY`` (a Personal API key from Linear
Settings → API → Personal API keys).
"""

from __future__ import annotations
import json
import logging
import os

import httpx

from largestack._core.tools import tool

log = logging.getLogger("largestack.linear")
_LINEAR_API = "https://api.linear.app/graphql"


def _headers() -> dict | None:
    tok = os.environ.get("LARGESTACK_LINEAR_API_KEY", "").strip()
    if not tok:
        return None
    return {
        "Authorization": tok,  # Linear uses the raw key, not Bearer
        "Content-Type": "application/json",
    }


async def _gql(query: str, variables: dict | None = None) -> tuple[bool, dict | str]:
    """Execute a GraphQL request. Returns (ok, data_or_error_msg)."""
    headers = _headers()
    if not headers:
        return False, "LARGESTACK_LINEAR_API_KEY env var not set."
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            _LINEAR_API,
            headers=headers,
            json={"query": query, "variables": variables or {}},
        )
    if r.status_code >= 400:
        return False, f"Linear API HTTP {r.status_code}: {r.text[:200]}"
    try:
        body = r.json()
    except Exception:
        return False, "Linear API returned non-JSON."
    if "errors" in body and body["errors"]:
        return False, f"Linear GraphQL error: {body['errors'][0].get('message', 'unknown')}"
    return True, body.get("data", {})


@tool(timeout=15)
async def linear_list_issues(team_key: str = "", limit: int = 20) -> str:
    """List recent issues, optionally filtered by team.

    Args:
        team_key: Team key (e.g. "ENG"). Empty = all teams the API key can see.
        limit: Max results (1-50, default 20).

    Returns:
        Newline-separated ``ID  TITLE  [STATE]`` lines, or error.
    """
    limit = max(1, min(int(limit), 50))
    if team_key:
        query = """
        query ($key: String!, $first: Int!) {
            team(id: $key) {
                issues(first: $first) {
                    nodes { identifier title state { name } }
                }
            }
        }
        """
        ok, data = await _gql(query, {"key": team_key, "first": limit})
        if not ok:
            return f"Error: {data}"
        team = data.get("team")
        if not team:
            return f"Team {team_key!r} not found."
        nodes = team.get("issues", {}).get("nodes", [])
    else:
        query = """
        query ($first: Int!) {
            issues(first: $first) {
                nodes { identifier title state { name } }
            }
        }
        """
        ok, data = await _gql(query, {"first": limit})
        if not ok:
            return f"Error: {data}"
        nodes = data.get("issues", {}).get("nodes", [])

    if not nodes:
        return "No issues found."
    return "\n".join(f"{n['identifier']}  {n['title']}  [{n['state']['name']}]" for n in nodes)


@tool(timeout=15)
async def linear_create_issue(team_id: str, title: str, description: str = "") -> str:
    """Create a Linear issue.

    Args:
        team_id: The team's UUID (NOT the team key — get this from Linear
            settings or via linear_list_teams). Required.
        title: Issue title.
        description: Markdown description (optional).

    Returns:
        ``ID  URL`` of created issue, or error.
    """
    if not team_id or not title:
        return "Error: team_id and title are required."
    query = """
    mutation ($input: IssueCreateInput!) {
        issueCreate(input: $input) {
            success
            issue { identifier url }
        }
    }
    """
    variables = {
        "input": {
            "teamId": team_id,
            "title": title,
            "description": description,
        }
    }
    ok, data = await _gql(query, variables)
    if not ok:
        return f"Error: {data}"
    payload = data.get("issueCreate", {})
    if not payload.get("success"):
        return "Linear: issue creation reported failure (check team_id)."
    issue = payload.get("issue", {})
    return f"{issue.get('identifier')}  {issue.get('url')}"
