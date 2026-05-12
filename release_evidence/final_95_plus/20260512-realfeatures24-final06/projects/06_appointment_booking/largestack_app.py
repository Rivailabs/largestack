import asyncio
from dataclasses import dataclass
from largestack import Agent
from largestack.testing import TestModel
from largestack.decorators import Agent as TypedAgent, RunContext, ModelRetry
from largestack.memory import create_memory

@dataclass
class Deps:
    value: str = "demo"

async def run_largestack_smoke() -> dict:
    # typed_decorator_api feature
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
        return f"context tool: {ctx.deps.value} {query}"

    @typed_agent.tool_plain
    def plain_tool(x: int) -> int:
        return x * 2

    @typed_agent.output_validator
    def validate_output(ctx: RunContext[Deps], output: str) -> str:
        if "error" in output.lower():
            raise ModelRetry("output contains error")
        return output

    with typed_agent.override(model=TestModel(custom_output_text="typed ok", call_tools=[])):
        typed_result = await typed_agent.run("prompt", deps=Deps())

    typed_tools = list(typed_agent.tools.keys())
    typed_output = typed_result.output

    # memory_isolation feature
    memory1 = create_memory("buffer")
    memory2 = create_memory("buffer")

    await memory1.add_message({"role": "user", "content": "hello user1"})
    await memory1.add_message({"role": "assistant", "content": "hi user1"})
    await memory2.add_message({"role": "user", "content": "hello user2"})

    messages1 = memory1.get_messages()
    messages2 = memory2.get_messages()

    # Check cross-user leak: messages from memory1 should not appear in memory2
    cross_user_leak = False
    for msg in messages2:
        if msg.get("content") == "hello user1" or msg.get("content") == "hi user1":
            cross_user_leak = True
            break

    memory_messages = len(messages1)

    return {
        "status": "ok",
        "features": ["typed_decorator_api", "memory_isolation"],
        "evidence": {
            "cross_user_leak": cross_user_leak,
            "memory_messages": memory_messages,
            "typed_output": typed_output,
            "typed_tools": typed_tools
        }
    }

if __name__ == "__main__":
    result = asyncio.run(run_largestack_smoke())
    print(result)
