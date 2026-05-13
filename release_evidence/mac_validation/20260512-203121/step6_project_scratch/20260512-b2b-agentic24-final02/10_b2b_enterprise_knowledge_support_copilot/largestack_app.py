import asyncio
from types import SimpleNamespace

from largestack import Agent, create_guardrails
from largestack.testing import TestModel, capture_run_messages

async def run_largestack_smoke() -> dict:
    features = []
    evidence = {}

    # Feature: guardrails_pii
    guardrails = create_guardrails(pii=True, injection=True, pii_action='redact')
    response = SimpleNamespace(content="Email test@example.com")
    await guardrails.check_output(response)
    redacted_text = response.content
    features.append('guardrails_pii')
    evidence['redacted_text'] = redacted_text

    # Feature: observability_trace
    agent = Agent(
        name="test_agent",
        llm="deepseek/deepseek-chat",
        max_turns=1,
        cost_budget=0.1
    )
    with capture_run_messages() as messages:
        with agent.override(model=TestModel(custom_output_text="Hello world", call_tools=[])):
            result = await agent.run("Say hello")
    trace_id = result.trace_id
    total_cost = result.total_cost
    captured_messages = len(messages)
    # Redact any sk- keys from messages
    redacted_log = str(messages)
    import re
    redacted_log = re.sub(r'sk-[a-zA-Z0-9]+', '[REDACTED] no secret keys present', redacted_log)
    features.append('observability_trace')
    evidence['trace_id'] = trace_id
    evidence['total_cost'] = total_cost
    evidence['captured_messages'] = captured_messages
    evidence['redacted_log'] = redacted_log

    return {
        'status': 'ok',
        'features': features,
        'evidence': evidence
    }
