"""Public Orchestrator facade tests.

These tests protect the developer-facing API so the framework has one simple
entry point for common multi-agent automation patterns.
"""

from __future__ import annotations

import asyncio

from largestack import Agent, FunctionModel, Orchestrator, TestModel


def run(coro):
    return asyncio.run(coro)


def test_orchestrator_supported_strategies_include_public_patterns():
    strategies = set(Orchestrator.supported_strategies())
    assert {
        "sequential",
        "parallel",
        "dag",
        "state_machine",
        "router",
        "supervisor",
        "map_reduce",
    } <= strategies


def test_orchestrator_describe_is_machine_readable():
    a = Agent(name="extractor")
    b = Agent(name="validator")
    orch = Orchestrator(
        strategy="dag", agents=[a, b], flow=[("extractor", "validator")], cost_budget=1.5
    )
    desc = orch.describe()
    assert desc["strategy"] == "dag"
    assert desc["agents"] == ["extractor", "validator"]
    assert desc["flow"] == [("extractor", "validator")]
    assert desc["cost_budget"] == 1.5


def test_router_strategy_dispatches_to_specialist():
    classifier = Agent(name="classifier")
    billing = Agent(name="billing")
    technical = Agent(name="technical")
    orch = Orchestrator(
        strategy="router",
        classifier=classifier,
        routes={"billing": billing, "technical": technical},
        default_route="technical",
    )
    with (
        classifier.override(model=TestModel("billing")),
        billing.override(model=TestModel("billing done")),
    ):
        result = run(orch.run("I was charged twice"))
    assert result.strategy == "router"
    assert result.output == "billing done"
    assert result.metadata["router_stats"]["by_category"]["billing"] == 1


def test_supervisor_strategy_routes_to_specialist():
    supervisor = Agent(name="supervisor")
    writer = Agent(name="writer")
    reviewer = Agent(name="reviewer")
    orch = Orchestrator(
        strategy="supervisor",
        supervisor_agent=supervisor,
        routes={"writer": writer, "reviewer": reviewer},
        max_iterations=2,
    )

    # First routing step chooses writer. Second supervisor response finishes.
    def supervisor_fn(messages, info):
        if info["attempt"] == 1:
            return "writer\nDraft a concise note"
        return "FINAL_ANSWER"

    with (
        supervisor.override(model=FunctionModel(supervisor_fn)),
        writer.override(model=TestModel("draft complete")),
    ):
        result = run(orch.run("prepare a note"))
    assert result.strategy == "supervisor"
    assert result.output == "draft complete"
    assert result.metadata["iterations"] == 1
    assert result.steps[0]["agent_name"] == "writer"


def test_map_reduce_strategy_maps_items_then_reduces():
    mapper = Agent(name="mapper")
    reducer = Agent(name="reducer")
    orch = Orchestrator(strategy="map_reduce", mapper=mapper, reducer=reducer, max_concurrency=2)
    with mapper.override(model=TestModel("mapped")), reducer.override(model=TestModel("summary")):
        result = run(orch.run({"items": ["doc1", "doc2", "doc3"]}))
    assert result.strategy == "map_reduce"
    assert result.output == "summary"
    assert result.metadata["items"] == 3


def test_orchestrator_rejects_unknown_flow_agent():
    a = Agent(name="a")
    orch = Orchestrator(strategy="dag", agents=[a], flow=[("a", "missing")])
    try:
        run(orch.run({"task": "go"}))
    except ValueError as exc:
        assert "Unknown flow destination" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
