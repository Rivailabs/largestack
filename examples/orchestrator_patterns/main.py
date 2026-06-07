"""Public Orchestrator examples.

Run with:
    python examples/orchestrator_patterns/main.py

This file uses TestModel/FunctionModel, so it does not call a real LLM.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow running this file directly from the source tree without installing.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from largestack import Agent, FunctionModel, Orchestrator, TestModel


async def dag_example() -> None:
    extractor = Agent(name="extractor")
    validator = Agent(name="validator")
    reporter = Agent(name="reporter")
    orch = Orchestrator(
        name="demo-dag",
        strategy="dag",
        agents=[extractor, validator, reporter],
        flow=[("extractor", "validator"), ("validator", "reporter")],
    )
    with (
        extractor.override(model=TestModel("extracted")),
        validator.override(model=TestModel("valid")),
        reporter.override(model=TestModel("report")),
    ):
        result = await orch.run({"task": "extract, validate, and report"})
    print("DAG:", result.output)


async def router_example() -> None:
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
        billing.override(model=TestModel("billing answer")),
    ):
        result = await orch.run("I was charged twice")
    print("Router:", result.output, result.metadata["router_stats"])


async def supervisor_example() -> None:
    manager = Agent(name="manager")
    writer = Agent(name="writer")
    reviewer = Agent(name="reviewer")

    def manager_logic(messages, info):
        if info["attempt"] == 1:
            return "writer\nDraft the summary"
        return "FINAL_ANSWER"

    orch = Orchestrator(
        strategy="supervisor",
        supervisor_agent=manager,
        routes={"writer": writer, "reviewer": reviewer},
        max_iterations=2,
    )
    with (
        manager.override(model=FunctionModel(manager_logic)),
        writer.override(model=TestModel("summary drafted")),
    ):
        result = await orch.run("prepare a short summary")
    print("Supervisor:", result.output, result.steps)


async def map_reduce_example() -> None:
    mapper = Agent(name="mapper")
    reducer = Agent(name="reducer")
    orch = Orchestrator(strategy="map_reduce", mapper=mapper, reducer=reducer, max_concurrency=2)
    with (
        mapper.override(model=TestModel("mapped item")),
        reducer.override(model=TestModel("combined summary")),
    ):
        result = await orch.run({"items": ["doc A", "doc B", "doc C"]})
    print("Map-reduce:", result.output, result.metadata)


async def main() -> None:
    await dag_example()
    await router_example()
    await supervisor_example()
    await map_reduce_example()


if __name__ == "__main__":
    asyncio.run(main())
