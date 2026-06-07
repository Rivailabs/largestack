"""Eval webhook alerts (v0.14.0).

Closes Tier A #10. Posts eval results to Slack / MS Teams / Discord /
generic webhooks. Used in CI when an eval suite passes/fails:

- Slack incoming webhook → ``payload`` shape with blocks
- MS Teams webhook → MessageCard / Adaptive Card payload
- Discord webhook → embeds payload
- Generic POST → JSON of the report

Usage::

    from largestack._eval.alerts import notify_eval_result, AlertChannel

    notify_eval_result(
        delta=delta,
        suite_name="KYC verification",
        channel=AlertChannel(
            kind="slack",
            url="https://hooks.slack.com/services/T0/B0/xxx",
        ),
        only_on_regression=True,  # don't notify on improvements
    )

The webhooks are POST'd via stdlib ``urllib`` — no extra deps. If
``aiohttp`` is installed, async helpers are also available.
"""

from __future__ import annotations
import asyncio
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Literal

from largestack._eval.pr_diff import (
    EvalDelta,
    render_pr_comment_markdown,
    render_slack_message,
)

log = logging.getLogger("largestack.eval.alerts")


AlertKind = Literal["slack", "teams", "discord", "generic"]


def _require_http_url(url: str) -> str:
    """Allow only absolute HTTP/HTTPS URLs before network requests."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must be absolute and use http or https")
    return url


@dataclass
class AlertChannel:
    """Webhook configuration."""

    kind: AlertKind
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 10.0


@dataclass
class AlertResult:
    """Result of attempting to send an alert."""

    sent: bool
    status_code: int = 0
    error: str = ""

    def __bool__(self) -> bool:
        return self.sent


# -------------------- Payload builders --------------------


def _build_slack_payload(
    delta: EvalDelta,
    suite_name: str,
) -> dict[str, Any]:
    """Build a Slack incoming-webhook payload (blocks format)."""
    icon = "⚠️" if delta.is_overall_regression else "✅"
    title = f"{icon} Eval result — {suite_name}"

    delta_pct = delta.pass_rate_delta * 100
    sign = "+" if delta_pct >= 0 else ""
    summary = (
        f"Pass rate: {delta.baseline_pass_rate * 100:.1f}% "
        f"→ {delta.current_pass_rate * 100:.1f}% "
        f"({sign}{delta_pct:.1f}%)"
    )

    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": title}},
        {"type": "section", "text": {"type": "mrkdwn", "text": summary}},
    ]

    if delta.regressions:
        regress_text = "\n".join(f"• `{r.name}`" for r in delta.regressions[:10])
        if len(delta.regressions) > 10:
            regress_text += f"\n_…and {len(delta.regressions) - 10} more_"
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (f"*🔴 Regressions ({len(delta.regressions)})*\n{regress_text}"),
                },
            }
        )

    if delta.improvements:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (f"*🟢 Improvements*: {len(delta.improvements)} case(s)"),
                },
            }
        )

    return {
        "text": title,  # fallback for clients that don't render blocks
        "blocks": blocks,
    }


def _build_teams_payload(
    delta: EvalDelta,
    suite_name: str,
) -> dict[str, Any]:
    """Build a Microsoft Teams MessageCard payload."""
    color = "FF6B35" if delta.is_overall_regression else "10B981"
    icon = "⚠️" if delta.is_overall_regression else "✅"

    facts = [
        {
            "name": "Baseline",
            "value": f"{delta.baseline_pass_rate * 100:.1f}%",
        },
        {
            "name": "Current",
            "value": f"{delta.current_pass_rate * 100:.1f}%",
        },
        {
            "name": "Δ",
            "value": f"{delta.pass_rate_delta * 100:+.1f}%",
        },
    ]
    if delta.regressions:
        facts.append(
            {
                "name": "Regressions",
                "value": str(len(delta.regressions)),
            }
        )

    return {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": color,
        "summary": f"{icon} Eval — {suite_name}",
        "title": f"{icon} Eval result — {suite_name}",
        "sections": [
            {"activityTitle": "LARGESTACK eval-block report", "facts": facts, "markdown": True}
        ],
    }


def _build_discord_payload(
    delta: EvalDelta,
    suite_name: str,
) -> dict[str, Any]:
    """Build a Discord webhook payload (embeds)."""
    color = 0xEF4444 if delta.is_overall_regression else 0x10B981
    icon = "⚠️" if delta.is_overall_regression else "✅"

    fields = [
        {"name": "Baseline", "value": f"{delta.baseline_pass_rate * 100:.1f}%", "inline": True},
        {"name": "Current", "value": f"{delta.current_pass_rate * 100:.1f}%", "inline": True},
        {"name": "Δ", "value": f"{delta.pass_rate_delta * 100:+.1f}%", "inline": True},
    ]
    if delta.regressions:
        names = "\n".join(f"• {r.name}" for r in delta.regressions[:10])
        fields.append(
            {
                "name": f"🔴 Regressions ({len(delta.regressions)})",
                "value": names,
                "inline": False,
            }
        )

    return {
        "embeds": [
            {
                "title": f"{icon} Eval result — {suite_name}",
                "color": color,
                "fields": fields,
            }
        ]
    }


def _build_generic_payload(
    delta: EvalDelta,
    suite_name: str,
) -> dict[str, Any]:
    """Build a generic JSON payload — useful for Zapier / n8n / custom."""
    return {
        "type": "largestack.eval.result",
        "suite_name": suite_name,
        "is_regression": delta.is_overall_regression,
        "pass_rate_delta": delta.pass_rate_delta,
        "baseline": {
            "pass_rate": delta.baseline_pass_rate,
            "total": delta.baseline_total,
        },
        "current": {
            "pass_rate": delta.current_pass_rate,
            "total": delta.current_total,
        },
        "regressions": [r.name for r in delta.regressions],
        "improvements": [i.name for i in delta.improvements],
        "new_cases": [n.name for n in delta.new_cases],
        "removed_cases": [r.name for r in delta.removed_cases],
        "markdown_summary": render_pr_comment_markdown(
            delta,
            suite_name=suite_name,
        ),
    }


def build_payload(
    kind: AlertKind,
    delta: EvalDelta,
    suite_name: str,
) -> dict[str, Any]:
    """Build the appropriate payload for the given channel kind."""
    builders = {
        "slack": _build_slack_payload,
        "teams": _build_teams_payload,
        "discord": _build_discord_payload,
        "generic": _build_generic_payload,
    }
    if kind not in builders:
        raise ValueError(f"unknown alert kind: {kind}")
    return builders[kind](delta, suite_name)


# -------------------- HTTP delivery --------------------


def _post_json_sync(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> AlertResult:
    """POST JSON via stdlib urllib (no aiohttp dependency)."""
    body = json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    safe_url = _require_http_url(url)
    req = urllib.request.Request(
        safe_url,
        data=body,
        headers=req_headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
            return AlertResult(sent=True, status_code=resp.status)
    except urllib.error.HTTPError as e:
        return AlertResult(
            sent=False,
            status_code=e.code,
            error=str(e),
        )
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return AlertResult(sent=False, error=str(e))


def notify_eval_result(
    delta: EvalDelta,
    *,
    suite_name: str,
    channel: AlertChannel,
    only_on_regression: bool = False,
    only_on_change: bool = False,
) -> AlertResult:
    """Send an eval result alert to a webhook.

    Args:
        delta: the computed eval delta
        suite_name: human label
        channel: webhook configuration
        only_on_regression: skip if no regression
        only_on_change: skip if pass-rate unchanged (within 0.1%)
    """
    if only_on_regression and not delta.is_overall_regression:
        return AlertResult(sent=False, error="skipped: no regression")
    if only_on_change and abs(delta.pass_rate_delta) < 0.001:
        return AlertResult(sent=False, error="skipped: no change")

    payload = build_payload(channel.kind, delta, suite_name)
    return _post_json_sync(
        channel.url,
        payload,
        headers=channel.headers,
        timeout=channel.timeout_seconds,
    )


async def notify_eval_result_async(
    delta: EvalDelta,
    *,
    suite_name: str,
    channel: AlertChannel,
    only_on_regression: bool = False,
    only_on_change: bool = False,
) -> AlertResult:
    """Async variant — uses ``aiohttp`` if available, else thread."""
    if only_on_regression and not delta.is_overall_regression:
        return AlertResult(sent=False, error="skipped: no regression")
    if only_on_change and abs(delta.pass_rate_delta) < 0.001:
        return AlertResult(sent=False, error="skipped: no change")

    payload = build_payload(channel.kind, delta, suite_name)

    try:
        import aiohttp  # type: ignore[import-not-found]
    except ImportError:
        return await asyncio.to_thread(
            _post_json_sync,
            channel.url,
            payload,
            channel.headers,
            channel.timeout_seconds,
        )

    timeout = aiohttp.ClientTimeout(total=channel.timeout_seconds)
    headers = {"Content-Type": "application/json", **channel.headers}
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                channel.url,
                json=payload,
                headers=headers,
            ) as resp:
                return AlertResult(sent=True, status_code=resp.status)
    except Exception as e:
        return AlertResult(sent=False, error=str(e))


__all__ = [
    "AlertChannel",
    "AlertResult",
    "AlertKind",
    "build_payload",
    "notify_eval_result",
    "notify_eval_result_async",
]
