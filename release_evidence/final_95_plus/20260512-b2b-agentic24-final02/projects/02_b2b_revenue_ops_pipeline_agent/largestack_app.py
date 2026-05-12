import asyncio
from largestack import Agent, Team
from largestack.testing import TestModel
from largestack.memory import create_memory

async def run_largestack_smoke() -> dict:
    """Execute selected LARGESTACK features: team_sequential and memory_isolation."""
    features = []
    evidence = {}

    # --- team_sequential ---
    agent_a = Agent(name="agent_a", llm="deepseek/deepseek-chat", max_turns=1)
    agent_b = Agent(name="agent_b", llm="deepseek/deepseek-chat", max_turns=1)
    team = Team(agents=[agent_a, agent_b], strategy="sequential", cost_budget=0.2)
    with agent_a.override(model=TestModel("output_a")), agent_b.override(model=TestModel("output_b")):
        team_result = await team.run("process sequentially")
    features.append("team_sequential")
    evidence["team_strategy"] = "sequential"
    evidence["team_output"] = team_result.content

    # --- memory_isolation ---
    memory_user1 = create_memory("buffer")
    memory_user2 = create_memory("buffer")
    await memory_user1.add_message({"role": "user", "content": "hello from user1"})
    await memory_user1.add_message({"role": "assistant", "content": "hi user1"})
    await memory_user2.add_message({"role": "user", "content": "hello from user2"})
    messages_user1 = memory_user1.get_messages()
    messages_user2 = memory_user2.get_messages()
    features.append("memory_isolation")
    evidence["memory_messages"] = len(messages_user1) + len(messages_user2)
    # Check no cross-user leak: user2's messages should not appear in user1's memory
    cross_leak = any("user2" in msg.get("content", "") for msg in messages_user1)
    evidence["cross_user_leak"] = cross_leak  # True if leak, False if isolated

    return {"status": "ok", "features": features, "evidence": evidence}

if __name__ == "__main__":
    result = asyncio.run(run_largestack_smoke())
    print(result)
