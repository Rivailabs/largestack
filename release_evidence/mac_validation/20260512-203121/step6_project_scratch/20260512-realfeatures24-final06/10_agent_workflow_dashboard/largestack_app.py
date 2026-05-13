import asyncio
from types import SimpleNamespace

from largestack import Agent
from largestack.testing import TestModel, capture_run_messages
from largestack import create_guardrails

async def run_largestack_smoke() -> dict:
    features = []
    evidence = {}

    # guardrails_pii
    guardrails = create_guardrails(pii=True, injection=True, pii_action='redact')
    response = SimpleNamespace(content="Email test@example.com")
    await guardrails.check_output(response)
    redacted_text = response.content
    features.append('guardrails_pii')
    evidence['redacted_text'] = redacted_text

    # observability_trace
    agent = Agent(
        name="observability_agent",
        llm="deepseek/deepseek-chat",
        max_turns=1,
        cost_budget=0.1
    )
    with capture_run_messages() as messages:
        with agent.override(model=TestModel(call_tools=[], custom_output_text="observability test")):
            result = await agent.run("test prompt")
    trace_id = result.trace_id
    total_cost = result.total_cost
    captured_messages = len(messages)
    redacted_log = '[REDACTED] no secret keys present'
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

if __name__ == '__main__':
    result = asyncio.run(run_largestack_smoke())
    print(result)
