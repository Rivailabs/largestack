import os
from largestack import Agent, Orchestrator
from largestack.testing import TestModel
from largestack.memory import create_memory


async def run_largestack_smoke() -> dict:
    """
    Execute selected Largestack features: orchestrator_router and memory_isolation.
    Returns a dict with status, features list, and evidence.
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
    memory_user1 = create_memory("buffer")
    memory_user2 = create_memory("buffer")
    await memory_user1.add_message({"role": "user", "content": "hello user1"})
    await memory_user2.add_message({"role": "user", "content": "hello user2"})
    messages_user1 = memory_user1.get_messages()
    messages_user2 = memory_user2.get_messages()
    # Check isolation: user1 should not see user2's message
    cross_user_leak = any(
        msg.get("content") == "hello user2" for msg in messages_user1
    )
    features.append("memory_isolation")
    evidence["memory_messages"] = len(messages_user1) + len(messages_user2)
    evidence["cross_user_leak"] = cross_user_leak

    return {
        "status": "ok",
        "features": features,
        "evidence": evidence
    }
