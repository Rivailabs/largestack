"""v0.14.1 — doc-alignment fixes.

Adds developer-friendly aliases so the API matches what intuitive docs and
the original LARGESTACK framework spec describe:

- Workflow.add_agent(agent, deps=...)        # alias for add_node(agent.name, agent)
- Guardrails.create(...)                     # classmethod alias for create_guardrails
- examples/local_llm_ollama/                 # missing example folder

These don't change any existing behaviour — just give developers two ways to
spell the same thing. Old code keeps working unchanged.
"""

from __future__ import annotations
import asyncio
from pathlib import Path

import pytest

from largestack import Agent, Guardrails, Workflow, create_guardrails, tool
from largestack.testing import TestModel


# -----------------------------------------------------------------
# Workflow.add_agent — alias for add_node when handler is an Agent
# -----------------------------------------------------------------


def test_workflow_add_agent_registers_under_agent_name():
    """add_agent(extractor) should be equivalent to add_node('extractor', extractor)."""
    a = Agent(name="extractor", instructions="…", llm="openai/gpt-4o-mini")
    wf = Workflow(name="t", mode="dag")
    wf.add_agent(a)

    impl = wf._impl
    assert "extractor" in impl.nodes


def test_workflow_add_agent_propagates_deps():
    """add_agent(b, deps=['a']) sets the dependency correctly."""
    a = Agent(name="a", instructions="…", llm="openai/gpt-4o-mini")
    b = Agent(name="b", instructions="…", llm="openai/gpt-4o-mini")
    wf = Workflow(name="t", mode="dag")
    wf.add_agent(a)
    wf.add_agent(b, deps=["a"])

    impl = wf._impl
    assert impl.nodes["b"].deps == ["a"]


def test_workflow_add_agent_rejects_non_agent_objects():
    """add_agent() expects an Agent-shaped object, not a raw callable."""
    wf = Workflow(name="t", mode="dag")

    async def bare_handler(state):
        return state

    with pytest.raises(TypeError, match="add_agent.*expects.*Agent"):
        wf.add_agent(bare_handler)


def test_workflow_add_agent_runs_end_to_end_with_test_model():
    """add_agent → run() should produce dict result with agent outputs."""
    a = Agent(name="extr", instructions="…", llm="openai/gpt-4o-mini")
    b = Agent(name="vald", instructions="…", llm="openai/gpt-4o-mini")
    wf = Workflow(name="pipe", mode="dag", cost_budget=1.0)

    with a.override(model=TestModel(custom_output_text="extracted")):
        with b.override(model=TestModel(custom_output_text="validated")):
            wf.add_agent(a)
            wf.add_agent(b, deps=["extr"])

            result = asyncio.run(wf.run({"task": "go"}))

    assert isinstance(result, dict)
    assert result["extr_output"] == "extracted"
    assert result["vald_output"] == "validated"
    assert "_total_cost" in result


# -----------------------------------------------------------------
# Guardrails.create() — classmethod alias for create_guardrails
# -----------------------------------------------------------------


def test_guardrails_create_classmethod_exists():
    assert hasattr(Guardrails, "create")
    assert callable(Guardrails.create)


def test_guardrails_create_returns_pipeline():
    g = Guardrails.create(pii=True, injection=True)
    # Same shape as create_guardrails(...)
    expected = create_guardrails(pii=True, injection=True)
    assert type(g).__name__ == type(expected).__name__
    assert len(g.guards) == len(expected.guards)


def test_guardrails_create_passes_through_all_kwargs():
    """All factory kwargs should flow through."""
    g = Guardrails.create(
        pii=True,
        injection=False,
        toxicity=True,
        topic_blocklist=["weapons", "drugs"],
        pii_action="block",
        injection_sensitivity="high",
    )
    # PII + toxicity = 2 guards (no injection because we disabled it)
    assert len(g.guards) >= 2


def test_guardrails_create_does_not_accept_schema_kwarg():
    """schema= belongs on TypedAgent's output_model, not on guardrails.

    We accept **kwargs and silently ignore unknown keys to avoid breaking old
    code, but no schema= guard is wired up.
    """
    g = Guardrails.create(pii=True, schema={"type": "object"})  # noqa
    # No schema-validation guard added
    guard_types = [type(x).__name__ for x in g.guards]
    assert not any("Schema" in t for t in guard_types)


# -----------------------------------------------------------------
# examples/local_llm_ollama/ — folder must exist with starter files
# -----------------------------------------------------------------


def test_local_llm_ollama_example_exists():
    """The example folder previously claimed in docs must actually exist."""
    repo_root = Path(__file__).resolve().parents[2]
    folder = repo_root / "examples" / "local_llm_ollama"
    assert folder.is_dir(), f"missing: {folder}"
    assert (folder / "README.md").is_file()
    assert (folder / "agent.py").is_file()
    assert (folder / "chat_only.py").is_file()


def test_local_llm_ollama_agent_py_imports_cleanly():
    """The example file should at least parse and expose make_agent()."""
    import importlib.util

    repo_root = Path(__file__).resolve().parents[2]
    path = repo_root / "examples" / "local_llm_ollama" / "agent.py"
    spec = importlib.util.spec_from_file_location("ollama_agent_example", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert callable(mod.make_agent)
    a = mod.make_agent()
    assert a.name == "local-loan-agent"
    assert a.llm.startswith(("ollama/llama3.1", "openai/llama3.1"))
