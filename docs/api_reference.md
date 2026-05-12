# Largestack AI — API Reference

## Agent

```python
class Agent(name, instructions="You are a helpful assistant.", llm=None,
            tools=None, guardrails=None, memory=None, steering=None,
            cost_budget=None, max_turns=None, tool_permissions=None)
```

**Parameters:**
- `name` (str): Agent identifier for tracing and logging.
- `instructions` (str): System prompt / persona.
- `llm` (str): Model identifier. Format: `provider/model` (e.g., `openai/gpt-4o-mini`, `deepseek/deepseek-chat`, `anthropic/claude-sonnet-4-6`). Use `"auto"` for smart routing.
- `tools` (list): List of `@tool` decorated functions.
- `guardrails` (list|GuardrailPipeline): Guard names `["pii", "injection", "hallucination", "toxicity", "topic"]` or a `GuardrailPipeline` instance.
- `memory`: Memory backend. Default: `ConversationMemory(strategy="buffer")`.
- `steering` (list): List of `@steer_before_tool` / `@steer_after_model` decorated functions.
- `cost_budget` (float): Max cost per run in USD. Default: 5.0.
- `max_turns` (int): Max agent loop iterations. Default: 25.
- `tool_permissions` (dict): `{"allow": [...], "deny": [...]}`.

**Methods:**
- `await agent.run(task: str) → AgentResult` — Execute agent on task.
- `async for token in agent.stream(task: str)` — Stream response tokens.
- `agent.clone(**overrides) → Agent` — Create modified copy.

## Team

```python
class Team(agents, strategy="sequential", cost_budget=10.0)
```

**Strategies:** `"sequential"` (A→B→C), `"parallel"` (all at once).

## Workflow

```python
class Workflow(name, mode="dag", max_transitions=50)
```

**Modes:** `"dag"` (directed acyclic graph), `"state_machine"` (cyclic).

**Methods:**
- `wf.add_node(name, handler, deps=None)` — Add a node.
- `wf.add_edge(source, target, condition=None)` — Add an edge.
- `wf.set_start(name)` / `wf.set_end(*names)` — For state machines.
- `await wf.run(initial_state) → dict` — Execute workflow.

## @tool

```python
@tool(timeout=30.0, retries=1, name=None, description=None)
async def my_tool(param: str) -> str:
    """Docstring becomes tool description. Type hints become JSON Schema."""
    return "result"
```

## Steering Hooks

```python
@steer_before_tool
def guard(tool_name: str, params: dict, context: dict) -> SteeringResult:
    if tool_name == "dangerous": return interrupt("Blocked")
    return proceed()

@steer_after_model
def check(response, context) -> SteeringResult:
    if len(response.content) > 10000: return discard("Too long")
    return accept()
```

**Actions:** `proceed()`, `guide(feedback)`, `interrupt(result)`, `accept()`, `discard(feedback)`.

## AgentResult

```python
class AgentResult:
    content: str          # Agent's response
    agent_name: str       # Which agent produced this
    total_cost: float     # Total USD cost
    total_tokens: int     # Total tokens used
    turns: int            # How many loop iterations
    trace_id: str         # OpenTelemetry trace ID
    duration_ms: float    # Wall-clock time
    tool_calls_made: list[str]  # Tools that were called
    status: str           # "completed" | "failed"
```

## RAG

```python
from largestack import create_rag

rag = create_rag(documents=["..."], chunk_size=512, top_k=5)
tool_fn = rag.as_tool()  # Use as agent tool
context = rag.build_context("query")  # Manual retrieval
results = rag.retrieve("query")  # Raw results
```

## Memory Types

| Type | Import | Use Case |
|------|--------|----------|
| `ConversationMemory` | `largestack` | Chat history (buffer/sliding/token) |
| `EpisodicMemory` | `largestack` | Timestamped events with importance decay |
| `ObservationalMemory` | `largestack` | Observer+Reflector (Mastra-inspired pattern) |
| `ProceduralMemory` | `largestack` | Executable skill library (Voyager) |
| `SemanticMemory` | `largestack` | Generalized knowledge from episodes |
| `GraphMemory` | `largestack` | Entity-relationship graphs |
| `SharedMemorySpace` | `largestack` | Cross-agent shared state |
| `ContextCompressor` | `largestack._memory` | Reduce tokens (extractive/LLMLingua) |

## Guardrails

```python
from largestack import create_guardrails

guards = create_guardrails(
    pii=True,              # Detect emails, SSN, credit cards, phones, IPs
    injection=True,        # Block prompt injection attempts
    hallucination=True,    # NLI-based faithfulness check
    toxicity=True,         # Block toxic/biased content
    topic_blocklist=["politics", "religion"],
)
```

## Configuration

All settings can be set via environment variables (prefix `LARGESTACK_`), `largestack.yaml`, or code:

```bash
LARGESTACK_OPENAI_API_KEY=<openai-api-key>
LARGESTACK_DEFAULT_LLM=openai/gpt-4o-mini
LARGESTACK_MAX_TURNS=25
LARGESTACK_COST_BUDGET=5.0
LARGESTACK_TRACE_ENABLED=true
LARGESTACK_SMART_ROUTING=false
LARGESTACK_SEMANTIC_CACHE=true
```
