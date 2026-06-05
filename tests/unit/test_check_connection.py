"""check_connection() must report a clear failure (not hang/raise) when a provider
is unreachable / has no key — so users can verify each provider with their own key.
"""
from __future__ import annotations

import os

from largestack import check_connection


async def test_reports_failure_without_key():
    os.environ.pop("LARGESTACK_GROQ_API_KEY", None)
    r = await check_connection("groq/llama-3.3-70b-versatile", timeout=10)
    assert r["ok"] is False
    assert r["provider"] == "groq"
    assert isinstance(r["detail"], str) and r["detail"]
    assert r["cost"] == 0.0


def test_check_connection_is_public():
    import largestack
    assert hasattr(largestack, "check_connection")
