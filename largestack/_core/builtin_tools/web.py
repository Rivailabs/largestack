"""Web search and fetch tools.

v0.3.12: web_fetch now uses the shared SSRF validator. Previously
follow_redirects=True with no host check meant any LLM tool call could hit
metadata IPs or internal services, defeating the v0.3.11 fix to http_tool.
"""
from __future__ import annotations
import os
import re

import httpx

from largestack._core.tools import tool
from largestack._core.builtin_tools._url_validator import validate_url


_FOLLOW_REDIRECTS = os.environ.get(
    "LARGESTACK_HTTP_TOOL_FOLLOW_REDIRECTS", ""
).lower() in ("1", "true", "yes")


@tool(timeout=15)
async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web for information. Returns top results.

    Uses Tavily if TAVILY_API_KEY is set; otherwise DuckDuckGo instant answer.
    Both endpoints are external; no SSRF concern, but we validate anyway in
    case operators set LARGESTACK_HTTP_ALLOWLIST.
    """
    tavily_key = os.environ.get("TAVILY_API_KEY", "")
    if tavily_key:
        url = "https://api.tavily.com/search"
        err = validate_url(url)
        if err:
            return f"Search disabled: {err}"
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                url,
                json={"api_key": tavily_key, "query": query,
                      "max_results": max_results},
            )
            data = r.json()
            results = []
            for item in data.get("results", [])[:max_results]:
                results.append(
                    f"**{item['title']}**\n{item['url']}\n"
                    f"{item.get('content','')[:200]}"
                )
            return "\n\n".join(results) or "No results found."

    # Fallback: DuckDuckGo instant answer
    url = "https://api.duckduckgo.com/"
    err = validate_url(url)
    if err:
        return f"Search disabled: {err}"
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(url, params={"q": query, "format": "json", "no_html": 1})
        data = r.json()
        abstract = data.get("AbstractText", "")
        if abstract:
            return abstract
        related = [
            t.get("Text", "")
            for t in data.get("RelatedTopics", [])[:max_results]
            if t.get("Text")
        ]
        return "\n".join(related) or (
            f"Search results for '{query}' — use web_fetch on specific URLs for details."
        )


@tool(timeout=20)
async def web_fetch(url: str) -> str:
    """Fetch a URL and convert HTML to plain text. SSRF-protected.

    Same protection as http_request:
        - Scheme must be http/https
        - Host must NOT resolve to a private/loopback/link-local/metadata IP
        - LARGESTACK_HTTP_ALLOWLIST controls strict pinning
        - Redirects OFF by default (LARGESTACK_HTTP_TOOL_FOLLOW_REDIRECTS=1 to enable)

    Returns plain-text content, capped at 5000 characters.
    """
    err = validate_url(url)
    if err is not None:
        return f"Request blocked: {err}"

    try:
        async with httpx.AsyncClient(
            follow_redirects=_FOLLOW_REDIRECTS, timeout=15
        ) as c:
            r = await c.get(url, headers={"User-Agent": "LargestackAI/0.1"})
            r.raise_for_status()
            html = r.text
    except httpx.RequestError as e:
        return f"Fetch error: {e}"

    # Basic HTML to text
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:5000]
