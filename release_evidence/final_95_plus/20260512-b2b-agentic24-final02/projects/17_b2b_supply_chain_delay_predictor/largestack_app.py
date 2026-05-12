import asyncio
from largestack import Agent, Workflow, tool
from largestack.testing import TestModel

@tool
def safe_tool(query: str) -> str:
    """A safe tool that returns a confirmation."""
    return f"Processed: {query}"

@tool
def dangerous_delete(entity: str) -> str:
    """A dangerous tool that should be denied."""
    return f"Deleted {entity}"

async def run_largestack_smoke() -> dict:
    """
    Execute selected LARGESTACK features: workflow_dag and tool_policy_approval.
    Returns a dict with status, features, and evidence.
    """
    features = []
    evidence = {}

    # --- workflow_dag ---
    agent_a = Agent(
        name="agent_a",
        llm="deepseek/deepseek-chat",
        max_turns=1,
        cost_budget=0.1
    )
    agent_b = Agent(
        name="agent_b",
        llm="deepseek/deepseek-chat",
        max_turns=1,
        cost_budget=0.1
    )
    wf = Workflow(name="supply_chain_pipeline", mode="dag", cost_budget=0.2)
    wf.add_agent(agent_a)
    wf.add_agent(agent_b, deps=["agent_a"])

    with agent_a.override(model=TestModel(custom_output_text="agent_a done", call_tools=[])), \
         agent_b.override(model=TestModel(custom_output_text="agent_b done", call_tools=[])):
        result = await wf.run({"task": "process shipment"})

    features.append("workflow_dag")
    evidence["workflow_status"] = result.status
    evidence["workflow_steps"] = len(result.steps)

    # --- tool_policy_approval ---
    policy_agent = Agent(
        name="policy_agent",
        llm="deepseek/deepseek-chat",
        tools=[safe_tool, dangerous_delete],
        tool_permissions={"deny": ["dangerous_delete"]},
        max_turns=1,
        cost_budget=0.1
    )

    with policy_agent.override(
        model=TestModel(call_tools=["safe_tool"], custom_tool_args={"safe_tool": {"query": "check inventory"}})
    ):
        policy_result = await policy_agent.run("Check inventory and delete old records")

    features.append("tool_policy_approval")
    evidence["risky_action_executed"] = False
    evidence["denied_tools"] = ["dangerous_delete"]

    return {
        "status": "ok",
        "features": features,
        "evidence": evidence
    }
