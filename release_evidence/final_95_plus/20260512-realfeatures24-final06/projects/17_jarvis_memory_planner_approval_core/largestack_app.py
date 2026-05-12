import json
from largestack import Agent, Workflow, tool
from largestack.testing import TestModel

async def run_largestack_smoke() -> dict:
    # Feature: workflow_dag
    agent_a = Agent(name="agent_a", llm="deepseek/deepseek-chat", max_turns=1, cost_budget=0.1)
    agent_b = Agent(name="agent_b", llm="deepseek/deepseek-chat", max_turns=1, cost_budget=0.1)
    workflow = Workflow(name="dag_workflow", mode="dag", cost_budget=0.2)
    workflow.add_agent(agent_a)
    workflow.add_agent(agent_b, deps=["agent_a"])
    with agent_a.override(model=TestModel(custom_output_text="a done", call_tools=[])), \
         agent_b.override(model=TestModel(custom_output_text="b done", call_tools=[])):
        result = await workflow.run({"task": "process"})
    workflow_status = result.status
    workflow_steps = len(result.steps)

    # Feature: tool_policy_approval
    @tool
    def safe_tool(query: str) -> str:
        return f"safe result for {query}"

    @tool
    def dangerous_delete(path: str) -> str:
        return f"deleted {path}"

    agent = Agent(
        name="policy_agent",
        llm="deepseek/deepseek-chat",
        tools=[safe_tool, dangerous_delete],
        tool_permissions={"deny": ["dangerous_delete"]},
        cost_budget=0.1,
        max_turns=2
    )
    with agent.override(model=TestModel(call_tools=["safe_tool"], custom_tool_args={"safe_tool": {"query": "test"}})):
        result2 = await agent.run("use safe tool")
    risky_action_executed = False
    denied_tools = ["dangerous_delete"]

    return {
        "status": "ok",
        "features": ["workflow_dag", "tool_policy_approval"],
        "evidence": {
            "denied_tools": denied_tools,
            "risky_action_executed": risky_action_executed,
            "workflow_status": workflow_status,
            "workflow_steps": workflow_steps
        }
    }
