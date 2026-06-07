# Agents

An **Agent** wraps a model + instructions + (optional) tools, guardrails, memory, and cost controls into one callable object. You call `await agent.run(task)` and get back an [`AgentResult`](#agentresult).

There are two agent surfaces:

| Import | Style | When to use |
|---|---|---|
| `from largestack import Agent` | Classic / keyword args | Tools as a list, named guardrails, fallback, callbacks |
| `from largestack.decorators import Agent` | Typed `Agent[Deps, Out]` | Typed dependency injection, `@agent.tool`, `@agent.output_validator` |

Both run on the same engine. This page covers the classic `Agent`; the typed one is at the [bottom](#typed-agent-deps-out).

## Constructing an Agent

```python
from largestack import Agent

agent = Agent(
    name="helper",
    instructions="You are a helpful assistant.",
    llm="openai/gpt-4o-mini",
)
```

### Constructor arguments

| Arg | Type | Default | Meaning |
|---|---|---|---|
| `name` | `str` | required | Agent name (used in traces / audit / shared memory keys). |
| `instructions` | `str` | `"You are a helpful assistant."` | System prompt. |
| `llm` | `str \| None` | config default | Provider model id, e.g. `"openai/gpt-4o-mini"`, `"anthropic/claude-..."`, or `"auto"`. |
| `tools` | `list \| None` | `[]` | Tools to register (see [Tools](tools.md)). |
| `guardrails` | see below | config default | `False` to disable, a list of names, or a `GuardrailPipeline`. See [Guardrails](guardrails.md). |
| `memory` | object | `ConversationMemory()` | Conversation memory. See [Memory](memory.md). |
| `cost_budget` | `float \| None` | config default | Hard per-run USD ceiling. Run raises `BudgetExceededError` if exceeded. |
| `max_turns` | `int \| None` | config default | Max LLM↔tool turns before the engine forces a final answer. |
| `tool_permissions` | `dict \| None` | `None` | `{"allow": [...]}` / `{"deny": [...]}` static allow/deny. See [Tools](tools.md#permissions). |
| `tool_policy` | `ToolAccessPolicy \| None` | `None` | Runtime rate-limit + parameter validation. See [Tools](tools.md#toolaccesspolicy). |
| `shared_memory` | object | `None` | A `SharedMemorySpace` for cross-agent data. |
| `retries` | `int` | `0` | Extra attempts on failure (`0` = one attempt total). |
| `fallback` | `Agent \| None` | `None` | Another agent to try if this one exhausts its retries. |
| `on_complete` | callable | `None` | Called with the `AgentResult` on success (sync or async). |
| `on_error` | callable | `None` | Called with the exception on each failed attempt. |
| `steering` | `list \| None` | `None` | Steering rules applied before tools / after the model. |

`guardrails=False` is an explicit opt-out — use it for tests, benchmarks, and trusted local runs.

## The run loop

`await agent.run(task)` drives this loop (in `largestack/_core/engine.py`):

1. **Build messages** — system instructions + prior memory + the user `task`.
2. **Input guardrails** — `check_input(messages)` (skipped if guardrails are off).
3. **LLM call** — through the gateway (or a `TestModel`, if [overridden](#testing-with-testmodel)).
4. **Output guardrails** — `check_output(response)`.
5. **Tool loop** — if the model requested tools, each is executed and the result is fed back; loop returns to step 2. Bounded by `max_turns`, `cost_budget`, and loop detection.
6. **Return** — when the model answers with text (no tool calls), a final `AgentResult` is produced and a trace row is written.

The whole run is wrapped in `retries` + `fallback`, and every run emits events + an audit/trace row.

```python
import asyncio
from largestack import Agent

async def main():
    agent = Agent(name="helper", llm="openai/gpt-4o-mini")
    result = await agent.run("Summarize the plot of Hamlet in one line.")
    print(result.content)
    print(f"${result.total_cost:.6f}, {result.turns} turns, trace {result.trace_id}")

asyncio.run(main())
```

Not in an event loop? Use the sync wrapper:

```python
from largestack import Agent

agent = Agent(name="helper", llm="openai/gpt-4o-mini")
result = agent.run_sync("Hello!")   # raises RuntimeError if a loop is already running
```

### AgentResult

`run()` returns an `AgentResult` (a Pydantic model from `largestack.types`):

| Field | Type | Meaning |
|---|---|---|
| `content` | `str` | The final text answer. |
| `agent_name` | `str` | Which agent produced it. |
| `total_cost` | `float` | Per-run USD cost. |
| `total_tokens` | `int` | Per-run token total (input + output). |
| `turns` | `int` | Number of loop turns taken. |
| `trace_id` | `str` | Trace id for this run. |
| `duration_ms` | `float` | Wall-clock duration. |
| `tool_calls_made` | `list[str]` | Tool names attempted this run. |
| `tool_calls_failed` | `list[str]` | Tools attempted that errored (succeeded = made − failed). |

> Passing `response_model=MySchema` to `run()` returns a parsed Pydantic model instead of an `AgentResult` (provider-native structured output engages where available).

## Testing with TestModel

`agent.override(model=...)` is a context manager that swaps in a `TestModel` / `FunctionModel` from `largestack.testing`. Inside the block the engine bypasses the gateway — **no real API key and no network call** — so it runs in CI.

```python
import asyncio
from largestack import Agent
from largestack.testing import TestModel

async def main():
    agent = Agent(name="helper", llm="openai/gpt-4o-mini", guardrails=False)
    test_model = TestModel(custom_output_text="canned reply")
    with agent.override(model=test_model):
        result = await agent.run("anything")
    assert result.content == "canned reply"
    assert test_model.calls == 1

asyncio.run(main())
```

To assert that no real provider call leaks through a test path, wrap the call in `block_model_requests()` (raises `ModelRequestsBlockedError` on any real gateway call), or capture the message flow with `capture_run_messages()`. See [Testing](../testing-and-validation.md).

## Typed Agent (`Deps`, `Out`)

`largestack.decorators.Agent` is a typed, PydanticAI-style surface: `Agent[DepsT, OutputT]` with dependency injection via `RunContext`, decorator-registered tools, and output validators.

```python
import asyncio
from dataclasses import dataclass
from largestack.decorators import Agent, RunContext, ModelRetry
from largestack.testing import TestModel

@dataclass
class Deps:
    user_id: str

agent = Agent[Deps, str](
    "openai/gpt-4o-mini",
    deps_type=Deps,
    instructions="You are a support agent.",
)

@agent.tool
async def whoami(ctx: RunContext[Deps]) -> str:
    """Return the current user id."""
    return ctx.deps.user_id

@agent.output_validator
def no_badword(ctx: RunContext[Deps], output: str) -> str:
    if "badword" in output:
        raise ModelRetry("Avoid bad words")   # ask the LLM to retry with a hint
    return output

async def main():
    with agent.override(model=TestModel(custom_output_text="hello u1", call_tools=[])):
        result = await agent.run("hi", deps=Deps(user_id="u1"))
    print(result.output)         # "hello u1"
    print(result.usage)          # {"input_tokens": ..., "output_tokens": ..., "cost": ...}
    print(result.retry_count)    # 0

asyncio.run(main())
```

`RunContext[Deps]` carries `deps`, `usage`, `retry_count`, `messages`, and `model`. The typed `run()` returns an `AgentRunResult[Out]` with `.output`, `.usage`, `.cost`, `.trace_id`, `.retry_count`, `.tool_calls_made`, and `.tool_calls_failed`.

| Decorator | First arg | Purpose |
|---|---|---|
| `@agent.tool` | `RunContext[Deps]` (optional) | Tool with access to typed deps. |
| `@agent.tool_plain` | none | Tool with no context. |
| `@agent.output_validator` | `RunContext`, `output` | Validate / transform output; raise `ModelRetry(hint)` to retry. |
| `@agent.instructions_func` | `RunContext` | Append dynamic instructions per run. |

Constructor: `Agent(model, *, deps_type=NoneType, output_type=str, instructions="", name="agent", max_retries=2, cost_budget=1.0, guardrails=None, retries=0)`. See [Tools](tools.md) for tool details and [Guardrails](guardrails.md).
