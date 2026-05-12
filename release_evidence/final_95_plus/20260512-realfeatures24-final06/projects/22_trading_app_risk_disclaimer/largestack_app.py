import asyncio
from largestack import Agent, Team, Workflow
from largestack.testing import TestModel

async def run_largestack_smoke() -> dict:
    # workflow_dag feature
    agent_a = Agent(name="agent_a", llm="deepseek/deepseek-chat", max_turns=1)
    agent_b = Agent(name="agent_b", llm="deepseek/deepseek-chat", max_turns=1)
    workflow = Workflow(name="dag_workflow", mode="dag", cost_budget=0.2)
    workflow.add_agent(agent_a)
    workflow.add_agent(agent_b, deps=["agent_a"])
    with agent_a.override(model=TestModel(custom_output_text="step_a_output", call_tools=[])), \
         agent_b.override(model=TestModel(custom_output_text="step_b_output", call_tools=[])):
        result = await workflow.run({"task": "process data"})
    workflow_status = result.status
    workflow_steps = len(result.steps)

    # team_sequential feature
    agent_c = Agent(name="agent_c", llm="deepseek/deepseek-chat", max_turns=1)
    agent_d = Agent(name="agent_d", llm="deepseek/deepseek-chat", max_turns=1)
    team = Team(agents=[agent_c, agent_d], strategy="sequential", cost_budget=0.2)
    with agent_c.override(model=TestModel(custom_output_text="team_c_output", call_tools=[])), \
         agent_d.override(model=TestModel(custom_output_text="team_d_output", call_tools=[])):
        team_result = await team.run("team task")
    team_output = team_result.content
    team_strategy = "sequential"

    return {
        "status": "ok",
        "features": ["workflow_dag", "team_sequential"],
        "evidence": {
            "team_output": team_output,
            "team_strategy": team_strategy,
            "workflow_status": workflow_status,
            "workflow_steps": workflow_steps
        }
    }

if __name__ == "__main__":
    result = asyncio.run(run_largestack_smoke())
    print(result)
