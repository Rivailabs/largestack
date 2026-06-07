# Memory

`create_memory(strategy)` returns a memory backend. Pick a strategy by what you
need to remember: raw turns, important events, facts, skills, or an entity graph.

```python
from largestack.memory import create_memory

mem = create_memory("buffer")          # default
```

## Strategies

`create_memory(strategy, **kwargs)` accepts these strategy strings:

| `strategy` | Backend | What it does | Status |
|---|---|---|---|
| `"buffer"` | `ConversationMemory` | Keep every message (no eviction) | works |
| `"sliding_window"` | `ConversationMemory` | Keep the last `max_messages` (default 20) | works |
| `"token_limited"` | `ConversationMemory` | Keep recent messages within `max_tokens` (default 4000, ~4 chars/token estimate) | works |
| `"episodic"` | `EpisodicMemory` | Timestamped events scored by recency + importance + word-overlap relevance | works |
| `"semantic"` | `SemanticMemory` | Similarity recall of facts. **Default embedder is a token-overlap hash vector** (not real embeddings) | works; real embeddings opt-in |
| `"procedural"` | `ProceduralMemory` | Reusable skills (name/procedure/trigger) with keyword search + success tracking | works |
| `"observational"` | `ObservationalMemory` | Observer/Reflector notes extracted from messages (heuristic; LLM optional) | works; heuristic |
| `"graph"` | `GraphMemory` | Entity–relationship graph with neighbors, paths, subgraphs | works |

Anything else falls back to a default `ConversationMemory` (buffer).

> `SharedMemorySpace` (cross-agent shared store) and the compression helper exist
> in `largestack._memory` but are **not** `create_memory` strategies — construct
> them directly (e.g. `from largestack._memory.shared import SharedMemorySpace`).

## Conversation memory (buffer / sliding_window / token_limited)

Add and read messages. `add_message`/`add_messages` are async; `get_messages`
returns a defensive copy.

```python
import asyncio
from largestack.memory import create_memory

async def main():
    mem = create_memory("buffer")
    await mem.add_message({"role": "user", "content": "Hello"})
    await mem.add_message({"role": "assistant", "content": "Hi there!"})

    print(mem.get_messages())   # [{'role': 'user', ...}, {'role': 'assistant', ...}]
    print(len(mem), mem.token_count, mem.stats)

asyncio.run(main())
```

Eviction kicks in for the bounded strategies (system messages are preserved by
default via `include_system=True`):

```python
sw = create_memory("sliding_window", max_messages=2)
# ...after adding m0..m3, get_messages() keeps only ['m2', 'm3']
```

Other helpers: `get_by_role(role)`, `prune_older_than(keep_last)`, `clear()`.

## Semantic memory

```python
import asyncio
from largestack.memory import create_memory

async def main():
    sem = create_memory("semantic")
    await sem.add("Python was created by Guido van Rossum")
    hits = await sem.search("Who created Python?", k=1)
    print(hits[0]["content"], round(hits[0]["score"], 3))

asyncio.run(main())
```

The default backend uses a 128-dim bag-of-words **hash** vector, so it matches on
shared tokens, not meaning — paraphrases won't match. For genuine semantic recall,
construct `SemanticMemory` directly with a real embedder:

```python
from largestack._memory.semantic import SemanticMemory
sem = SemanticMemory(embedder=my_embed_fn)   # sync or async callable -> list[float]
```

## Episodic memory

```python
ep = create_memory("episodic")
await ep.add("User prefers dark mode", importance=8.0)     # importance 1–10
top = await ep.retrieve("dark mode preference", k=1)       # tri-score ranked
```

## Procedural memory

```python
pm = create_memory("procedural")
await pm.add_skill(
    name="book_flight",
    description="Search and book a flight between cities",
    procedure="1. flight_search  2. filter by price  3. book lowest",
    trigger="user wants to book travel",
)
matches = pm.search("how do I book a trip")   # keyword search; [Skill, ...]
pm.record_usage("book_flight", success=True)   # tracks success_rate
```

## Observational memory

```python
obs = create_memory("observational")
await obs.observe([{"role": "user", "content": "I always prefer tea over coffee."}])
print(obs.get_context())   # emoji-prioritized notes for LLM context
```

## Graph memory

```python
g = create_memory("graph")
await g.add_entity("Alice", "person")
await g.add_relation("Alice", "Acme", "works_at")   # entities auto-created
print(await g.neighbors("Alice"))                   # ['Acme']
print(await g.find_paths("Alice", "Acme"))          # [['Alice', 'Acme']]
```

See also: [RAG](../rag.md) for retrieval over documents.
