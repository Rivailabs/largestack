import json
import os
from largestack import Agent, Team, Orchestrator
from largestack.testing import TestModel, FunctionModel, capture_run_messages
from largestack.memory import create_memory

async def run_largestack_smoke() -> dict:
    """
    Execute selected LARGESTACK features: team_parallel and memory_isolation.
    Returns dict with status, features, and evidence.
    """
    features = []
    evidence = {}

    # --- team_parallel ---
    agent_a = Agent(
        name="agent_a",
        llm="deepseek/deepseek-chat",
        max_turns=1,
        cost_budget=0.1
    )
    agent_b = Agent(
        name="agent_b",
        llm="deepseek/deepseek-chat",
        max_turns=1,
        cost_budget=0.1
    )
    team = Team(
        agents=[agent_a, agent_b],
        strategy="parallel",
        cost_budget=0.2
    )
    with agent_a.override(model=TestModel(custom_output_text="agent_a output", call_tools=[])), \
         agent_b.override(model=TestModel(custom_output_text="agent_b output", call_tools=[])):
        team_result = await team.run("Process audit data")
    team_output = team_result.content
    features.append("team_parallel")
    evidence["team_output"] = team_output
    evidence["team_strategy"] = "parallel"

    # --- memory_isolation ---
    memory_user1 = create_memory("buffer")
    memory_user2 = create_memory("buffer")
    await memory_user1.add_message({"role": "user", "content": "Hello from user1"})
    await memory_user1.add_message({"role": "assistant", "content": "Hi user1"})
    await memory_user2.add_message({"role": "user", "content": "Hello from user2"})
    messages_user1 = memory_user1.get_messages()
    messages_user2 = memory_user2.get_messages()
    # Check isolation: no cross-user leak
    cross_user_leak = False
    for msg in messages_user1:
        if "user2" in msg.get("content", ""):
            cross_user_leak = True
            break
    for msg in messages_user2:
        if "user1" in msg.get("content", ""):
            cross_user_leak = True
            break
    features.append("memory_isolation")
    evidence["memory_messages"] = len(messages_user1) + len(messages_user2)
    evidence["cross_user_leak"] = cross_user_leak

    return {
        "status": "ok",
        "features": features,
        "evidence": evidence
    }
