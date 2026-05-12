import json
import os
from largestack import Agent, Orchestrator
from largestack.testing import TestModel
from largestack.memory import create_memory

async def run_largestack_smoke() -> dict:
    """
    Execute selected LARGESTACK features: orchestrator_router and memory_isolation.
    Returns status, features list, and evidence dict.
    """
    features = []
    evidence = {}

    # --- orchestrator_router ---
    classifier = Agent(
        name="classifier",
        llm="deepseek/deepseek-chat",
        max_turns=1,
        cost_budget=0.1
    )
    specialist = Agent(
        name="billing",
        llm="deepseek/deepseek-chat",
        max_turns=1,
        cost_budget=0.1
    )
    orch = Orchestrator(
        strategy="router",
        classifier=classifier,
        routes={"billing": specialist},
        default_route="billing"
    )
    with classifier.override(model=TestModel("billing")), specialist.override(model=TestModel("routed ok")):
        route_result = await orch.run("route this")
    route_output = route_result.output
    features.append("orchestrator_router")
    evidence["orchestrator_strategy"] = "router"
    evidence["route_output"] = route_output

    # --- memory_isolation ---
    memory1 = create_memory("buffer")
    memory2 = create_memory("buffer")
    await memory1.add_message({"role": "user", "content": "hello user1"})
    await memory1.add_message({"role": "assistant", "content": "hi user1"})
    await memory2.add_message({"role": "user", "content": "hello user2"})
    messages1 = memory1.get_messages()
    messages2 = memory2.get_messages()
    # Check isolation: user2's message should not appear in memory1
    cross_user_leak = any("user2" in msg.get("content", "") for msg in messages1)
    features.append("memory_isolation")
    evidence["memory_messages"] = len(messages1)
    evidence["cross_user_leak"] = cross_user_leak

    return {
        "status": "ok",
        "features": features,
        "evidence": evidence
    }
