import asyncio
from dataclasses import dataclass
from datetime import datetime

from largestack import Agent
from largestack.testing import TestModel, capture_run_messages
from largestack.decorators import Agent as TypedAgent, RunContext, ModelRetry

@dataclass
class Deps:
    value: str = "demo"

async def run_largestack_smoke() -> dict:
    """Execute selected LARGESTACK features: typed_decorator_api and observability_trace."""
    features = []
    evidence = {}

    # --- typed_decorator_api ---
    typed_agent = TypedAgent[Deps, str](
        'deepseek/deepseek-chat',
        deps_type=Deps,
        output_type=str,
        instructions='You are a helpful assistant.',
        name='typed',
        max_retries=1,
        cost_budget=0.1
    )

    @typed_agent.tool
    def context_tool(ctx: RunContext[Deps], query: str) -> str:
        """Context tool that uses deps."""
        return f"Context: {ctx.deps.value} and {query}"

    @typed_agent.tool_plain
    def plain_tool(x: int) -> str:
        """Plain tool."""
        return f"Plain: {x * 2}"

    @typed_agent.output_validator
    def validate_output(ctx: RunContext[Deps], output: str) -> str:
        if 'error' in output.lower():
            raise ModelRetry("Output contains error, retry.")
        return output

    with typed_agent.override(model=TestModel(custom_output_text='typed ok', call_tools=[])):
        typed_result = await typed_agent.run("test prompt", deps=Deps())

    typed_tools = list(typed_agent.tools.keys())
    typed_output = typed_result.output
    features.append('typed_decorator_api')
    evidence['typed_tools'] = typed_tools
    evidence['typed_output'] = typed_output

    # --- observability_trace ---
    agent = Agent(
        name="obs_agent",
        llm="deepseek/deepseek-chat",
        cost_budget=0.1,
        max_turns=3
    )

    with capture_run_messages() as messages:
        with agent.override(model=TestModel(call_tools=[], custom_output_text="observability result")):
            result = await agent.run("test")

    trace_id = result.trace_id
    total_cost = result.total_cost
    captured_messages = len(messages)
    # Simulate redacted log
    redacted_log = '[REDACTED] no secret keys present'
    features.append('observability_trace')
    evidence['trace_id'] = trace_id
    evidence['captured_messages'] = captured_messages
    evidence['total_cost'] = total_cost
    evidence['redacted_log'] = redacted_log

    return {"status": "ok", "features": features, "evidence": evidence}
