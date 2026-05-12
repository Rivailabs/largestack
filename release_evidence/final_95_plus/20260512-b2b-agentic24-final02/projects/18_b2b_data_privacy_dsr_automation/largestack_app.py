import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

from largestack import Agent
from largestack.decorators import Agent as TypedAgent, RunContext, ModelRetry
from largestack.testing import TestModel
from largestack import create_guardrails

@dataclass
class Deps:
    value: str = "demo"

async def run_largestack_smoke() -> dict:
    features = []
    evidence = {}

    # --- typed_decorator_api ---
    typed_agent = TypedAgent[Deps, str](
        'deepseek/deepseek-chat',
        deps_type=Deps,
        output_type=str,
        instructions="You are a helpful assistant.",
        name='typed',
        max_retries=1,
        cost_budget=0.1
    )

    @typed_agent.tool
    def context_tool(ctx: RunContext[Deps], query: str) -> str:
        return f"Context: {ctx.deps.value}, query: {query}"

    @typed_agent.tool_plain
    def plain_tool(query: str) -> str:
        return f"Plain: {query}"

    @typed_agent.output_validator
    def validate_output(ctx: RunContext[Deps], output: str) -> str:
        if "error" in output.lower():
            raise ModelRetry("Output contains error, retrying...")
        return output

    with typed_agent.override(model=TestModel(custom_output_text='typed ok', call_tools=[])):
        typed_result = await typed_agent.run("test prompt", deps=Deps())

    typed_tools = list(typed_agent.tools.keys())
    typed_output = typed_result.output
    features.append("typed_decorator_api")
    evidence["typed_tools"] = typed_tools
    evidence["typed_output"] = typed_output

    # --- guardrails_pii ---
    guardrails = create_guardrails(pii=True, injection=True, pii_action='redact')
    response = SimpleNamespace(content="Email test@example.com")
    await guardrails.check_output(response)
    redacted_text = response.content
    features.append("guardrails_pii")
    evidence["redacted_text"] = redacted_text

    return {
        "status": "ok",
        "features": features,
        "evidence": evidence
    }

if __name__ == "__main__":
    result = asyncio.run(run_largestack_smoke())
    print(result)
