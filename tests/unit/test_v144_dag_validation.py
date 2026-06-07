"""v0.14.4 — Bug fixes from competitor-parity audit.

Three real bugs found and fixed:

1. Duplicate node name in Workflow silently overwrote — now raises ValueError.
2. Dependency cycle silently produced empty result — now raises ValueError
   with the cycle path in the message.
3. Reference to nonexistent dep silently produced empty result — now raises
   ValueError naming the missing nodes.

These are P1 developer-experience bugs: the framework would silently produce
wrong/empty results instead of failing loudly with an actionable message.
"""

from __future__ import annotations
import asyncio

import pytest

from largestack import Workflow


async def _h(state: dict) -> dict:
    return state


# ---------------------------------------------------------------------------
# Bug 1: duplicate node name
# ---------------------------------------------------------------------------


def test_duplicate_node_name_raises():
    wf = Workflow(name="t", mode="dag")
    wf.add_node("a", _h)
    with pytest.raises(ValueError, match="already has a node named 'a'"):
        wf.add_node("a", _h)


def test_duplicate_node_message_is_actionable():
    wf = Workflow(name="t", mode="dag")
    wf.add_node("a", _h)
    with pytest.raises(ValueError) as exc:
        wf.add_node("a", _h)
    msg = str(exc.value)
    # Message should include both the rule and the workaround
    assert "unique" in msg.lower()
    assert "remove" in msg.lower() or "different name" in msg.lower()


# ---------------------------------------------------------------------------
# Bug 2: dependency cycle
# ---------------------------------------------------------------------------


def test_simple_cycle_raises():
    wf = Workflow(name="t", mode="dag")
    wf.add_node("a", _h, deps=["b"])
    wf.add_node("b", _h, deps=["a"])
    with pytest.raises(ValueError, match="cycle"):
        asyncio.run(wf.run({}))


def test_three_node_cycle_raises_with_path():
    wf = Workflow(name="t", mode="dag")
    wf.add_node("a", _h, deps=["c"])
    wf.add_node("b", _h, deps=["a"])
    wf.add_node("c", _h, deps=["b"])
    with pytest.raises(ValueError) as exc:
        asyncio.run(wf.run({}))
    msg = str(exc.value)
    # Should name the cycle path
    assert "cycle" in msg.lower()
    assert "→" in msg or "->" in msg


def test_self_loop_cycle_raises():
    wf = Workflow(name="t", mode="dag")
    wf.add_node("a", _h, deps=["a"])
    with pytest.raises(ValueError, match="cycle"):
        asyncio.run(wf.run({}))


# ---------------------------------------------------------------------------
# Bug 3: missing dep reference
# ---------------------------------------------------------------------------


def test_missing_dep_raises():
    wf = Workflow(name="t", mode="dag")
    wf.add_node("a", _h, deps=["ghost"])
    with pytest.raises(ValueError, match="undefined node"):
        asyncio.run(wf.run({}))


def test_missing_dep_message_names_the_missing_node():
    wf = Workflow(name="t", mode="dag")
    wf.add_node("a", _h, deps=["ghost", "phantom"])
    with pytest.raises(ValueError) as exc:
        asyncio.run(wf.run({}))
    msg = str(exc.value)
    assert "ghost" in msg
    assert "phantom" in msg


# ---------------------------------------------------------------------------
# Sanity: valid graphs still run
# ---------------------------------------------------------------------------


def test_valid_dag_still_runs():
    wf = Workflow(name="t", mode="dag")
    wf.add_node("a", _h)
    wf.add_node("b", _h, deps=["a"])
    wf.add_node("c", _h, deps=["b"])
    result = asyncio.run(wf.run({"task": "ok"}))
    assert result["task"] == "ok"
    assert "_total_cost" in result


def test_diamond_dag_runs():
    """a → {b, c} → d (parallel branches)"""
    wf = Workflow(name="t", mode="dag")
    wf.add_node("a", _h)
    wf.add_node("b", _h, deps=["a"])
    wf.add_node("c", _h, deps=["a"])
    wf.add_node("d", _h, deps=["b", "c"])
    result = asyncio.run(wf.run({"task": "diamond"}))
    assert result["task"] == "diamond"


# ---------------------------------------------------------------------------
# v1.0.0 ergonomic addition: Agent.guardrails public property
# ---------------------------------------------------------------------------


def test_agent_guardrails_public_attribute():
    """Configured guardrails should be accessible via a public attribute."""
    from largestack import Agent, create_guardrails

    g = create_guardrails(pii=True)
    a = Agent(name="x", instructions="x", llm="openai/gpt-4o-mini", guardrails=g)
    assert a.guardrails is g


def test_agent_guardrails_property_returns_pipeline():
    """When guardrails are configured, the property returns the pipeline."""
    from largestack import Agent, create_guardrails
    from largestack._guard.pipeline import GuardrailPipeline

    g = create_guardrails(pii=True, injection=True)
    a = Agent(name="x", instructions="x", llm="openai/gpt-4o-mini", guardrails=g)
    # The property always returns a pipeline (default or explicit)
    assert isinstance(a.guardrails, GuardrailPipeline)
    # When explicitly passed, the same object comes back
    assert a.guardrails is g
