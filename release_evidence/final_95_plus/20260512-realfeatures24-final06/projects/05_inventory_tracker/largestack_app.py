from largestack import Agent, Team, Orchestrator
from largestack.testing import TestModel

async def run_largestack_smoke() -> dict:
    features = []
    evidence = {}

    # orchestrator_router
    classifier = Agent(name="classifier", llm="deepseek/deepseek-chat", max_turns=1)
    specialist = Agent(name="billing", llm="deepseek/deepseek-chat", max_turns=1)
    orch = Orchestrator(strategy="router", classifier=classifier, routes={"billing": specialist}, default_route="billing")
    with classifier.override(model=TestModel("billing")), specialist.override(model=TestModel("routed ok")):
        route_result = await orch.run("route this")
    route_output = route_result.output
    features.append("orchestrator_router")
    evidence["orchestrator_strategy"] = "router"
    evidence["route_output"] = route_output

    # team_parallel
    agent_a = Agent(name="agent_a", llm="deepseek/deepseek-chat", max_turns=1)
    agent_b = Agent(name="agent_b", llm="deepseek/deepseek-chat", max_turns=1)
    team = Team(agents=[agent_a, agent_b], strategy="parallel", cost_budget=0.2)
    with agent_a.override(model=TestModel("a")), agent_b.override(model=TestModel("b")):
        team_result = await team.run("task")
    team_output = team_result.content
    features.append("team_parallel")
    evidence["team_strategy"] = "parallel"
    evidence["team_output"] = team_output

    return {"status": "ok", "features": features, "evidence": evidence}
