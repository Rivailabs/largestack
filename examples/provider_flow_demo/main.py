"""Provider-switchable workflow demo.

Runs offline by default with TestModel so users can see the flow without an API
key. Set LARGESTACK_FLOW_DEMO_LIVE=1 plus LARGESTACK_DEFAULT_MODEL to run the
same flow against a real provider.

Examples:

    python examples/provider_flow_demo/main.py

    LARGESTACK_FLOW_DEMO_LIVE=1 \
    LARGESTACK_OPENAI_API_KEY=... \
    LARGESTACK_DEFAULT_MODEL=openai/gpt-4o-mini \
    python examples/provider_flow_demo/main.py

    LARGESTACK_FLOW_DEMO_LIVE=1 \
    LARGESTACK_ANTHROPIC_API_KEY=... \
    LARGESTACK_DEFAULT_MODEL=anthropic/claude-sonnet-4-6 \
    python examples/provider_flow_demo/main.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from largestack import Agent, Workflow
from largestack.testing import TestModel


FLOW_MERMAID = """flowchart LR
    U[User task] --> I[Intake agent]
    I --> P[Planner agent]
    P --> R[Responder agent]
    R --> O[Final answer]
"""


def selected_model() -> str:
    return os.environ.get("LARGESTACK_DEFAULT_MODEL", "deepseek/deepseek-chat")


def build_agents(model: str) -> tuple[Agent, Agent, Agent]:
    intake = Agent(
        name="intake",
        llm=model,
        instructions="Extract the user's goal, constraints, and success criteria.",
        guardrails=False,
        cost_budget=0.05,
        retries=1,
    )
    planner = Agent(
        name="planner",
        llm=model,
        instructions="Create a concise execution plan from the intake summary.",
        guardrails=False,
        cost_budget=0.05,
        retries=1,
    )
    responder = Agent(
        name="responder",
        llm=model,
        instructions="Write the final user-facing response from the plan.",
        guardrails=False,
        cost_budget=0.05,
        retries=1,
    )
    return intake, planner, responder


async def run_demo() -> None:
    model = selected_model()
    live = os.environ.get("LARGESTACK_FLOW_DEMO_LIVE", "").lower() in {"1", "true", "yes"}
    agents = build_agents(model)
    intake, planner, responder = agents

    workflow = Workflow("provider-flow-demo", mode="dag", cost_budget=0.20)
    workflow.add_agent(intake)
    workflow.add_agent(planner, deps=["intake"])
    workflow.add_agent(responder, deps=["planner"])

    task = (
        "Build a customer-support AI that can classify tickets, search docs, "
        "draft an answer, and escalate risky cases."
    )

    print("Largestack provider flow demo")
    print(f"Mode: {'live provider' if live else 'offline deterministic'}")
    print(f"Model string: {model}")
    print("\nFlow:")
    print(FLOW_MERMAID)

    try:
        if live:
            result = await workflow.run({"task": task})
        else:
            with (
                intake.override(model=TestModel(custom_output_text="Goal: support AI with ticket classification, RAG, drafting, and escalation.")),
                planner.override(model=TestModel(custom_output_text="Plan: intake ticket -> classify -> retrieve docs -> draft answer -> escalate if risky.")),
                responder.override(model=TestModel(custom_output_text="Final: build the flow as a guarded DAG with RAG and human escalation for risky tickets.")),
            ):
                result = await workflow.run({"task": task})

        print("\nSteps:")
        for step in result.steps:
            print(f"- {step['name']}: {step['output']}")

        print("\nFinal output:")
        print(result.final_output)
        print(f"\nStatus: {result.status}")
        print(f"Trace ID: {result.trace_id}")
    finally:
        for agent in agents:
            await agent.aclose()


if __name__ == "__main__":
    asyncio.run(run_demo())
