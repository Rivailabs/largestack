# Tools

A **tool** is a Python function the model can call. Largestack reads the function's type hints + docstring and generates the JSON Schema the provider needs — you don't write schemas by hand.

There are two registration styles, matching the two agent surfaces (see [Agents](agents.md)):

| Style | Decorator | Agent |
|---|---|---|
| Classic | `@tool` (from `largestack`) → pass via `tools=[...]` | `from largestack import Agent` |
| Typed | `@agent.tool` / `@agent.tool_plain` | `from largestack.decorators import Agent` |

## Classic: `@tool` + `tools=[...]`

```python
from largestack import tool

@tool
def add(x: int, y: int) -> int:
    """Add two integers."""
    return x + y
```

Pass tools as a list when constructing the agent:

```python
import asyncio
from largestack import Agent, tool
from largestack.testing import TestModel

@tool
def add(x: int, y: int) -> int:
    """Add two integers."""
    return x + y

async def main():
    agent = Agent(name="calc", llm="openai/gpt-4o-mini", tools=[add], guardrails=False)

    # TestModel drives the tool call deterministically (no real LLM / network):
    test_model = TestModel(
        custom_output_text="done",
        custom_tool_args={"add": {"x": 2, "y": 3}},
        call_tools=["add"],
    )
    with agent.override(model=test_model):
        result = await agent.run("add 2 and 3")

    assert result.tool_calls_made == ["add"]
    assert result.content == "done"

asyncio.run(main())
```

`TestModel(call_tools=...)` controls which tools fire on the first turn: `"all"` (default), `[]` (none), or a list of names. `custom_tool_args` supplies the arguments; otherwise dummy values are generated from the schema.

### `@tool` options

`@tool` can be used bare or with keyword arguments:

| Arg | Default | Meaning |
|---|---|---|
| `timeout` | `30.0` | Per-call timeout (seconds). Sync tools get a real timeout via a thread. |
| `retries` | `1` | Retries on failure (in addition to the first attempt). |
| `idempotent` | `False` | Cache identical `(name, params)` calls for the agent's lifetime. Set only for pure functions. |
| `backoff` | `"exponential"` | `"linear"`, `"constant"`, or `"none"`. |
| `backoff_max_seconds` | `30.0` | Cap on a single backoff sleep. |
| `backoff_jitter` | `True` | ±25% randomized jitter between retries. |
| `circuit_breaker_threshold` | `0` | If `>0`, open the circuit after N consecutive failures in the window. |
| `circuit_breaker_window_seconds` | `60.0` | Failure-counting window. |
| `circuit_breaker_cooldown_seconds` | `30.0` | How long the circuit stays open. |
| `name`, `description` | from function | Override the schema name/description. |

```python
@tool(timeout=10, retries=2, idempotent=True)
def lookup(symbol: str) -> str:
    """Look up a stock symbol (pure read — safe to cache)."""
    ...
```

## Typed: `@agent.tool` / `@agent.tool_plain`

With the typed `Agent`, register tools as methods on the agent. A tool whose first parameter is `RunContext[Deps]` receives the typed dependencies; otherwise use `tool_plain`.

```python
import asyncio
from largestack.decorators import Agent, RunContext
from largestack.testing import TestModel

agent = Agent("openai/gpt-4o-mini", instructions="Be helpful.", guardrails=False)

@agent.tool
def whoami(ctx: RunContext) -> str:
    """Return a fixed id."""
    return "anon"

@agent.tool_plain
def add(x: int, y: int) -> int:
    """Add two integers."""
    return x + y

async def main():
    with agent.override(model=TestModel(custom_output_text="42", call_tools=[])):
        result = await agent.run("hi")
    assert result.output == "42"
    assert set(agent.tools) == {"whoami", "add"}

asyncio.run(main())
```

The `ctx` parameter is detected by type (`RunContext` / `RunContext[Deps]`) or, if unannotated, by name (`ctx`, `context`, `run_context`). It is stripped out of the generated schema.

## Schemas from type hints

Both styles auto-generate JSON Schema from your annotations:

| Python type | JSON Schema |
|---|---|
| `str` | `{"type": "string"}` |
| `int` | `{"type": "integer"}` |
| `float` | `{"type": "number"}` |
| `bool` | `{"type": "boolean"}` |
| `list[X]` | `{"type": "array", "items": ...}` |
| `dict[K, V]` | `{"type": "object", ...}` |
| `Optional[X]` / `X \| None` | schema for `X` |
| `Union[X, Y]` | `{"anyOf": [...]}` |
| `Literal["a", "b"]` | `{"type": "string", "enum": [...]}` |
| `Enum` subclass | `{"type": "string", "enum": [...]}` |
| Pydantic `BaseModel` | the model's `model_json_schema()` |

Parameters with no default become `required`. The docstring's first line becomes the tool description.

> Models sometimes send numbers/booleans as strings. Before execution, scalar args are best-effort coerced to their annotated type (e.g. `"19"` → `19` for an `int` parameter).

## Permissions

`tool_permissions` on the classic `Agent` is a static allow/deny list, checked before each tool runs:

```python
agent = Agent(
    name="reader",
    llm="openai/gpt-4o-mini",
    tools=[read_file, shell_command],
    tool_permissions={"allow": ["read_file"]},   # or {"deny": ["shell_command"]}
)
```

A denied tool does **not** abort the run — it returns a recoverable error to the model (so it can self-correct), and the tool name shows up in `result.tool_calls_failed`.

## ToolAccessPolicy

For runtime controls — per-agent allow/deny, rate limits, and regex parameter validation — use `ToolAccessPolicy` (OWASP ASI02). Pass it as `tool_policy=` and it is enforced inside the tool loop.

```python
import asyncio
from largestack import Agent, tool, ToolAccessPolicy
from largestack.testing import TestModel

@tool
def shell(command: str) -> str:
    """Run a shell command."""
    return "ran: " + command

async def main():
    policy = ToolAccessPolicy()
    policy.rate_limit("shell", max_calls=10, window_seconds=60)
    # fullmatch against the WHOLE value — "rm -rf /" is rejected
    policy.validate_params("shell", {"command": r"(ls|cat).*"})

    agent = Agent(name="b", llm="openai/gpt-4o-mini", tools=[shell],
                  tool_policy=policy, guardrails=False)

    test_model = TestModel(
        custom_output_text="final",
        call_tools=["shell"],
        custom_tool_args={"shell": {"command": "rm -rf /"}},
    )
    with agent.override(model=test_model):
        result = await agent.run("go")

    # The call was attempted but denied by the policy:
    assert result.tool_calls_failed == ["shell"]

asyncio.run(main())
```

| Method | Purpose |
|---|---|
| `allow(agent, [tools])` | Per-agent allowlist. |
| `deny(agent, [tools])` | Per-agent denylist (takes precedence). |
| `rate_limit(tool, max_calls, window_seconds)` | Sliding-window rate limit. |
| `validate_params(tool, {param: regex})` | Regex **fullmatch** on parameter values. |
| `cap_output(tool, max_chars)` | Truncate over-long tool output. |
| `await enforce(agent, tool, params)` | Full check → `(ok, reason)`. |

> `validate_params` uses `re.fullmatch` — the whole value must match, so a rule like `^(ls|cat)` no longer accepts `"ls; rm -rf ~"`. Still treat tool args as untrusted: never pass them straight to a shell. See [OWASP coverage](../owasp-coverage.md).

## Built-in tools

Largestack ships ready-made tools in `largestack._core.builtin_tools`. Import the ones you need and pass them in `tools=[...]`:

| Tool | Description |
|---|---|
| `web_search` | Search the web; returns top results. |
| `web_fetch` | Fetch a URL → plain text (SSRF-protected). |
| `http_request` | HTTP/HTTPS request (SSRF-protected). |
| `code_execute` | Run code in a sandbox. |
| `read_file` / `write_file` | File read / write. |
| `calculator` | Evaluate a math expression safely (`+ - * / // % **`, `sqrt`, `sin`, …). |
| `shell_command` | Restricted shell command (no shell interpretation). |
| `database_query` | Read-only SQLite `SELECT`. |
| `get_current_time` | Current date/time. |

`ALL_BUILTIN` is the full list.

```python
import asyncio
from largestack import Agent
from largestack._core.builtin_tools import calculator
from largestack.testing import TestModel

async def main():
    agent = Agent(name="math", llm="openai/gpt-4o-mini", tools=[calculator], guardrails=False)
    test_model = TestModel(
        custom_output_text="The answer is 14.",
        custom_tool_args={"calculator": {"expression": "2 * (3 + 4)"}},
        call_tools=["calculator"],
    )
    with agent.override(model=test_model):
        result = await agent.run("what is 2*(3+4)?")
    assert result.tool_calls_made == ["calculator"]

asyncio.run(main())
```

See also: [Agents](agents.md) · [Guardrails](guardrails.md) · [Memory](memory.md).
