"""v0.14.0: Tests for sub-graph Workflow composition."""

from __future__ import annotations

import pytest


# Simple sync handler for testing — wraps a coroutine function shape
async def _double(state):
    state = dict(state or {})
    state["x"] = state.get("x", 0) * 2
    return state


async def _add_one(state):
    state = dict(state or {})
    state["x"] = state.get("x", 0) + 1
    return state


async def _explode(state):
    raise RuntimeError("inner failed")


# -------------------- as_node basic --------------------


@pytest.mark.asyncio
async def test_as_node_runs_inner_workflow():
    from largestack.workflow import Workflow
    from largestack._workflow.sub_graph import as_node

    inner = Workflow("inner")
    inner.add_node("double", _double)
    sub = as_node(inner)

    result = await sub({"x": 5})
    assert result["x"] == 10


@pytest.mark.asyncio
async def test_as_node_returns_subworkflow_node_type():
    import asyncio
    from largestack.workflow import Workflow
    from largestack._workflow.sub_graph import as_node, SubWorkflowNode

    sub = as_node(Workflow("inner"))
    # Returns a real async function so DAGWorkflow can detect it
    assert asyncio.iscoroutinefunction(sub)
    # The underlying SubWorkflowNode is attached for introspection
    assert isinstance(sub.sub_node, SubWorkflowNode)


@pytest.mark.asyncio
async def test_subworkflow_node_has_name_property():
    from largestack.workflow import Workflow
    from largestack._workflow.sub_graph import as_node

    inner = Workflow("my-named-inner")
    sub = as_node(inner)
    assert sub.sub_node.name == "my-named-inner"


@pytest.mark.asyncio
async def test_subworkflow_passthrough_state():
    """Outer state propagates into inner when passthrough=True (default)."""
    from largestack.workflow import Workflow
    from largestack._workflow.sub_graph import as_node

    captured = {}

    async def capture(state):
        state = dict(state or {})
        captured.update(state)
        return state

    inner = Workflow("inner")
    inner.add_node("capture", capture)
    sub = as_node(inner)
    await sub({"outer_key": "outer_value", "x": 1})
    assert captured.get("outer_key") == "outer_value"


@pytest.mark.asyncio
async def test_subworkflow_state_mapping_renames_input():
    from largestack.workflow import Workflow
    from largestack._workflow.sub_graph import as_node

    captured = {}

    async def capture(state):
        captured.update(state or {})
        return state

    inner = Workflow("inner")
    inner.add_node("capture", capture)

    sub = as_node(
        inner,
        state_mapping={"applicant_pan": "pan"},
        passthrough=False,  # only use mapped keys
    )
    await sub({"applicant_pan": "ABCDE1234F"})
    assert captured.get("pan") == "ABCDE1234F"
    assert "applicant_pan" not in captured


@pytest.mark.asyncio
async def test_subworkflow_output_mapping_renames_output():
    from largestack.workflow import Workflow
    from largestack._workflow.sub_graph import as_node

    async def emit(state):
        state = dict(state or {})
        state["inner_result"] = "ok"
        return state

    inner = Workflow("inner")
    inner.add_node("emit", emit)

    sub = as_node(inner, output_mapping={"inner_result": "kyc_result"})
    out = await sub({})
    assert out.get("kyc_result") == "ok"


# -------------------- isolate_errors --------------------


@pytest.mark.asyncio
async def test_subworkflow_isolate_errors_swallows():
    from largestack.workflow import Workflow
    from largestack._workflow.sub_graph import as_node

    inner = Workflow("inner")
    inner.add_node("explode", _explode)

    sub = as_node(inner, isolate_errors=True)
    result = await sub({"x": 1})
    assert "_subgraph_error" in result
    assert "inner failed" in result["_subgraph_error"]


@pytest.mark.asyncio
async def test_subworkflow_propagates_errors_when_not_isolated():
    from largestack.workflow import Workflow
    from largestack._workflow.sub_graph import as_node

    inner = Workflow("inner")
    inner.add_node("explode", _explode)

    sub = as_node(inner, isolate_errors=False)
    with pytest.raises(RuntimeError, match="inner failed"):
        await sub({"x": 1})


# -------------------- WorkflowComposer --------------------


@pytest.mark.asyncio
async def test_composer_builds_workflow_with_subgraphs():
    from largestack.workflow import Workflow
    from largestack._workflow.sub_graph import WorkflowComposer

    inner1 = Workflow("inner1")
    inner1.add_node("add", _add_one)

    inner2 = Workflow("inner2")
    inner2.add_node("double", _double)

    composer = WorkflowComposer("outer")
    composer.add_subgraph("step1", inner1)
    composer.add_subgraph("step2", inner2, deps=["step1"])

    outer = composer.build()
    # Outer is a Workflow
    assert outer.name == "outer"


@pytest.mark.asyncio
async def test_composer_runs_end_to_end():
    from largestack.workflow import Workflow
    from largestack._workflow.sub_graph import WorkflowComposer

    inner1 = Workflow("inner1")
    inner1.add_node("add", _add_one)

    composer = WorkflowComposer("outer")
    composer.add_subgraph("apply_inner1", inner1)
    outer = composer.build()

    result = await outer.run({"x": 10})
    # Outer state has the result of inner1 — x went from 10 → 11
    # Result shape varies by impl; just check the increment landed
    found = False
    for v in (result or {}).values():
        if isinstance(v, dict) and v.get("x") == 11:
            found = True
            break
    if not found and isinstance(result, dict):
        # Maybe Workflow returns flat
        found = result.get("x") == 11
    assert found, f"x=11 not found in result: {result}"


@pytest.mark.asyncio
async def test_composer_supports_scalar_nodes():
    from largestack._workflow.sub_graph import WorkflowComposer

    composer = WorkflowComposer("mixed")
    composer.add_node("plain", _add_one)
    outer = composer.build()
    assert outer.name == "mixed"


def test_composer_requires_node_name():
    from largestack.workflow import Workflow
    from largestack._workflow.sub_graph import WorkflowComposer

    composer = WorkflowComposer()
    with pytest.raises(ValueError, match="node_name"):
        composer.add_subgraph("", Workflow("inner"))
