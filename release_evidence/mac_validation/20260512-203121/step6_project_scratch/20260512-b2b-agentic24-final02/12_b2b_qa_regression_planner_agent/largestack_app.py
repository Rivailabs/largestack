import json
import os
from dataclasses import dataclass
from largestack import Agent, Workflow
from largestack.testing import TestModel
from largestack.decorators import Agent as TypedAgent, RunContext, ModelRetry

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
        return f"context: {ctx.deps.value} {query}"

    @typed_agent.tool_plain
    def plain_tool(x: int) -> int:
        return x * 2

    @typed_agent.output_validator
    def validate_output(ctx: RunContext[Deps], output: str) -> str:
        if "error" in output:
            raise ModelRetry("output contains error")
        return output

    with typed_agent.override(model=TestModel(custom_output_text="typed ok", call_tools=[])):
        typed_result = await typed_agent.run("prompt", deps=Deps())
    typed_tools = list(typed_agent.tools.keys())
    typed_output = typed_result.output

    # workflow_dag feature
    agent_a = Agent(name="agent_a", llm="deepseek/deepseek-chat", max_turns=1)
    agent_b = Agent(name="agent_b", llm="deepseek/deepseek-chat", max_turns=1)
    wf = Workflow(name="pipe", mode="dag", cost_budget=0.2)
    wf.add_agent(agent_a)
    wf.add_agent(agent_b, deps=["agent_a"])
    with agent_a.override(model=TestModel("a")), agent_b.override(model=TestModel("b")):
        result = await wf.run({"task": "go"})
    workflow_status = result.status
    workflow_steps = len(result.steps)

    return {
        "status": "ok",
        "features": ["typed_decorator_api", "workflow_dag"],
        "evidence": {
            "typed_output": typed_output,
            "typed_tools": typed_tools,
            "workflow_status": workflow_status,
            "workflow_steps": workflow_steps
        }
    }
