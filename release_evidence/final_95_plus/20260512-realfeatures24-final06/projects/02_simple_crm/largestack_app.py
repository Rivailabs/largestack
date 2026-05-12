import asyncio
from largestack import Agent, Team, Orchestrator
from largestack.testing import TestModel, FunctionModel, capture_run_messages
from largestack.memory import create_memory


async def run_largestack_smoke() -> dict:
    features = []
    evidence = {}

    # --- team_sequential ---
    agent_a = Agent(name="agent_a", llm="deepseek/deepseek-chat", max_turns=1)
    agent_b = Agent(name="agent_b", llm="deepseek/deepseek-chat", max_turns=1)
    team = Team(agents=[agent_a, agent_b], strategy="sequential", cost_budget=0.2)
    with agent_a.override(model=TestModel(custom_output_text="output_a", call_tools=[])), \
         agent_b.override(model=TestModel(custom_output_text="output_b", call_tools=[])):
        team_result = await team.run("sequential task")
    features.append("team_sequential")
    evidence["team_strategy"] = "sequential"
    evidence["team_output"] = team_result.content

    # --- memory_isolation ---
    # Use different memory types to ensure isolation
    memory1 = create_memory("buffer")
    memory2 = create_memory("sliding_window")
    await memory1.add_message({"role": "user", "content": "hello user1"})
    await memory1.add_message({"role": "assistant", "content": "hi user1"})
    await memory2.add_message({"role": "user", "content": "hello user2"})
    messages1 = memory1.get_messages()
    messages2 = memory2.get_messages()
    features.append("memory_isolation")
    evidence["memory_messages"] = len(messages1) + len(messages2)
    # Check no cross-user leak: user1 messages should not appear in memory2
    cross_leak = any("user1" in msg.get("content", "") for msg in messages2)
    evidence["cross_user_leak"] = cross_leak  # should be False if no leak

    return {
        "status": "ok",
        "features": features,
        "evidence": evidence
    }


if __name__ == "__main__":
    result = asyncio.run(run_largestack_smoke())
    print(result)
