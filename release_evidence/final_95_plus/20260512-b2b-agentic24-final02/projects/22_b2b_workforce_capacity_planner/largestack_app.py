import asyncio
from largestack import Agent, Workflow, Team
from largestack.testing import TestModel

async def run_largestack_smoke() -> dict:
    """
    Execute selected LARGESTACK features: workflow_dag and team_sequential.
    All agents use TestModel overrides to avoid network calls.
    """
    features = []
    evidence = {}

    # --- workflow_dag ---
    agent_a = Agent(name="agent_a", llm="deepseek/deepseek-chat", max_turns=1)
    agent_b = Agent(name="agent_b", llm="deepseek/deepseek-chat", max_turns=1)
    wf = Workflow(name="pipe", mode="dag", cost_budget=0.2)
    wf.add_agent(agent_a)
    wf.add_agent(agent_b, deps=["agent_a"])
    with agent_a.override(model=TestModel("output_a")), agent_b.override(model=TestModel("output_b")):
        result = await wf.run({"task": "go"})
    features.append("workflow_dag")
    evidence["workflow_status"] = result.status
    evidence["workflow_steps"] = len(result.steps)

    # --- team_sequential ---
    agent_c = Agent(name="agent_c", llm="deepseek/deepseek-chat", max_turns=1)
    agent_d = Agent(name="agent_d", llm="deepseek/deepseek-chat", max_turns=1)
    team = Team(agents=[agent_c, agent_d], strategy="sequential", cost_budget=0.2)
    with agent_c.override(model=TestModel("team_c")), agent_d.override(model=TestModel("team_d")):
        team_result = await team.run("team task")
    features.append("team_sequential")
    evidence["team_output"] = team_result.content
    evidence["team_strategy"] = "sequential"

    return {"status": "ok", "features": features, "evidence": evidence}
