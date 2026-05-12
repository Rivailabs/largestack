"""Notion integration — read pages and search the workspace.

Auth: env var ``LARGESTACK_NOTION_TOKEN`` (an Internal Integration token —
get one from <https://www.notion.so/my-integrations>).

Hits the Notion REST API directly via httpx — no notion_client dep.
"""
from __future__ import annotations
import logging
import os

import httpx

from largestack._core.tools import tool

log = logging.getLogger("largestack.notion")
_NOTION_API = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"  # Latest stable version


def _headers() -> dict | None:
    tok = os.environ.get("LARGESTACK_NOTION_TOKEN", "").strip()
    if not tok:
        return None
    return {
        "Authorization": f"Bearer {tok}",
        "Notion-Version": _NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _block_to_text(block: dict) -> str:
    """Extract plain text from a Notion block. Handles common block types."""
    btype = block.get("type", "")
    data = block.get(btype, {})
    rich = data.get("rich_text") or data.get("text") or []
    text = "".join(r.get("plain_text", "") for r in rich)
    if btype == "heading_1":
        return f"# {text}"
    if btype == "heading_2":
        return f"## {text}"
    if btype == "heading_3":
        return f"### {text}"
    if btype == "bulleted_list_item":
        return f"- {text}"
    if btype == "numbered_list_item":
        return f"1. {text}"
    if btype == "to_do":
        check = "[x]" if data.get("checked") else "[ ]"
        return f"{check} {text}"
    if btype == "code":
        lang = data.get("language", "")
        return f"```{lang}\n{text}\n```"
    if btype == "divider":
        return "---"
    return text


@tool(timeout=20)
async def notion_read_page(page_id: str) -> str:
    """Read a Notion page and return its content as Markdown-ish text.

    Args:
        page_id: Page UUID (with or without dashes). The integration must
            be invited to the page (Notion → Share → "Invite" → your integration).

    Returns:
        Plain-text rendering of the page blocks, or error string.
    """
    headers = _headers()
    if not headers:
        return "Error: LARGESTACK_NOTION_TOKEN env var not set."
    if not page_id:
        return "Error: page_id is required."

    # Notion accepts UUIDs with or without dashes
    page_id = page_id.replace("-", "")

    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            f"{_NOTION_API}/blocks/{page_id}/children?page_size=100",
            headers=headers,
        )
    if r.status_code == 404:
        return f"Notion page {page_id} not found or integration lacks access."
    if r.status_code >= 400:
        return f"Notion API error: HTTP {r.status_code}: {r.text[:200]}"
    try:
        body = r.json()
    except Exception:
        return "Notion API returned non-JSON response."
    blocks = body.get("results", [])
    if not blocks:
        return "(empty page)"
    return "\n".join(_block_to_text(b) for b in blocks if _block_to_text(b))


@tool(timeout=15)
async def notion_search(query: str, limit: int = 10) -> str:
    """Search the Notion workspace for pages matching a query.

    Args:
        query: Search text.
        limit: Max results (default 10).

    Returns:
        Newline-separated ``page_id  title`` lines, or error.
    """
    headers = _headers()
    if not headers:
        return "Error: LARGESTACK_NOTION_TOKEN env var not set."

    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(
            f"{_NOTION_API}/search",
            headers=headers,
            json={
                "query": query,
                "page_size": max(1, min(int(limit), 100)),
                "filter": {"property": "object", "value": "page"},
            },
        )
    if r.status_code >= 400:
        return f"Notion API error: HTTP {r.status_code}: {r.text[:200]}"
    try:
        body = r.json()
    except Exception:
        return "Notion API returned non-JSON."
    results = body.get("results", [])
    if not results:
        return f"No results for {query!r}."
    lines = []
    for p in results:
        pid = p.get("id", "")
        # Title is in different places depending on parent
        props = p.get("properties", {})
        title = ""
        for prop_val in props.values():
            if isinstance(prop_val, dict) and prop_val.get("type") == "title":
                title_arr = prop_val.get("title", [])
                title = "".join(t.get("plain_text", "") for t in title_arr)
                break
        lines.append(f"{pid}  {title or '(untitled)'}")
    return "\n".join(lines)
