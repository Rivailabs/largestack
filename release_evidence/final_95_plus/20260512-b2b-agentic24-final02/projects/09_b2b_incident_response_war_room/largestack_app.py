import json
import os
from largestack import Agent, Workflow, create_rag, tool
from largestack.testing import TestModel

async def run_largestack_smoke() -> dict:
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
    workflow = Workflow(name="incident_pipeline", mode="dag", cost_budget=0.2)
    workflow.add_agent(agent_a)
    workflow.add_agent(agent_b, deps=["agent_a"])

    with agent_a.override(model=TestModel(custom_output_text="triage done", call_tools=[])), \
         agent_b.override(model=TestModel(custom_output_text="response ready", call_tools=[])):
        result = await workflow.run({"task": "handle incident"})

    features.append("workflow_dag")
    evidence["workflow_status"] = result.status
    evidence["workflow_steps"] = len(result.steps)

    # --- rag_citations ---
    base = os.path.dirname(__file__)
    fixture_path = os.path.join(base, 'data', 'fixture_incidents.json')
    with open(fixture_path) as f:
        incidents_data = json.load(f)
    documents = [inc['description'] for inc in incidents_data]

    rag = create_rag(documents=documents, chunk_size=100, top_k=2)
    context = rag.build_context(query='duplicate payments')
    rag_tool = rag.as_tool()

    agent_rag = Agent(
        name="rag_agent",
        llm="deepseek/deepseek-chat",
        tools=[rag_tool],
        max_turns=2,
        cost_budget=0.1
    )

    with agent_rag.override(model=TestModel(call_tools=["search_knowledge"], custom_tool_args={"search_knowledge": {"query": "duplicate payments"}})):
        rag_result = await agent_rag.run("Find info about duplicate payments")

    features.append("rag_citations")
    evidence["rag_context"] = context
    evidence["rag_tool_calls"] = rag_result.tool_calls_made

    return {
        "status": "ok",
        "features": features,
        "evidence": evidence
    }
