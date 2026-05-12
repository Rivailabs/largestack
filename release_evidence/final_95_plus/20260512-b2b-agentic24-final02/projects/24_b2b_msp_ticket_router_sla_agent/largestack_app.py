import asyncio
from types import SimpleNamespace

from largestack import Agent, Orchestrator
from largestack.testing import TestModel
from largestack.guardrails import create_guardrails

async def run_largestack_smoke() -> dict:
    """Execute selected LARGESTACK features: map-reduce orchestration and PII guardrails."""
    features = []
    evidence = {}

    # Feature: orchestrator_map_reduce
    mapper = Agent(name="mapper", llm="deepseek/deepseek-chat", max_turns=1)
    reducer = Agent(name="reducer", llm="deepseek/deepseek-chat", max_turns=1)
    orch = Orchestrator(strategy="map_reduce", mapper=mapper, reducer=reducer)
    items = ["item1", "item2", "item3"]
    with mapper.override(model=TestModel("mapped")), reducer.override(model=TestModel("summary")):
        result = await orch.run({"items": items})
    features.append("orchestrator_map_reduce")
    evidence["orchestrator_strategy"] = "map_reduce"
    evidence["map_items"] = len(items)

    # Feature: guardrails_pii
    guardrails = create_guardrails(pii=True, injection=True, pii_action="redact")
    response = SimpleNamespace(content="Email test@example.com")
    await guardrails.check_output(response)
    features.append("guardrails_pii")
    evidence["redacted_text"] = response.content

    return {"status": "ok", "features": features, "evidence": evidence}
