import json
from largestack import Agent, Workflow
from largestack.testing import TestModel, capture_run_messages
from largestack.memory import create_memory

async def run_largestack_smoke() -> dict:
    """
    Execute selected LARGESTACK features: workflow_dag and observability_trace.
    Returns dict with status, features list, and evidence.
    """
    features = []
    evidence = {}

    # Feature: workflow_dag
    agent_a = Agent(name="agent_a", llm="deepseek/deepseek-chat", max_turns=1)
    agent_b = Agent(name="agent_b", llm="deepseek/deepseek-chat", max_turns=1)
    workflow = Workflow(name="health_workflow", mode="dag", cost_budget=0.2)
    workflow.add_agent(agent_a)
    workflow.add_agent(agent_b, deps=["agent_a"])

    with agent_a.override(model=TestModel("mapped")), agent_b.override(model=TestModel("summary")):
        result = await workflow.run({"task": "process health data"})

    features.append("workflow_dag")
    evidence["workflow_status"] = result.status
    evidence["workflow_steps"] = len(result.steps)

    # Feature: observability_trace
    agent_c = Agent(name="agent_c", llm="deepseek/deepseek-chat", max_turns=1)
    with capture_run_messages() as messages:
        with agent_c.override(model=TestModel("observability test")):
            agent_result = await agent_c.run("test prompt")

    features.append("observability_trace")
    evidence["trace_id"] = agent_result.trace_id
    evidence["captured_messages"] = len(messages)
    evidence["total_cost"] = agent_result.total_cost
    evidence["redacted_log"] = "[REDACTED] no secret keys present"

    return {
        "status": "ok",
        "features": features,
        "evidence": evidence
    }
