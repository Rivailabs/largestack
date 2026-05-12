import asyncio
from largestack import Agent, Team, Orchestrator, tool, create_rag, create_guardrails
from largestack.memory import create_memory
from largestack.testing import TestModel, FunctionModel, capture_run_messages
from largestack.decorators import Agent as TypedAgent, RunContext, ModelRetry
from dataclasses import dataclass
from types import SimpleNamespace

async def run_largestack_smoke() -> dict:
    """Execute selected LARGESTACK features: team_parallel and memory_isolation.
    Returns dict with status, features list, and evidence dict.
    """
    features = []
    evidence = {}

    # --- team_parallel ---
    agent_a = Agent(name="agent_a", llm="deepseek/deepseek-chat", max_turns=1)
    agent_b = Agent(name="agent_b", llm="deepseek/deepseek-chat", max_turns=1)
    team = Team(agents=[agent_a, agent_b], strategy="parallel", cost_budget=0.2)
    with agent_a.override(model=TestModel(custom_output_text="output from agent_a")), \
         agent_b.override(model=TestModel(custom_output_text="output from agent_b")):
        team_result = await team.run("parallel task")
    team_output = team_result.content
    features.append("team_parallel")
    evidence["team_output"] = team_output
    evidence["team_strategy"] = "parallel"

    # --- memory_isolation ---
    memory_user1 = create_memory("buffer")
    memory_user2 = create_memory("buffer")
    await memory_user1.add_message({"role": "user", "content": "hello user1"})
    await memory_user1.add_message({"role": "assistant", "content": "hi user1"})
    await memory_user2.add_message({"role": "user", "content": "hello user2"})
    messages_user1 = memory_user1.get_messages()
    messages_user2 = memory_user2.get_messages()
    # Check isolation: user1's messages should not contain user2's content
    cross_user_leak = any("user2" in msg.get("content", "") for msg in messages_user1)
    features.append("memory_isolation")
    evidence["memory_messages"] = len(messages_user1)
    evidence["cross_user_leak"] = cross_user_leak

    return {
        "status": "ok",
        "features": features,
        "evidence": evidence
    }

if __name__ == "__main__":
    result = asyncio.run(run_largestack_smoke())
    print(result)
