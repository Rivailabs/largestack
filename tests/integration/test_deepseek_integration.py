"""Integration tests with real DeepSeek API.
Run: LARGESTACK_DEEPSEEK_API_KEY=sk-... python -m pytest tests/integration/ -v
"""
import asyncio, os, sys, pytest
sys.path.insert(0, ".")

SKIP = not os.environ.get("LARGESTACK_DEEPSEEK_API_KEY")
reason = "LARGESTACK_DEEPSEEK_API_KEY not set"

@pytest.mark.skipif(SKIP, reason=reason)
def test_basic_agent():
    from largestack import Agent
    async def run():
        a = Agent(name="test", instructions="Reply in 1 sentence.", llm="deepseek/deepseek-chat", cost_budget=0.05)
        r = await a.run("What is Python?")
        assert len(r.content) > 10
        assert r.total_cost >= 0
        assert r.trace_id
    asyncio.run(run())

@pytest.mark.skipif(SKIP, reason=reason)
def test_agent_with_tools():
    from largestack import Agent, tool
    @tool
    async def add(a: int, b: int) -> str:
        """Add two numbers."""
        return str(a + b)
    async def run():
        a = Agent(name="calc", instructions="Use the add tool.", llm="deepseek/deepseek-chat",
                  tools=[add], cost_budget=0.05, max_turns=5)
        r = await a.run("What is 15 + 27? Use the add tool.")
        assert "42" in r.content
        assert "add" in r.tool_calls_made
    asyncio.run(run())

@pytest.mark.skipif(SKIP, reason=reason)
def test_team_sequential():
    from largestack import Agent, Team
    async def run():
        r = Agent(name="r", instructions="List 1 fact. Max 20 words.", llm="deepseek/deepseek-chat", cost_budget=0.03)
        w = Agent(name="w", instructions="Rewrite in 1 sentence.", llm="deepseek/deepseek-chat", cost_budget=0.03)
        team = Team(agents=[r, w], strategy="sequential", cost_budget=0.10)
        result = await team.run("Benefits of Python")
        assert len(result.content) > 10
    asyncio.run(run())

@pytest.mark.skipif(SKIP, reason=reason)
def test_guardrails():
    from largestack import Agent, create_guardrails
    async def run():
        a = Agent(name="safe", instructions="Be concise.", llm="deepseek/deepseek-chat",
                  guardrails=create_guardrails(pii=True, injection=True), cost_budget=0.05)
        r = await a.run("What is 2+2?")
        assert "4" in r.content
    asyncio.run(run())

@pytest.mark.skipif(SKIP, reason=reason)
def test_rag():
    from largestack import Agent, create_rag
    async def run():
        rag = create_rag(documents=["LARGESTACK costs $299/year.", "LARGESTACK has 15 guardrails."], chunk_size=100)
        a = Agent(name="kb", instructions="Search then answer.", llm="deepseek/deepseek-chat",
                  tools=[rag.as_tool()], cost_budget=0.05, max_turns=5)
        r = await a.run("What does LARGESTACK cost?")
        assert "299" in r.content
    asyncio.run(run())

@pytest.mark.skipif(SKIP, reason=reason)
def test_memory_persistence():
    from largestack import Agent
    from largestack.memory import create_memory
    async def run():
        mem = create_memory("buffer")
        a = Agent(name="mem", instructions="Remember context.", llm="deepseek/deepseek-chat",
                  memory=mem, cost_budget=0.05)
        await a.run("My favorite color is blue. Remember it.")
        r = await a.run("What is my favorite color?")
        assert "blue" in r.content.lower()
    asyncio.run(run())

@pytest.mark.skipif(SKIP, reason=reason)
def test_workflow_dag():
    from largestack import Workflow, Agent
    async def run():
        wf = Workflow("test", mode="dag")
        async def step1(state):
            a = Agent(name="s1", instructions="1 fact. Max 15 words.", llm="deepseek/deepseek-chat", cost_budget=0.02)
            r = await a.run(state.get("topic", "AI"))
            state["fact"] = r.content
            return state
        async def step2(state):
            a = Agent(name="s2", instructions="Rephrase. Max 15 words.", llm="deepseek/deepseek-chat", cost_budget=0.02)
            r = await a.run(f"Rephrase: {state.get('fact','')}")
            state["output"] = r.content
            return state
        wf.add_node("research", step1)
        wf.add_node("rewrite", step2, deps=["research"])
        result = await wf.run({"topic": "Docker"})
        assert result.get("output")
    asyncio.run(run())
