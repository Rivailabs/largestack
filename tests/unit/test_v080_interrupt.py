"""v0.8.0: Human-in-the-loop interrupt tests."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from largestack._workflow import (
    HumanInTheLoop,
    InterruptException,
    interrupt,
    resume_with,
    Graph,
    END,
)


# -------------------- interrupt() primitive --------------------


def test_interrupt_raises_exception():
    with pytest.raises(InterruptException):
        interrupt("Approve?")


def test_interrupt_carries_metadata():
    try:
        interrupt(
            "Approve loan?",
            interrupt_id="loan_42",
            default="deny",
            choices=["approve", "deny"],
            metadata={"severity": "high"},
        )
        assert False, "should have raised"
    except InterruptException as e:
        assert e.interrupt_id == "loan_42"
        assert e.question == "Approve loan?"
        assert e.default == "deny"
        assert e.choices == ["approve", "deny"]
        assert e.metadata == {"severity": "high"}


def test_interrupt_auto_generates_id():
    try:
        interrupt("X?")
        assert False
    except InterruptException as e:
        assert e.interrupt_id  # non-empty UUID
        assert len(e.interrupt_id) > 8


def test_resume_with_helper():
    resp = resume_with("approve")
    assert resp.answer == "approve"
    assert resp.metadata["default_used"] is False
    resp2 = resume_with("deny", default_used=True)
    assert resp2.metadata["default_used"] is True


# -------------------- HumanInTheLoop callback path --------------------


@pytest.mark.asyncio
async def test_hitl_with_async_callback():
    """Async callback is awaited and its return value used as answer."""

    async def fake_ui(prompt: str) -> str:
        return f"answer to: {prompt}"

    hitl = HumanInTheLoop(callback=fake_ui)
    result = await hitl.ask("What is your name?")
    assert result == "answer to: What is your name?"
    assert len(hitl.history) == 1
    assert hitl.history[0]["answer"] == result


@pytest.mark.asyncio
async def test_hitl_with_sync_callback():
    """Sync callback is called and its return value used."""

    def fake_ui(prompt: str) -> str:
        return "yes"

    hitl = HumanInTheLoop(callback=fake_ui)
    result = await hitl.ask("OK?")
    assert result == "yes"


@pytest.mark.asyncio
async def test_hitl_validates_prompt():
    hitl = HumanInTheLoop(callback=lambda p: "x")
    with pytest.raises(ValueError):
        await hitl.ask("")


@pytest.mark.asyncio
async def test_hitl_callback_failure_uses_default():
    """If callback raises, return default and record the error."""

    async def broken_ui(prompt: str):
        raise RuntimeError("UI disconnected")

    hitl = HumanInTheLoop(callback=broken_ui)
    result = await hitl.ask("Q?", default="fallback")
    assert result == "fallback"
    assert hitl.history[-1]["default_used"] is True
    assert "disconnected" in hitl.history[-1]["error"]


@pytest.mark.asyncio
async def test_hitl_timeout_uses_default():
    """If async callback times out, return default."""

    async def slow_ui(prompt: str):
        await asyncio.sleep(10)  # never returns in time
        return "late"

    hitl = HumanInTheLoop(callback=slow_ui)
    result = await hitl.ask("Q?", default="default", timeout=0.05)
    assert result == "default"
    assert hitl.history[-1]["default_used"] is True


@pytest.mark.asyncio
async def test_hitl_validates_choices_re_asks_once():
    """Invalid answer → reask once. If still invalid → default."""
    answers = iter(["maybe", "yes"])

    async def fake_ui(prompt: str):
        return next(answers)

    hitl = HumanInTheLoop(callback=fake_ui)
    result = await hitl.ask("OK?", choices=["yes", "no"])
    assert result == "yes"
    rec = hitl.history[-1]
    assert rec["first_invalid"] == "maybe"
    assert rec["answer"] == "yes"


@pytest.mark.asyncio
async def test_hitl_invalid_twice_returns_default():
    answers = iter(["bad1", "bad2"])

    async def fake_ui(prompt: str):
        return next(answers)

    hitl = HumanInTheLoop(callback=fake_ui)
    result = await hitl.ask("OK?", choices=["yes", "no"], default="no")
    assert result == "no"
    assert hitl.history[-1]["default_used"] is True


def test_hitl_rejects_non_callable():
    with pytest.raises(TypeError):
        HumanInTheLoop(callback="not_a_function")


# -------------------- Integration with Graph workflow --------------------


@pytest.mark.asyncio
async def test_graph_node_can_use_hitl():
    """A graph node can call hitl.ask and proceed normally."""

    async def callback(prompt: str) -> str:
        return "approve"

    hitl = HumanInTheLoop(callback=callback)

    async def review_node(state: dict) -> dict:
        decision = await hitl.ask(f"Approve {state['amount']}?", choices=["approve", "deny"])
        return {"decision": decision}

    g = Graph()
    g.add_node("review", review_node)
    g.set_entry("review")
    g.add_edge("review", END)

    result = await g.run({"amount": 50000})
    assert result.state["decision"] == "approve"


@pytest.mark.asyncio
async def test_interrupt_exception_propagates_through_graph():
    """If a node calls interrupt(), the exception propagates out of run()."""

    def review_node(state):
        if state["amount"] > 100_000:
            interrupt("Approve large amount?", interrupt_id="big_x", default="deny")
        return {"approved": True}

    g = Graph()
    g.add_node("r", review_node)
    g.set_entry("r")
    g.add_edge("r", END)

    with pytest.raises(InterruptException) as exc_info:
        await g.run({"amount": 500_000})
    assert exc_info.value.interrupt_id == "big_x"
    assert exc_info.value.default == "deny"
