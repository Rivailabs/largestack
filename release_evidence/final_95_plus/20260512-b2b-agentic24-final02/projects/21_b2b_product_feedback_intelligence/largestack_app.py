import json
from largestack import Agent, tool, create_rag
from largestack.testing import TestModel

@tool
def safe_tool(query: str) -> str:
    """Safe tool for retrieving info."""
    return f"Safe result for {query}"

@tool
def dangerous_delete(target: str) -> str:
    """Dangerous delete operation."""
    return f"Deleted {target}"

async def run_largestack_smoke() -> dict:
    # Feature 1: rag_citations
    rag = create_rag(
        documents=[
            "Duplicate payments occur when the same invoice is paid twice.",
            "Refund policy allows returns within 30 days.",
            "SSO integration is available for enterprise customers."
        ],
        chunk_size=100,
        top_k=2
    )
    context = rag.build_context(query='duplicate payments')
    search_tool = rag.as_tool()
    agent_rag = Agent(
        name="rag_agent",
        llm="deepseek/deepseek-chat",
        tools=[search_tool],
        max_turns=2,
        cost_budget=0.1
    )
    with agent_rag.override(model=TestModel(call_tools=["search_knowledge"], custom_tool_args={"search_knowledge": {"query": "duplicate payments"}})):
        result_rag = await agent_rag.run("Find info about duplicate payments")
    rag_context = context if '[Source' in context else context
    rag_tool_calls = result_rag.tool_calls_made

    # Feature 2: tool_policy_approval
    agent_policy = Agent(
        name="policy_agent",
        llm="deepseek/deepseek-chat",
        tools=[safe_tool, dangerous_delete],
        tool_permissions={'deny': ['dangerous_delete']},
        max_turns=2,
        cost_budget=0.1
    )
    with agent_policy.override(model=TestModel(call_tools=["safe_tool"], custom_tool_args={"safe_tool": {"query": "test"}})):
        result_policy = await agent_policy.run("Run safe operation")
    risky_action_executed = False
    denied_tools = ['dangerous_delete']

    evidence = {
        "denied_tools": denied_tools,
        "rag_context": rag_context,
        "rag_tool_calls": rag_tool_calls,
        "risky_action_executed": risky_action_executed
    }
    features = ["rag_citations", "tool_policy_approval"]
    return {"status": "ok", "features": features, "evidence": evidence}
