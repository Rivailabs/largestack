import asyncio
from largestack import Agent, Orchestrator, Team
from largestack.testing import TestModel


async def run_largestack_smoke() -> dict:
    """
    Execute selected LARGESTACK features: map_reduce orchestrator and sequential team.
    All agents are overridden with TestModel to avoid network calls.
    """
    # Map-Reduce Orchestrator
    mapper = Agent(
        name="mapper",
        llm="deepseek/deepseek-chat",
        max_turns=1
    )
    reducer = Agent(
        name="reducer",
        llm="deepseek/deepseek-chat",
        max_turns=1
    )
    orch = Orchestrator(
        strategy="map_reduce",
        mapper=mapper,
        reducer=reducer
    )
    items = ["item1", "item2", "item3"]
    with mapper.override(model=TestModel("mapped")), reducer.override(model=TestModel("summary")):
        map_result = await orch.run({"items": items})
    map_items = len(items)
    orchestrator_strategy = "map_reduce"

    # Sequential Team
    agent_a = Agent(
        name="agent_a",
        llm="deepseek/deepseek-chat",
        max_turns=1
    )
    agent_b = Agent(
        name="agent_b",
        llm="deepseek/deepseek-chat",
        max_turns=1
    )
    team = Team(
        agents=[agent_a, agent_b],
        strategy="sequential",
        cost_budget=0.2
    )
    with agent_a.override(model=TestModel("first")), agent_b.override(model=TestModel("second")):
        team_result = await team.run("sequential task")
    team_output = team_result.content
    team_strategy = "sequential"

    return {
        "status": "ok",
        "features": ["orchestrator_map_reduce", "team_sequential"],
        "evidence": {
            "map_items": map_items,
            "orchestrator_strategy": orchestrator_strategy,
            "team_output": team_output,
            "team_strategy": team_strategy
        }
    }


if __name__ == "__main__":
    result = asyncio.run(run_largestack_smoke())
    print(result)
