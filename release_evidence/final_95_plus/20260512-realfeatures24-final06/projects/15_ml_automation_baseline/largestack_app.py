import asyncio
from largestack import Agent, Orchestrator, Team
from largestack.testing import TestModel


async def run_largestack_smoke() -> dict:
    """Execute selected LARGESTACK features: map-reduce and sequential team.
    Uses TestModel overrides to avoid network calls.
    Returns a dict with status, features, and evidence.
    """
    features = []
    evidence = {}

    # --- Orchestrator map-reduce ---
    mapper = Agent(name="mapper", llm="deepseek/deepseek-chat", max_turns=1)
    reducer = Agent(name="reducer", llm="deepseek/deepseek-chat", max_turns=1)
    orch = Orchestrator(strategy="map_reduce", mapper=mapper, reducer=reducer)
    items = ["item1", "item2", "item3"]
    with mapper.override(model=TestModel("mapped")), reducer.override(model=TestModel("summary")):
        result = await orch.run({"items": items})
    features.append("orchestrator_map_reduce")
    evidence["orchestrator_strategy"] = "map_reduce"
    evidence["map_items"] = len(items)

    # --- Team sequential ---
    agent_a = Agent(name="agent_a", llm="deepseek/deepseek-chat", max_turns=1)
    agent_b = Agent(name="agent_b", llm="deepseek/deepseek-chat", max_turns=1)
    team = Team(agents=[agent_a, agent_b], strategy="sequential", cost_budget=0.2)
    with agent_a.override(model=TestModel("output_a")), agent_b.override(model=TestModel("output_b")):
        team_result = await team.run("sequential task")
    features.append("team_sequential")
    evidence["team_strategy"] = "sequential"
    evidence["team_output"] = team_result.content

    return {
        "status": "ok",
        "features": features,
        "evidence": evidence
    }


if __name__ == "__main__":
    result = asyncio.run(run_largestack_smoke())
    print(result)
