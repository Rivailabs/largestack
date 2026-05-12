# LARGESTACK Benchmarks

Honest performance comparison: LARGESTACK vs raw OpenAI SDK, with notes on
how we compare to Agno's "10000x faster than LangGraph" claim.

## Methodology

We measure three things that actually affect real applications:

1. **Cold-start instantiation** — `Agent()` constructor time. This is
   what Agno's marketing benchmark measures. Mostly meaningless for real
   workloads (one-time cost amortized over thousands of requests).

2. **Hot-path agent.run() with mocked LLM** — measures LARGESTACK overhead
   excluding the LLM round-trip (which dominates real workloads at
   100-2000ms). This is the framework tax — what LARGESTACK adds vs.
   calling OpenAI's HTTP API directly.

3. **Memory footprint** — bytes of resident memory per Agent instance.
   Matters if you create thousands of agents (rare but real for swarm
   patterns).

## Running

```bash
# Cold-start + memory comparison
python benchmarks/competitor_compare.py

# Hot-path with mocked LLM (no API key needed)
python benchmarks/agent_latency.py

# Decorator overhead
python benchmarks/decorator_overhead.py
```

## Honest results (on a 2024 reference laptop, no GPU)

| Operation | Time | Notes |
|---|---:|---|
| `OpenAIProvider()` cold start | ~0.3 μs | v0.5.0 lazy init (was ~10ms) |
| `Agent()` cold start | ~50 μs | 90% of which is Pydantic / decorators |
| `agent.run()` overhead (mocked LLM) | ~2 ms | Loop guard + cost tracker + audit emit |
| `agent.run()` real (gpt-4o-mini, ~100 tokens) | ~800 ms | LLM dominates; framework <0.5% of total |
| Memory per Agent | ~12 KB | Includes default tool registry |

## Honest comparison to Agno's claims

Agno claims **"10000x faster agent instantiation than LangGraph"** and
**"50x less memory"**. Two things are true:

1. The claim is mathematically defensible if you measure only the cold
   constructor. Agno defers HTTP client setup; LangGraph eagerly creates
   `httpx.AsyncClient` (which calls `ssl.create_default_context()` —
   ~10ms one-time cost).

2. The claim is **practically meaningless**. From the [Hacker News
   discussion](https://news.ycombinator.com/item?id=43274435): once you
   actually run an agent, the SSL setup happens anyway. Amortized over
   2+ requests, the difference is "not even a rounding error."

LARGESTACK v0.5.0 applies the same lazy-init trick (see
`largestack/_core/providers/openai_prov.py`). Cold-start is now ~0.3μs,
matching Agno's order of magnitude. **This does not make your agent
faster** — it just makes the constructor microbenchmark look good.

## What actually makes agents fast in production

In rough order of impact (highest first):

1. **Pick a fast model.** GPT-4o-mini is ~3x faster than GPT-4o. Claude
   Haiku is ~2x faster than Sonnet. DeepSeek-chat is ~2-4x cheaper than
   either. Local Ollama on a good GPU eliminates network latency.

2. **Reduce LLM round-trips.** Better prompts that need fewer tool calls.
   `parallel_tool_use=True` runs independent tools concurrently.

3. **Stream the response.** `agent.stream()` shows tokens as they arrive
   — perceived 5-10x faster even though total time is identical.

4. **Cache identical prompts.** LARGESTACK has semantic cache enabled by
   default for repeat queries (see `largestack/_core/cache.py`).

5. **Use HTTP/2.** All LARGESTACK providers do this already (`http2=True` in
   the httpx clients).

Framework instantiation overhead is **never** in the top 5.
