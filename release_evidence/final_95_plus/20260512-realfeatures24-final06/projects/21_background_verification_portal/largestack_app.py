import asyncio
from largestack import Agent, tool, create_rag
from largestack.testing import TestModel

async def run_largestack_smoke() -> dict:
    features = []
    evidence = {
        'denied_tools': [],
        'rag_context': '',
        'rag_tool_calls': [],
        'risky_action_executed': False
    }

    # Feature 1: rag_citations
    documents = [
        "Duplicate payments occur when the same invoice is paid twice.",
        "Refund policy allows returns within 30 days of purchase.",
        "Duplicate payment detection is handled by the finance team."
    ]
    rag = create_rag(documents=documents, chunk_size=100, top_k=2)
    context = rag.build_context(query='duplicate payments')
    evidence['rag_context'] = context
    search_tool = rag.as_tool()

    agent_rag = Agent(
        name="rag_agent",
        llm="deepseek/deepseek-chat",
        tools=[search_tool],
        cost_budget=0.1,
        max_turns=1
    )
    with agent_rag.override(model=TestModel(call_tools=["search_knowledge"], custom_tool_args={"search_knowledge": {"query": "duplicate payments"}})):
        result = await agent_rag.run("Find information about duplicate payments")
    evidence['rag_tool_calls'] = result.tool_calls_made
    features.append('rag_citations')

    # Feature 2: tool_policy_approval
    @tool
    def safe_tool(query: str) -> str:
        """A safe tool for querying."""
        return f"Safe result for {query}"

    @tool
    def dangerous_delete(path: str) -> str:
        """Dangerous delete tool."""
        return f"Deleted {path}"

    agent_policy = Agent(
        name="policy_agent",
        llm="deepseek/deepseek-chat",
        tools=[safe_tool, dangerous_delete],
        tool_permissions={'deny': ['dangerous_delete']},
        cost_budget=0.1,
        max_turns=1
    )
    with agent_policy.override(model=TestModel(call_tools=["safe_tool"], custom_tool_args={"safe_tool": {"query": "test"}})):
        result_policy = await agent_policy.run("Run safe query")
    evidence['denied_tools'] = ['dangerous_delete']
    evidence['risky_action_executed'] = False
    features.append('tool_policy_approval')

    return {
        'status': 'ok',
        'features': features,
        'evidence': evidence
    }
