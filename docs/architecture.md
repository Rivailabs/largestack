# Largestack AI — Architecture

## 4-Layer Microkernel

```
┌─────────────────────────────────────────────────┐
│  Layer 4: Experience                            │
│  CLI (11 cmds) │ Dashboard (10 views) │ REST    │
├─────────────────────────────────────────────────┤
│  Layer 3: Composable Capabilities               │
│  RAG │ Memory (8 types) │ Eval │ Enterprise     │
├─────────────────────────────────────────────────┤
│  Layer 2: Agent Runtime                         │
│  Engine │ Tools │ Guards │ Steering │ Cost      │
├─────────────────────────────────────────────────┤
│  Layer 1: Protocol Core (<2K LOC)               │
│  LLM Gateway │ MCP │ A2A │ OTel │ Events       │
└─────────────────────────────────────────────────┘
```

## Agent Execution Loop

```
User Task → [Kill Switch Check] → [Context Compression]
         → [Input Guardrails (parallel)]
         → [LLM Call (circuit breaker + retry + fallback)]
         → [Cost Check] → [Output Guardrails]
         → [Steering After Model]
         → [Tool Calls? → Steering Before Tool → Execute → Loop]
         → [No Tools → Return Result]
         → [Metrics + Audit Trail]
```

## Provider Fallback Chain

```
Primary Provider → [Circuit Breaker OPEN?]
    → Yes: Skip to next provider
    → No: Try with retry (3x, exponential jitter)
        → Success: Record in circuit breaker, cache, return
        → Failure: Record failure, try next provider
```

## 5-Layer Loop Termination

1. **Max iterations** (default: 25)
2. **Cost budget** (default: $5.00)
3. **Loop fingerprinting** (3 identical action hashes = stuck)
4. **No-progress detection** (5 turns with no new information)
5. **Wall-clock timeout** (default: 300s)
