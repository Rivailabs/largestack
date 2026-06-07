"""v1.0.0 — close the remaining 4 P0/P1 doc-alignment gaps.

- WorkflowResult: dict-and-object hybrid (final_output, steps, total_cost,
  guardrail_events, trace_id, status). Old ``result["key"]`` access keeps
  working unchanged.
- LangfuseTracer.attach(agent): context manager that activates the tracer
  globally for its block and auto-flushes on exit.
- known-limitations.md: stale RBAC/Vault/Helm claims removed.
- Helm chart versions bumped to 1.0.0.
"""

from __future__ import annotations
import asyncio
from pathlib import Path

import pytest

from largestack import Agent, Workflow
from largestack.testing import TestModel
from largestack.workflow import WorkflowResult


# ---------------------------------------------------------------------------
# WorkflowResult: behaves as both dict and object
# ---------------------------------------------------------------------------


def test_workflow_run_returns_workflow_result():
    a = Agent(name="extr", instructions="…", llm="openai/gpt-4o-mini")
    b = Agent(name="vald", instructions="…", llm="openai/gpt-4o-mini")
    wf = Workflow(name="pipe", mode="dag")

    with a.override(model=TestModel(custom_output_text="extracted")):
        with b.override(model=TestModel(custom_output_text="validated")):
            wf.add_agent(a)
            wf.add_agent(b, deps=["extr"])
            result = asyncio.run(wf.run({"task": "go"}))

    assert isinstance(result, WorkflowResult)
    assert isinstance(result, dict)  # also a dict


def test_workflow_result_dict_access_still_works():
    """Old code using result['key'] must keep working unchanged."""
    a = Agent(name="alpha", instructions="…", llm="openai/gpt-4o-mini")
    wf = Workflow(name="t", mode="dag")
    with a.override(model=TestModel(custom_output_text="hello")):
        wf.add_agent(a)
        result = asyncio.run(wf.run({"task": "x"}))

    # dict access — was the only API in v0.14.1
    assert result["alpha_output"] == "hello"
    assert "_total_cost" in result


def test_workflow_result_attribute_access():
    """New attribute access matches the developer-doc API shape."""
    a = Agent(name="alpha", instructions="…", llm="openai/gpt-4o-mini")
    b = Agent(name="beta", instructions="…", llm="openai/gpt-4o-mini")
    wf = Workflow(name="t", mode="dag")

    with a.override(model=TestModel(custom_output_text="aaa")):
        with b.override(model=TestModel(custom_output_text="bbb")):
            wf.add_agent(a)
            wf.add_agent(b, deps=["alpha"])
            result = asyncio.run(wf.run({"task": "x"}))

    assert result.final_output == "bbb"
    assert isinstance(result.steps, list)
    assert len(result.steps) == 2
    assert result.steps[0]["name"] == "alpha"
    assert result.steps[0]["output"] == "aaa"
    assert result.steps[1]["name"] == "beta"
    assert isinstance(result.total_cost, float)
    assert isinstance(result.guardrail_events, list)
    assert isinstance(result.trace_id, str) and len(result.trace_id) > 0
    assert result.status == "completed"


def test_workflow_result_steps_in_execution_order():
    a = Agent(name="step_a", instructions="…", llm="openai/gpt-4o-mini")
    b = Agent(name="step_b", instructions="…", llm="openai/gpt-4o-mini")
    c = Agent(name="step_c", instructions="…", llm="openai/gpt-4o-mini")
    wf = Workflow(name="t", mode="dag")

    with a.override(model=TestModel(custom_output_text="A")):
        with b.override(model=TestModel(custom_output_text="B")):
            with c.override(model=TestModel(custom_output_text="C")):
                wf.add_agent(a)
                wf.add_agent(b, deps=["step_a"])
                wf.add_agent(c, deps=["step_b"])
                result = asyncio.run(wf.run({"task": "x"}))

    names = [s["name"] for s in result.steps]
    assert names == ["step_a", "step_b", "step_c"]
    assert result.final_output == "C"


def test_workflow_result_empty_state_safe():
    """Even with no nodes producing _output keys, attributes are safe."""
    state = {"task": "raw", "_total_cost": 0.0}
    wr = WorkflowResult.from_state(state, workflow_name="empty")
    assert wr.final_output == {"task": "raw"}
    assert wr.steps == []
    assert wr.total_cost == 0.0
    assert wr.guardrail_events == []
    assert wr.status == "completed"


def test_workflow_result_error_status():
    state = {"_error": "something broke", "_total_cost": 0.0}
    wr = WorkflowResult.from_state(state)
    assert wr.status == "error"


# ---------------------------------------------------------------------------
# LangfuseTracer.attach() — context manager
# ---------------------------------------------------------------------------


def test_langfuse_attach_method_exists():
    from largestack._integrations.langfuse_adapter import LangfuseTracer

    assert hasattr(LangfuseTracer, "attach")


def test_langfuse_attach_works_as_context_manager():
    from largestack._integrations.langfuse_adapter import (
        LangfuseTracer,
        LangfuseConfig,
    )

    cfg = LangfuseConfig(
        public_key="pk-test",
        secret_key="sk-test",
        host="https://cloud.langfuse.com",
        environment="test",
        enable=False,  # disabled — no real network
        allow_non_india_host=True,
    )
    tracer = LangfuseTracer(cfg)

    a = Agent(name="t", instructions="…", llm="openai/gpt-4o-mini")
    with tracer.attach(a) as t2:
        assert t2 is tracer  # __enter__ returns the tracer

    # No exception = pass


def test_langfuse_attach_swaps_global_tracer_for_block():
    """Inside attach() block, the module-level global is set."""
    import largestack._integrations.langfuse_adapter as mod
    from largestack._integrations.langfuse_adapter import (
        LangfuseTracer,
        LangfuseConfig,
    )

    before = mod._global_tracer
    cfg = LangfuseConfig(
        public_key="pk-x",
        secret_key="sk-x",
        environment="test",
        enable=False,
        allow_non_india_host=True,
    )
    tracer = LangfuseTracer(cfg)

    with tracer.attach():
        assert mod._global_tracer is tracer

    # Restored on exit
    assert mod._global_tracer is before


def test_langfuse_attach_works_without_agent_arg():
    """Attach should work whether or not an agent is passed."""
    from largestack._integrations.langfuse_adapter import (
        LangfuseTracer,
        LangfuseConfig,
    )

    tracer = LangfuseTracer(
        LangfuseConfig(
            public_key="pk",
            secret_key="sk",
            environment="test",
            enable=False,
            allow_non_india_host=True,
        )
    )
    with tracer.attach():
        pass


# ---------------------------------------------------------------------------
# known-limitations.md is no longer stale
# ---------------------------------------------------------------------------


def test_known_limitations_no_stale_helm_claim():
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "docs" / "known-limitations.md").read_text(encoding="utf-8")
    assert "No published Helm chart" not in text, (
        "known-limitations.md still claims no Helm chart, but charts exist in deploy/helm/"
    )


def test_known_limitations_no_stale_kms_claim():
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "docs" / "known-limitations.md").read_text(encoding="utf-8")
    assert "no KMS / cloud secret-manager integration" not in text, (
        "known-limitations.md still claims no KMS — but vault.py supports AWS/Azure/Vault"
    )


def test_known_limitations_no_stale_rbac_claim():
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "docs" / "known-limitations.md").read_text(encoding="utf-8")
    assert "in-memory, no tenant isolation" not in text, (
        "known-limitations.md still claims RBAC has no tenant isolation, but check_for_tenant() exists"
    )


# ---------------------------------------------------------------------------
# Helm chart version matches package version
# ---------------------------------------------------------------------------


def test_helm_chart_version_matches_package():
    repo_root = Path(__file__).resolve().parents[2]
    chart = (repo_root / "deploy" / "helm" / "largestack" / "Chart.yaml").read_text()
    assert "version: 1.0.0" in chart
    assert 'appVersion: "1.0.0"' in chart


def test_helm_values_image_tag_matches():
    repo_root = Path(__file__).resolve().parents[2]
    values = (repo_root / "deploy" / "helm" / "largestack" / "values.yaml").read_text()
    assert 'tag: "1.0.0"' in values


def test_helm_no_legacy_versions_remain():
    """Make sure no 0.4.0 / 0.10.0 strings linger anywhere in deploy/helm/."""
    repo_root = Path(__file__).resolve().parents[2]
    for path in (repo_root / "deploy" / "helm").rglob("*"):
        if not path.is_file() or path.suffix not in {".yaml", ".yml", ".md", ".tpl"}:
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        for stale in ("0.4.0", "0.10.0"):
            # Allow inside comments warning about legacy, but flag bare uses
            assert stale not in content, f"{path} still references stale version {stale}"


# ---------------------------------------------------------------------------
# Bug fix: WorkflowResult derived attrs reflect dict mutations (not cached)
# ---------------------------------------------------------------------------


def test_workflow_result_steps_reflect_dict_mutation():
    """Mutating the result dict after construction must update derived attrs."""
    from largestack.workflow import WorkflowResult

    wr = WorkflowResult.from_state({"a_output": "x", "_total_cost": 0.1})
    assert [s["name"] for s in wr.steps] == ["a"]
    wr["new_output"] = "y"
    wr["new_cost"] = 0.2
    # steps must include the new node — not return a stale cached list
    names = [s["name"] for s in wr.steps]
    assert "new" in names
    assert wr.final_output == "y"


def test_workflow_result_total_cost_reflects_mutation():
    from largestack.workflow import WorkflowResult

    wr = WorkflowResult.from_state({"_total_cost": 1.0})
    assert wr.total_cost == 1.0
    wr["_total_cost"] = 5.5
    assert wr.total_cost == 5.5  # property reads current dict state


def test_workflow_result_pickle_round_trip():
    """Pickling must preserve trace_id and produce a working WorkflowResult."""
    import pickle
    from largestack.workflow import WorkflowResult

    wr = WorkflowResult.from_state({"a_output": "x", "_total_cost": 0.1})
    original_trace = wr.trace_id

    blob = pickle.dumps(wr)
    restored = pickle.loads(blob)

    assert isinstance(restored, WorkflowResult)
    assert restored["a_output"] == "x"
    assert restored.trace_id == original_trace  # not regenerated
    assert restored.steps == wr.steps  # derived attr still works
    assert restored.final_output == "x"


def test_workflow_result_deepcopy_preserves_attrs():
    import copy
    from largestack.workflow import WorkflowResult

    wr = WorkflowResult.from_state({"a_output": "x"})
    wr2 = copy.deepcopy(wr)
    # deepcopy returns a plain dict because dict subclasses don't deepcopy their __dict__ by default
    # But because we use properties, even a plain dict subclass instance still computes attrs correctly
    assert isinstance(wr2, WorkflowResult)
    assert wr2["a_output"] == "x"
