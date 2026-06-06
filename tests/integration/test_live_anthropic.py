"""Live Anthropic verification — runs ONLY when a real key is provided.

Anthropic is the one adapter that has never been live-verified end-to-end (no key
was available). This test makes that verifiable: set LARGESTACK_ANTHROPIC_API_KEY to a
real `sk-ant-...` key with credits and it runs a single live `check_connection` call;
otherwise it skips. When it passes in CI, the provider matrix can honestly move
anthropic from `adapter_only` → `verified`.

    LARGESTACK_ANTHROPIC_API_KEY=sk-ant-... pytest tests/integration/test_live_anthropic.py
"""
from __future__ import annotations
import asyncio
import os

import pytest

_KEY = os.environ.get("LARGESTACK_ANTHROPIC_API_KEY", "")


@pytest.mark.skipif(not _KEY, reason="no LARGESTACK_ANTHROPIC_API_KEY — set a real key to verify Anthropic live")
def test_anthropic_check_connection_live():
    from largestack import check_connection
    model = os.environ.get("LARGESTACK_ANTHROPIC_TEST_MODEL", "anthropic/claude-haiku-4-5-20251001")
    res = asyncio.run(check_connection(model))
    assert res.get("ok") is True, f"anthropic check_connection failed: {res.get('detail')}"
