import json
from dataclasses import dataclass
from typing import List

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
        instructions="demo",
        name="typed",
        max_retries=1,
        cost_budget=0.1
    )

    @typed_agent.tool
    async def context_tool(ctx: RunContext[Deps], query: str) -> str:
        return f"context tool: {ctx.deps.value} - {query}"

    @typed_agent.tool_plain
    def plain_tool(query: str) -> str:
        return f"plain tool: {query}"

    @typed_agent.output_validator
    def validate_output(ctx: RunContext[Deps], output: str) -> str:
        if "error" in output.lower():
            raise ModelRetry("Output contains error, retrying...")
        return output

    with typed_agent.override(model=TestModel(custom_output_text="typed ok", call_tools=[])):
        typed_result = await typed_agent.run("test prompt", deps=Deps())

    typed_tools = list(typed_agent.tools.keys())
    typed_output = typed_result.output
    features.append("typed_decorator_api")
    evidence["typed_tools"] = typed_tools
    evidence["typed_output"] = typed_output

    # --- memory_isolation ---
    memory_user1 = create_memory("buffer")
    memory_user2 = create_memory("buffer")
    await memory_user1.add_message({"role": "user", "content": "hello user1"})
    await memory_user2.add_message({"role": "user", "content": "hello user2"})
    messages_user1 = memory_user1.get_messages()
    messages_user2 = memory_user2.get_messages()
    cross_user_leak = any("user2" in msg.get("content", "") for msg in messages_user1)
    features.append("memory_isolation")
    evidence["memory_messages"] = len(messages_user1) + len(messages_user2)
    evidence["cross_user_leak"] = cross_user_leak

    return {
        "status": "ok",
        "features": features,
        "evidence": evidence
    }
