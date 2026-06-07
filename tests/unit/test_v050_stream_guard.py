"""v0.5.0: per-chunk streaming guardrails.

Validates that ``stream_guard=True`` blocks unsafe content mid-stream
instead of letting the user see it before guards run.
"""

from __future__ import annotations

import pytest


# -------------------- helpers --------------------


class _FakeGuardrails:
    """Minimal guardrails impl. Blocks any output containing a forbidden word."""

    def __init__(self, forbidden: str = "FORBIDDEN"):
        self.forbidden = forbidden
        self.calls: list[str] = []

    async def check_input(self, msgs):
        return None

    async def check_output(self, resp):
        text = getattr(resp, "content", "")
        self.calls.append(text)
        if self.forbidden in text:
            raise RuntimeError(f"Output contains forbidden term: {self.forbidden}")


class _FakeGateway:
    """Streams a fixed list of tokens."""

    def __init__(self, tokens: list[str]):
        self.tokens = tokens

    async def stream(self, model, messages, **kw):
        for t in self.tokens:
            yield t


# -------------------- tests --------------------


@pytest.mark.asyncio
async def test_stream_guard_off_legacy_behavior_yields_unsafe_content():
    """When stream_guard=False (default), unsafe tokens are yielded.
    This is the v0.3 behavior — kept for backwards compat."""
    from largestack._core.engine import AgentEngine

    eng = AgentEngine.__new__(AgentEngine)
    eng.name = "test"
    eng.llm = "test/test"
    eng.guardrails = _FakeGuardrails(forbidden="leaked")
    eng.gateway = _FakeGateway(["safe ", "tokens ", "and leaked ", "data"])
    eng.cost_budget = None
    eng.tools = []
    eng.system_prompt = ""
    eng.memory = None
    eng._check_kill_switch = lambda: None
    eng._build_msgs = lambda task: [{"role": "user", "content": task}]
    eng._kill_switch = None

    out = []
    async for tok in eng.stream("test"):
        out.append(tok)

    full = "".join(out)
    # Without guard mode, all tokens are yielded
    assert "leaked" in full


@pytest.mark.asyncio
async def test_stream_guard_on_blocks_chunk_with_unsafe_content():
    """When stream_guard=True, chunk containing forbidden word is replaced
    with redaction marker and stream stops."""
    from largestack._core.engine import AgentEngine

    eng = AgentEngine.__new__(AgentEngine)
    eng.name = "test"
    eng.llm = "test/test"
    eng.guardrails = _FakeGuardrails(forbidden="LEAKED_SECRET")
    eng.gateway = _FakeGateway(
        [
            "safe content. ",
            "more safe text. ",
            "this contains LEAKED_SECRET word. ",
            "more after but stream should be blocked.",
        ]
    )
    eng.cost_budget = None
    eng.tools = []
    eng.system_prompt = ""
    eng.memory = None
    eng._check_kill_switch = lambda: None
    eng._build_msgs = lambda task: [{"role": "user", "content": task}]
    eng._kill_switch = None

    out = []
    async for tok in eng.stream("test", stream_guard=True, stream_chunk_chars=20):
        out.append(tok)

    full = "".join(out)
    # The leaked secret must NOT have reached the user
    assert "LEAKED_SECRET" not in full, f"Secret leaked despite guard: {full!r}"
    # Redaction marker must be present
    assert "blocked by safety policy" in full
    # Safe early chunks should have been delivered
    assert "safe content" in full


@pytest.mark.asyncio
async def test_stream_guard_passes_safe_content_through():
    """All safe tokens must pass through when guard is on."""
    from largestack._core.engine import AgentEngine

    eng = AgentEngine.__new__(AgentEngine)
    eng.name = "test"
    eng.llm = "test/test"
    eng.guardrails = _FakeGuardrails(forbidden="NEVER_APPEARS")
    eng.gateway = _FakeGateway(
        [
            "Hello, ",
            "this is a ",
            "completely safe ",
            "response with no ",
            "issues at all.",
        ]
    )
    eng.cost_budget = None
    eng.tools = []
    eng.system_prompt = ""
    eng.memory = None
    eng._check_kill_switch = lambda: None
    eng._build_msgs = lambda task: [{"role": "user", "content": task}]
    eng._kill_switch = None

    out = []
    async for tok in eng.stream("test", stream_guard=True, stream_chunk_chars=20):
        out.append(tok)
    full = "".join(out)
    assert "Hello, this is a completely safe response with no issues at all." == full
    assert "blocked" not in full


@pytest.mark.asyncio
async def test_stream_guard_custom_redaction_marker():
    """The redaction marker can be customized."""
    from largestack._core.engine import AgentEngine

    eng = AgentEngine.__new__(AgentEngine)
    eng.name = "test"
    eng.llm = "test/test"
    eng.guardrails = _FakeGuardrails(forbidden="bad")
    eng.gateway = _FakeGateway(["this is bad content."])
    eng.cost_budget = None
    eng.tools = []
    eng.system_prompt = ""
    eng.memory = None
    eng._check_kill_switch = lambda: None
    eng._build_msgs = lambda task: [{"role": "user", "content": task}]
    eng._kill_switch = None

    out = []
    async for tok in eng.stream(
        "test",
        stream_guard=True,
        stream_chunk_chars=10,
        stream_redaction_marker="*** REDACTED ***",
    ):
        out.append(tok)
    full = "".join(out)
    assert "*** REDACTED ***" in full
    assert "bad content" not in full


@pytest.mark.asyncio
async def test_stream_guard_off_works_without_guardrails():
    """No guardrails attached + stream_guard=False = pure pass-through."""
    from largestack._core.engine import AgentEngine

    eng = AgentEngine.__new__(AgentEngine)
    eng.name = "test"
    eng.llm = "test/test"
    eng.guardrails = None
    eng.gateway = _FakeGateway(["tok1 ", "tok2 ", "tok3"])
    eng.cost_budget = None
    eng.tools = []
    eng.system_prompt = ""
    eng.memory = None
    eng._check_kill_switch = lambda: None
    eng._build_msgs = lambda task: [{"role": "user", "content": task}]
    eng._kill_switch = None

    out = []
    async for tok in eng.stream("test"):
        out.append(tok)
    assert "".join(out) == "tok1 tok2 tok3"
