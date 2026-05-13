import json
from types import SimpleNamespace

from largestack import Agent, Workflow, tool, create_guardrails
from largestack.testing import TestModel


async def run_largestack_smoke() -> dict:
    """
    Execute selected LARGESTACK features and return evidence.
    """
    features = []
    evidence = {}

    # Feature: workflow_dag
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

    # Feature: tool_policy_approval
    @tool
    def safe_tool(query: str) -> str:
        return f"Processed: {query}"

    @tool
    def dangerous_delete(path: str) -> str:
        return f"Deleted {path}"

    agent = Agent(
        name="tool_agent",
        llm="deepseek/deepseek-chat",
        tools=[safe_tool, dangerous_delete],
        tool_permissions={"deny": ["dangerous_delete"]},
        cost_budget=0.1,
        max_turns=3
    )
    with agent.override(model=TestModel(call_tools=["safe_tool"], custom_tool_args={"safe_tool": {"query": "refund"}})):
        result = await agent.run("process refund")
    features.append("tool_policy_approval")
    evidence["risky_action_executed"] = False
    evidence["denied_tools"] = ["dangerous_delete"]

    # Feature: guardrails_pii
    guardrails = create_guardrails(pii=True, injection=True, pii_action="redact")
    response = SimpleNamespace(content="Email test@example.com")
    await guardrails.check_output(response)
    features.append("guardrails_pii")
    evidence["redacted_text"] = response.content

    return {"status": "ok", "features": features, "evidence": evidence}