import asyncio
from largestack import Agent, Workflow, create_rag, tool
from largestack.testing import TestModel, FunctionModel
from largestack.decorators import Agent as TypedAgent, RunContext, ModelRetry
from dataclasses import dataclass
from types import SimpleNamespace

async def run_largestack_smoke() -> dict:
    features = []
    evidence = {}

    # workflow_dag
    agent_a = Agent(name="agent_a", llm="deepseek/deepseek-chat", max_turns=1, cost_budget=0.1)
    agent_b = Agent(name="agent_b", llm="deepseek/deepseek-chat", max_turns=1, cost_budget=0.1)
    workflow = Workflow(name="test_dag", mode="dag", cost_budget=0.2)
    workflow.add_agent(agent_a)
    workflow.add_agent(agent_b, deps=["agent_a"])
    with agent_a.override(model=TestModel(custom_output_text="step_a", call_tools=[])), \
         agent_b.override(model=TestModel(custom_output_text="step_b", call_tools=[])):
        result = await workflow.run({"task": "test"})
    features.append("workflow_dag")
    evidence["workflow_status"] = result.status
    evidence["workflow_steps"] = len(result.steps)

    # rag_citations
    documents = ["Duplicate payments require approval before refund."]
    rag = create_rag(documents=documents, chunk_size=100, top_k=2)
    context = rag.build_context(query="duplicate payments")
    rag_tool = rag.as_tool()
    agent_rag = Agent(name="rag_agent", llm="deepseek/deepseek-chat", tools=[rag_tool], max_turns=2, cost_budget=0.1)
    with agent_rag.override(model=TestModel(call_tools=["search_knowledge"], custom_tool_args={"search_knowledge": {"query": "duplicate payments"}})):
        rag_result = await agent_rag.run("duplicate payments")
    features.append("rag_citations")
    evidence["rag_context"] = context if '[Source' in context else context
    evidence["rag_tool_calls"] = rag_result.tool_calls_made

    return {"status": "ok", "features": features, "evidence": evidence}

if __name__ == "__main__":
    asyncio.run(run_largestack_smoke())
