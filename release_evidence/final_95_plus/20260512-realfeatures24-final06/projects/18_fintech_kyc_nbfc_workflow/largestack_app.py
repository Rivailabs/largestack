import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

from largestack import Agent, Team, Workflow, Orchestrator, tool, create_rag, create_guardrails
from largestack.memory import create_memory
from largestack.testing import TestModel, FunctionModel, capture_run_messages
from largestack.decorators import Agent as TypedAgent, RunContext, ModelRetry

@dataclass
class Deps:
    value: str = "demo"

async def run_largestack_smoke() -> dict:
    features = []
    evidence = {}

    # --- typed_decorator_api ---
    typed_agent = TypedAgent[Deps, str](
        "deepseek/deepseek-chat",
        deps_type=Deps,
        output_type=str,
        instructions="You are a helpful assistant.",
        name="typed",
        max_retries=1,
        cost_budget=0.1
    )

    @typed_agent.tool
    async def get_context(ctx: RunContext[Deps]) -> str:
        return f"context: {ctx.deps.value}"

    @typed_agent.tool_plain
    def plain_tool() -> str:
        return "plain tool result"

    @typed_agent.output_validator
    def validate_output(ctx: RunContext[Deps], output: str) -> str:
        if "error" in output.lower():
            raise ModelRetry("Output contains error, retry.")
        return output

    with typed_agent.override(model=TestModel(custom_output_text="typed ok", call_tools=[])):
        typed_result = await typed_agent.run("test prompt", deps=Deps())

    typed_tools = list(typed_agent.tools.keys())
    typed_output = typed_result.output
    features.append("typed_decorator_api")
    evidence["typed_tools"] = typed_tools
    evidence["typed_output"] = typed_output

    # --- guardrails_pii ---
    guardrails = create_guardrails(pii=True, injection=True, pii_action="redact")
    response = SimpleNamespace(content="Email test@example.com")
    await guardrails.check_output(response)
    redacted_text = response.content
    features.append("guardrails_pii")
    evidence["redacted_text"] = redacted_text

    return {"status": "ok", "features": features, "evidence": evidence}

if __name__ == "__main__":
    result = asyncio.run(run_largestack_smoke())
    print(result)
