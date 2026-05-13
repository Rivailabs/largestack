import asyncio
from types import SimpleNamespace
from largestack import Agent, create_rag, tool
from largestack.testing import TestModel
from largestack.memory import create_memory
from largestack.decorators import Agent as TypedAgent, RunContext, ModelRetry
from largestack import Orchestrator, Team, Workflow
from largestack import create_guardrails

async def run_largestack_smoke() -> dict:
    features = []
    evidence = {}

    # Feature: rag_citations
    documents = [
        "Duplicate payments occur when the same invoice is paid more than once.",
        "To prevent duplicate payments, implement three-way matching.",
        "Vendor risk assessment includes financial health checks."
    ]
    rag = create_rag(documents=documents, chunk_size=100, top_k=2)
    context = rag.build_context(query='duplicate payments')
    evidence['rag_context'] = context
    search_tool = rag.as_tool()
    agent = Agent(
        name="rag_agent",
        llm="deepseek/deepseek-chat",
        tools=[search_tool],
        cost_budget=0.1,
        max_turns=3
    )
    with agent.override(model=TestModel(call_tools=["search_knowledge"], custom_tool_args={"search_knowledge": {"query": "duplicate payments"}})):
        result = await agent.run("Find information about duplicate payments")
    evidence['rag_tool_calls'] = result.tool_calls_made
    features.append('rag_citations')

    # Feature: guardrails_pii
    guardrails = create_guardrails(pii=True, injection=True, pii_action='redact')
    response = SimpleNamespace(content="Contact us at test@example.com for support.")
    await guardrails.check_output(response)
    evidence['redacted_text'] = response.content
    features.append('guardrails_pii')

    # Memory
    memory = create_memory("buffer")
    await memory.add_message({"role": "user", "content": "hello user1"})
    messages = memory.get_messages()
    features.append('memory')

    # Typed agent
    from dataclasses import dataclass
    @dataclass
    class Deps:
        value: str = "demo"
    typed_agent = TypedAgent[Deps, str](
        "deepseek/deepseek-chat",
        deps_type=Deps,
        output_type=str,
        instructions="demo",
        name="typed",
        max_retries=1,
        cost_budget=0.1
    )
    with typed_agent.override(model=TestModel(custom_output_text="typed ok", call_tools=[])):
        typed_result = await typed_agent.run("prompt", deps=Deps())
    typed_tools = list(typed_agent.tools.keys())
    typed_output = typed_result.output
    features.append('typed_agent')

    # Workflow (DAG) - fix: add agent_a before agent_b
    agent_a = Agent(name="agent_a", llm="deepseek/deepseek-chat", max_turns=1)
    agent_b = Agent(name="agent_b", llm="deepseek/deepseek-chat", max_turns=1)
    wf = Workflow(name="pipe", mode="dag", cost_budget=0.2)
    wf.add_agent(agent_a)
    wf.add_agent(agent_b, deps=["agent_a"])
    with agent_a.override(model=TestModel("a")), agent_b.override(model=TestModel("b")):
        result_wf = await wf.run({"task": "go"})
    workflow_steps = len(result_wf.steps)
    features.append('workflow')

    # Orchestrator map_reduce
    mapper = Agent(name="mapper", llm="deepseek/deepseek-chat", max_turns=1)
    reducer = Agent(name="reducer", llm="deepseek/deepseek-chat", max_turns=1)
    orch = Orchestrator(strategy="map_reduce", mapper=mapper, reducer=reducer)
    with mapper.override(model=TestModel("mapped")), reducer.override(model=TestModel("summary")):
        result_orch = await orch.run({"items": ["a", "b", "c"]})
    features.append('orchestrator_map_reduce')

    # Orchestrator router
    classifier = Agent(name="classifier", llm="deepseek/deepseek-chat")
    specialist = Agent(name="billing", llm="deepseek/deepseek-chat")
    orch_router = Orchestrator(strategy="router", classifier=classifier, routes={"billing": specialist}, default_route="billing")
    with classifier.override(model=TestModel("billing")), specialist.override(model=TestModel("routed ok")):
        route_result = await orch_router.run("route this")
    route_output = route_result.output
    features.append('orchestrator_router')

    # Team
    team = Team(agents=[agent_a, agent_b], strategy="parallel", cost_budget=0.2)
    with agent_a.override(model=TestModel("a")), agent_b.override(model=TestModel("b")):
        team_result = await team.run("task")
    team_output = team_result.content
    features.append('team')

    return {
        "status": "ok",
        "features": features,
        "evidence": evidence
    }
