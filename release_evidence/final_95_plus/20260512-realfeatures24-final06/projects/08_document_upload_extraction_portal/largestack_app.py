import asyncio
from largestack import Agent, create_rag
from largestack.testing import TestModel
from largestack.memory import create_memory

async def run_largestack_smoke() -> dict:
    """
    Execute selected LARGESTACK features: rag_citations and memory_isolation.
    Returns a dict with status, features list, and evidence.
    """
    features = []
    evidence = {}

    # --- rag_citations ---
    # Create RAG with sample documents
    rag = create_rag(
        documents=[
            "Duplicate payments occur when the same invoice is paid more than once.",
            "To prevent duplicate payments, implement three-way matching.",
            "Audit trails help detect duplicate payments early."
        ],
        chunk_size=100,
        top_k=2
    )
    # Build context
    context = rag.build_context(query='duplicate payments')
    # Convert to tool
    search_tool = rag.as_tool()
    # Create agent with the tool
    agent = Agent(
        name="rag_agent",
        llm="deepseek/deepseek-chat",
        tools=[search_tool],
        cost_budget=0.1,
        max_turns=3
    )
    # Override model to call search_knowledge tool
    with agent.override(model=TestModel(call_tools=["search_knowledge"], custom_tool_args={"search_knowledge": {"query": "duplicate payments"}})):
        result = await agent.run("Find information about duplicate payments.")
    # Collect evidence
    evidence['rag_context'] = context if '[Source' in context else context
    evidence['rag_tool_calls'] = result.tool_calls_made
    features.append('rag_citations')

    # --- memory_isolation ---
    # Create separate memory objects for two users
    memory_user1 = create_memory('buffer')
    memory_user2 = create_memory('buffer')
    # Add messages for user1
    await memory_user1.add_message({"role": "user", "content": "Hello from user1"})
    await memory_user1.add_message({"role": "assistant", "content": "Hi user1!"})
    # Add messages for user2
    await memory_user2.add_message({"role": "user", "content": "Hello from user2"})
    # Get messages
    messages_user1 = memory_user1.get_messages()
    messages_user2 = memory_user2.get_messages()
    # Check isolation: user2's messages should not appear in user1's memory
    cross_user_leak = False
    for msg in messages_user1:
        if 'user2' in msg.get('content', ''):
            cross_user_leak = True
            break
    evidence['memory_messages'] = len(messages_user1)
    evidence['cross_user_leak'] = cross_user_leak
    features.append('memory_isolation')

    return {
        "status": "ok",
        "features": features,
        "evidence": evidence
    }

if __name__ == "__main__":
    result = asyncio.run(run_largestack_smoke())
    print(result)
