"""Focused tests for the Jarvis demo bundle.

Run from the bundle root:  cd jarvis_app && python -m pytest test_jarvis.py -q
These need no API key — they exercise the tools and safety bounds directly.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("JARVIS_DATA_DIR", "/tmp/jarvis_test_data")
os.environ.setdefault("JARVIS_WORKSPACE", str(ROOT))

from jarvis import memory_store, tools  # noqa: E402
from jarvis.assistant import JarvisReply  # noqa: E402


def _call(t, **kw):
    fn = getattr(t, "func", t)
    return asyncio.run(fn(**kw))


def test_calculator_basic():
    assert _call(tools.calculate, expression="23 * 19 + 7") == "444"


def test_calculator_refuses_pow_dos_without_hanging():
    # The bound must reject before computing — wrap in a timeout as a safety net.
    out = asyncio.run(asyncio.wait_for(_wrap(tools.calculate, expression="9**9**9"), timeout=5))
    assert "Error" in out


async def _wrap(t, **kw):
    fn = getattr(t, "func", t)
    return await fn(**kw)


def test_calculator_refuses_overlong_expression():
    assert "too long" in _call(tools.calculate, expression="1+" * 200 + "1")


def test_list_directory_refuses_outside_workspace():
    assert "outside the Jarvis workspace" in _call(tools.list_directory, path="/etc")


def test_list_directory_allows_inside_workspace():
    out = _call(tools.list_directory, path=".")
    assert "run.py" in out


def test_request_approval_persists_to_queue():
    before = len(memory_store.get_approvals())
    out = _call(tools.request_approval, action="delete all files", details="risky")
    assert "pending" in out.lower()
    after = memory_store.get_approvals()
    assert len(after) == before + 1
    assert after[-1]["status"] == "pending"


def test_reply_is_typed_model():
    r = JarvisReply(reply="hi")
    assert r.reply == "hi" and r.tools_used == []
