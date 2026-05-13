import asyncio
from dataclasses import dataclass
from largestack import Agent, Workflow
from largestack.testing import TestModel
from largestack.decorators import Agent as TypedAgent, RunContext, ModelRetry

@dataclass
class Deps:
    value: str = "demo"

async def run_largestack_smoke() -> dict:
    """
    Execute selected LARGESTACK features: typed_decorator_api and workflow_dag.
    Returns status, features list, and evidence dict.
    """
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
        """Return the dependency value."""
        return ctx.deps.value

    @typed_agent.tool_plain
    def get_constant() -> str:
        """Return a constant string."""
        return "constant"

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
    evidence["typed_output"] = typed_output
    evidence["typed_tools"] = typed_tools

    # --- workflow_dag ---
    agent_a = Agent(name="agent_a", llm="deepseek/deepseek-chat", max_turns=1, cost_budget=0.1)
    agent_b = Agent(name="agent_b", llm="deepseek/deepseek-chat", max_turns=1, cost_budget=0.1)

    workflow = Workflow(name="test_workflow", mode="dag", cost_budget=0.2)
    workflow.add_agent(agent_a)
    workflow.add_agent(agent_b, deps=["agent_a"])

    with agent_a.override(model=TestModel("output_a")), agent_b.override(model=TestModel("output_b")):
        result = await workflow.run({"task": "test"})

    workflow_status = result.status
    workflow_steps = len(result.steps)
    features.append("workflow_dag")
    evidence["workflow_status"] = workflow_status
    evidence["workflow_steps"] = workflow_steps

    return {
        "status": "ok",
        "features": features,
        "evidence": evidence
    }

if __name__ == "__main__":
    asyncio.run(run_largestack_smoke())
