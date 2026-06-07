"""Slack integration — send messages and list channels.

Auth: env var ``LARGESTACK_SLACK_TOKEN`` (a Bot User OAuth token starting
with ``xoxb-``). Get one from <https://api.slack.com/apps> → "OAuth &
Permissions" → "Bot Token Scopes": at minimum ``chat:write`` and
``channels:read``.

Uses the Slack Web API directly via httpx — no slack_sdk dependency.
"""

from __future__ import annotations
import logging
import os

import httpx

from largestack._core.tools import tool

log = logging.getLogger("largestack.slack")
_SLACK_API = "https://slack.com/api"


def _token() -> str | None:
    return os.environ.get("LARGESTACK_SLACK_TOKEN", "").strip() or None


@tool(timeout=15)
async def slack_send_message(channel: str, text: str) -> str:
    """Send a message to a Slack channel.

    Args:
        channel: Channel name (e.g. ``"#engineering"``) or ID (e.g. ``"C0123ABC"``).
        text: Message body. Markdown supported (Slack ``mrkdwn``).

    Returns:
        Success message with channel + ts, or an error string.

    Requires: LARGESTACK_SLACK_TOKEN env var set to a Slack Bot User OAuth token.
    """
    tok = _token()
    if not tok:
        return "Error: LARGESTACK_SLACK_TOKEN env var not set."
    if not channel or not text:
        return "Error: channel and text are required."

    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(
            f"{_SLACK_API}/chat.postMessage",
            headers={"Authorization": f"Bearer {tok}"},
            json={"channel": channel, "text": text},
        )
    try:
        body = r.json()
    except Exception:
        return f"Slack API error: HTTP {r.status_code}"
    if not body.get("ok"):
        return f"Slack error: {body.get('error', 'unknown')}"
    return f"Posted to {body.get('channel', channel)} (ts={body.get('ts')})"


@tool(timeout=15)
async def slack_list_channels(limit: int = 50) -> str:
    """List public channels the bot has access to.

    Args:
        limit: Max channels to return (default 50, max 1000).

    Returns:
        Newline-separated ``id  name`` lines, or error string.
    """
    tok = _token()
    if not tok:
        return "Error: LARGESTACK_SLACK_TOKEN env var not set."
    limit = max(1, min(int(limit), 1000))

    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            f"{_SLACK_API}/conversations.list",
            headers={"Authorization": f"Bearer {tok}"},
            params={"limit": limit, "exclude_archived": "true"},
        )
    try:
        body = r.json()
    except Exception:
        return f"Slack API error: HTTP {r.status_code}"
    if not body.get("ok"):
        return f"Slack error: {body.get('error', 'unknown')}"
    chans = body.get("channels", [])
    if not chans:
        return "No channels found."
    return "\n".join(f"{c['id']}  #{c['name']}" for c in chans)
