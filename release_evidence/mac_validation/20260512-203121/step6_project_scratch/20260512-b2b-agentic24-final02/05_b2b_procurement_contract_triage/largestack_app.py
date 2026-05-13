from largestack import Agent, Team, Orchestrator
from largestack.testing import TestModel

async def run_largestack_smoke() -> dict:
    # orchestrator_router feature
    classifier = Agent(name="classifier", llm="deepseek/deepseek-chat", max_turns=1)
    specialist = Agent(name="billing", llm="deepseek/deepseek-chat", max_turns=1)
    orch = Orchestrator(strategy="router", classifier=classifier, routes={"billing": specialist}, default_route="billing")
    with classifier.override(model=TestModel(custom_output_text="billing", call_tools=[])), \
         specialist.override(model=TestModel(custom_output_text="routed ok", call_tools=[])):
        route_result = await orch.run("route this")
    route_output = route_result.output
    orchestrator_strategy = "router"

    # team_parallel feature
    agent_a = Agent(name="agent_a", llm="deepseek/deepseek-chat", max_turns=1)
    agent_b = Agent(name="agent_b", llm="deepseek/deepseek-chat", max_turns=1)
    team = Team(agents=[agent_a, agent_b], strategy="parallel", cost_budget=0.2)
    with agent_a.override(model=TestModel(custom_output_text="output_a", call_tools=[])), \
         agent_b.override(model=TestModel(custom_output_text="output_b", call_tools=[])):
        team_result = await team.run("task")
    team_output = team_result.content
    team_strategy = "parallel"

    return {
        "status": "ok",
        "features": ["orchestrator_router", "team_parallel"],
        "evidence": {
            "orchestrator_strategy": orchestrator_strategy,
            "route_output": route_output,
            "team_output": team_output,
            "team_strategy": team_strategy
        }
    }
