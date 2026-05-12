import asyncio
from largestack import Agent, create_rag
from largestack.testing import TestModel
from largestack.memory import create_memory

async def run_largestack_smoke() -> dict:
    features = []
    evidence = {}

    # rag_citations
    documents = [
        "Duplicate payments occur when the same invoice is paid twice.",
        "Refund policy allows returns within 30 days.",
        "Duplicate payment detection is critical for financial compliance."
    ]
    rag = create_rag(documents=documents, chunk_size=100, top_k=2)
    context = rag.build_context(query='duplicate payments')
    search_tool = rag.as_tool()
    agent = Agent(
        name="rag_agent",
        llm="deepseek/deepseek-chat",
        tools=[search_tool],
        cost_budget=0.1,
        max_turns=3
    )
    with agent.override(model=TestModel(call_tools=["search_knowledge"], custom_tool_args={"search_knowledge": {"query": "duplicate payments"}})):
        result = await agent.run("Find information about duplicate payments.")
    evidence['rag_context'] = context
    evidence['rag_tool_calls'] = result.tool_calls_made
    features.append('rag_citations')

    # memory_isolation
    memory1 = create_memory('buffer')
    memory2 = create_memory('buffer')
    await memory1.add_message({"role": "user", "content": "hello user1"})
    await memory1.add_message({"role": "assistant", "content": "hi user1"})
    await memory2.add_message({"role": "user", "content": "hello user2"})
    msgs1 = memory1.get_messages()
    msgs2 = memory2.get_messages()
    evidence['memory_messages'] = len(msgs1)
    # cross_user_leak: check that user2's message is not in memory1
    cross_leak = any("user2" in m.get('content','') for m in msgs1)
    evidence['cross_user_leak'] = cross_leak
    features.append('memory_isolation')

    return {
        "status": "ok",
        "features": features,
        "evidence": evidence
    }
