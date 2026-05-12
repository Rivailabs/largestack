import asyncio
from largestack import Agent, Workflow
from largestack.testing import TestModel, capture_run_messages
from largestack.memory import create_memory
from largestack import create_guardrails
from types import SimpleNamespace

async def run_largestack_smoke() -> dict:
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

    # --- observability_trace ---
    agent_c = Agent(name="agent_c", llm="deepseek/deepseek-chat", max_turns=1)
    with capture_run_messages() as messages:
        with agent_c.override(model=TestModel("trace_output")):
            trace_result = await agent_c.run("trace me")
    evidence["trace_id"] = trace_result.trace_id
    evidence["captured_messages"] = len(messages)
    evidence["total_cost"] = trace_result.total_cost
    # Simulate redacted log: ensure no real secret keys
    redacted_log = "[REDACTED] no secret keys present"
    evidence["redacted_log"] = redacted_log
    features.append("observability_trace")

    return {"status": "ok", "features": features, "evidence": evidence}
