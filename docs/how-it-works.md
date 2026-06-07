# How Largestack Works

End-to-end reference for how a Largestack run actually executes. Statuses are kept exactly as surveyed (`verified` / `works` / `partial` / `opt-in` / `seam`) and are not inflated. Largestack is a standalone agent framework; this page describes only what its own code does.

New here? Read this page for the mental model, then follow the [Getting Started](getting-started.md) guide to run your first agent.

---

## 1. End-to-end agent-run flow

Per-request lifecycle, in order. RBAC and retrieval steps apply only to the `SecureRAGAgent` path; the bare `Agent.run()` path starts at step 4 (input guards).

```
                          AGENT-RUN PIPELINE (per request)
   ┌──────────────────────────────────────────────────────────────────────────┐
   │  (RAG path only)                                                           │
   │  [1] RBAC gate ──► [2] pre-retrieval guards ──► [3] hybrid retrieval ──┐   │
   │      rag.query?         PII+Injection on query      BM25(+dense RRF)   │   │
   │      deny→audited       block→audited               +rerank→top_k      │   │
   └────────────────────────────────────────────────────────────────────┐  │  │
                                                                          ▼  ▼  │
   [4] check_license → open OTel span → emit agent.started                      │
   [5] _build_msgs: system instructions + memory + user task (+ RAG context)    │
   [6] construct LoopGuard (max_turns, cost_budget, wall-clock timeout)         │
        │                                                                       │
        ▼   ┌─────────────────────── PER-TURN LOOP ───────────────────────┐    │
        │   │ [7]  _check_kill_switch()  → KillSwitchActivatedError        │    │
        │   │ [8]  guard.check_turn() (turns + timeout)                    │    │
        │   │ [9]  guard.check_cost_pre_call() (hard pre-flight ceiling)   │    │
        │   │ [10] context compression if enabled & >10 msgs (off default) │    │
        │   │ [11] INPUT guards: check_input(msgs) — PII+Injection ∥       │    │
        │   │ [12] LLM call: gateway.chat OR TestModel override            │    │
        │   │ [13] accumulate cost/tokens → guard.check_cost(delta)        │    │
        │   │ [14] OUTPUT guards: check_output(resp) ∥                     │    │
        │   │ [15] after-model steering (DISCARD re-prompt / INTERRUPT)    │    │
        │   │ [16] tool_calls? ─yes─► loop-fingerprint → ToolExecutor:     │    │
        │   │        perms→ToolAccessPolicy→idempotency→circuit-breaker    │    │
        │   │        →retry/backoff→timeout ; feed results back ──┐        │    │
        │   │        no─► [17] no-progress check → persist memory │        │    │
        │   └────────────────────────────────────────────────────┘────────┘   │
        │            └── on exhaustion: [18] _force_final (one last call) ──────┘
        ▼
   (RAG path only)
   [19] groundedness: HallucinationGuard(fast).analyze → score ≥ 0.5
   [20] citations: CitationEngine.cite → inline [n] + cited-sources
   [21] sanitize: OutputSanitizer strips script/iframe/JS-URI (RAG default only)
        │
        ▼
   [22] _result: write traces.db row (trace_id, agent, model, cost, tokens,
        turns, finish_reason) + build AgentResult
   [23] finally: emit agent.done, failure trace if failed, write agent.run
        audit row (HMAC chain), close OTel span
```

Cost is accumulated per-run from each response in the engine (not the shared gateway tracker) to avoid concurrency races. `OutputSanitizer` and groundedness/citations are **only** default in `SecureRAGAgent`, not in bare `Agent.run()`.

---

## 2. Feature matrix by subsystem

### Agents & Orchestration

| Feature | Module | Status | What it does |
|---|---|---|---|
| Agent (public run loop) | `agent.py` + `_core/engine.py` | verified | Async agent: input guards → LLM (gateway/TestModel) → tool loop → output guards → trace/audit, with retries + fallback + callbacks. |
| Tool calling loop | `_core/engine.py` + `_core/tools.py` | verified | Executes `tool_calls` via ToolExecutor (perms, policy, idempotency, retry/backoff, circuit-breaker, timeout); loops to text answer. |
| Structured output (`response_model`) | `_core/structured.py` | verified | `run()` routes to `run_structured` for provider-native JSON/tool_use schema + retry; returns hydrated Pydantic instance. |
| max_turns / cost_budget / timeout | `_core/loop_guard.py` | verified | LoopGuard: max_turns, cost ceiling (pre+post), repeated-toolcall fingerprint, no-progress, wall-clock timeout. |
| Kill switch | `_guard/kill_switch.py` | verified | Checked before every LLM call; raises KillSwitchActivatedError. |
| Agent retries + fallback | `agent.py` | works | Retries N times then delegates to a fallback Agent. |
| Streaming with per-chunk guards | `_core/engine.py::stream` | opt-in | Kill-switch + input guards always on; per-chunk output guards only when `stream_guard=True` (default: full-buffer only). |
| Context compression | `_core/engine.py` + `_memory/compression.py` | opt-in | Compresses middle msgs when >10, only if `context_compression` enabled (off by default). |
| Audit events (per tool-call / guard-block) | `_core/engine.py` | opt-in | Per-tool/per-guard audit rows only when `LARGESTACK_AUDIT_EVENTS=1`; per-run rows always written. |
| TypedAgent (`Agent[Deps,Out]`) | `decorators.py` | verified | Decorator-style API: `@tool` with `RunContext[Deps]`, `@output_validator` + ModelRetry, dynamic instructions, native structured output. |
| `Agent.override(TestModel)` | `agent.py` + `decorators.py` | verified | Context manager swaps gateway for TestModel/FunctionModel so the full loop runs in CI without keys. |
| Team (sequential / parallel) | `team.py` | verified | Coordinates agents with AgentContext passing, per-agent retry/skip/fallback, workflow cost budget. |
| Workflow (DAG / state_machine) | `workflow.py` + `_orchestrate/{dag,state_machine}.py` | verified | Facade over DAGWorkflow (auto-parallel, cycle/missing-dep validation) and StateMachine (cyclic, conditional). |
| Orchestrator (public facade) | `orchestrator.py` | verified | One entry point for 7 stable strategies → normalized OrchestratorResult. |
| Orchestrator durable checkpoints | `orchestrator.py` + `_state/checkpoint.py` | opt-in | Run-level started/completed/failed + resume_completed only when `durable=True`; NOT per-node replay. |
| Supervisor (LLM hierarchical routing) | `_core/multiagent.py::Supervisor` | verified | Supervisor picks a named specialist each round until FINAL_ANSWER or max_iterations. |
| Swarm (LLM handoff, no supervisor) | `_core/multiagent.py::Swarm` | verified | Agents self-route via `HANDOFF: <name>` marker until one answers. |
| Swarm (marker-routing variant) | `_orchestrate/swarm.py::Swarm` | works | Alt swarm: Agent objects + `handoff_to` allowlists + `[HANDOFF:x]`/`[TRANSFER_TO:x]` regex. |
| StructuredChatAgent (ReAct JSON) | `_core/multiagent.py` | works | JSON action/observation loop for non-function-calling models. |
| SequentialPipeline | `_orchestrate/sequential.py` | verified | A→B→C with context accumulation, transform hook, per-stage timeout, fail/skip/retry, cost/turn aggregation. |
| ParallelFanOut | `_orchestrate/parallel.py` | verified | Concurrent agents combined via concat/best/vote/first/custom with fail/skip/partial handling. |
| Router (classify + dispatch) | `_orchestrate/router.py` | works | Classifier categorizes then dispatches to a specialist route + default fallback + stats. |
| Supervisor (Erlang restart) | `_orchestrate/supervisor.py` | works | Process-supervisor restart: one_for_one/one_for_all/rest_for_one with bounded budget. |
| Debate (multi-agent critique) | `_orchestrate/debate.py` | works | N rounds of parallel critique-and-revise; rounds/consensus/judge strategies; cost/token accumulated. |
| MapReduce | `_orchestrate/map_reduce.py` | works | Semaphore-bounded parallel mapper then reducer synthesis with skip/fail handling. |
| Flow (`@start`/`@listen`) | `_orchestrate/flows.py` | partial | `run()` executes only `@start`; listeners fire via manual `emit()` (no auto-chaining). |
| AutonomousProjectBuilder | `autonomous_builder.py` | verified | LLM plan→generate→validate(compile/pytest/acceptance)→bounded patch-repair, with budgets + path-safe writes. |
| HumanInTheLoop approval | `_core/hitl.py` | opt-in | Pause-for-human (terminal/callback/queue) as `create_tool()` (`ask_human`); not auto-injected into the loop. |
| InterAgentAuth (signed handoffs) | `_guard/inter_agent_auth.py` | seam | HMAC-signed/nonce-protected messages exist but are NOT the default transport (Team/Swarm pass plain text). |

### Memory

| Feature | Module | Status | What it does |
|---|---|---|---|
| `create_memory` factory | `memory.py` | verified | Dispatches strategy → buffer/sliding_window/token_limited/episodic/observational/procedural/semantic/graph. |
| ConversationMemory (buffer/sliding/token) | `_memory/buffer.py` | verified | Message store, 3 eviction strategies, preserves system msgs, ~4 chars/token. |
| EpisodicMemory | `_memory/episodic.py` | works | Generative-Agents tri-score (recency-decay + importance + word-overlap) retrieval; `reflect()` is a stub. |
| SemanticMemory | `_memory/semantic.py` | partial | Cosine recall, but default embedder is a 128-dim bag-of-words hash (token overlap, not true semantics). |
| ProceduralMemory (skills) | `_memory/procedural.py` | works | Voyager-style skill library: keyword search + success-rate boosting + optional JSON persistence. |
| ObservationalMemory | `_memory/observational.py` | partial | Observer/Reflector notes with priority+compression; fact extraction is heuristic; an LLM-backed path is not implemented. |
| GraphMemory | `_memory/graph.py` | works | Directed entity-relation graph: BFS path-finding, subgraph extraction, JSON persistence. |
| SharedMemorySpace | `_memory/shared.py` | works | Lock-guarded cross-agent key/value with pub/sub; thread-isolated by default. |
| ContextCompressor | `_memory/compression.py` | partial | Extractive sentence-density default; LLMLingua opt-in (falls back to extractive). |
| LongTerm memory (+ DPDP) | `_memory/long_term.py` | works | Tiered `LongTermMemoryManager`, episodic/semantic/procedural scopes, TTL/purpose/lawful-basis; InMemory + SQLite. |
| Vector-search memory layer | `_memory/vector_store.py` | partial | Cosine search over a long-term store; default HashingEmbedder is token-overlap (real embedders opt-in). |
| Postgres long-term store | `_memory/postgres_store.py` | opt-in | asyncpg/psycopg2 backend mirroring SQLite; ImportError unless a pg driver is installed. |
| External adapters (Mem0/Zep) | `_memory/external_adapters.py` | seam | Mem0Memory/ZepMemory integration points for external memory services. |

### RAG

| Feature | Module | Status | What it does |
|---|---|---|---|
| `create_rag` factory + RAGPipeline | `rag.py` + `_rag/pipeline.py` | verified | chunk→BM25 pipeline (dense + reranker opt-in); `retrieve()`/`build_context()`/`as_tool()`. CRAG + eval separate. |
| Chunker (multi-strategy) | `_rag/chunker.py` | works | recursive (default) + fixed/sentence/paragraph/heading with overlap. |
| BM25 keyword retrieval + stemmer | `_rag/retriever.py` | verified | Okapi BM25 + conservative suffix stemmer; the default retrieval path. |
| Hybrid BM25 + dense + RRF fusion | `_rag/retriever.py` | verified | RRF-fuses BM25 + cosine dense when `set_embeddings()` called; degrades to BM25-only otherwise. |
| Dense embeddings (sentence-transformers) | `_rag/pipeline.py` | opt-in | `dense=True/'auto'` wires local all-MiniLM-L6-v2; falls back to BM25 if ST missing. |
| Embedder (multi-backend) | `_rag/embedder.py` | partial | Auto-resolves OpenAI/Voyage/Cohere/local/mock by keys; API backends opt-in, mock-hash fallback. |
| Reranker (keyword/cross_encoder/cohere/voyage) | `_rag/reranker.py` | works | Keyword TF-IDF+n-gram default; cross_encoder/cohere/voyage opt-in, all fall back to keyword. |
| CitationEngine | `_core/citation_sandbox.py` | verified | Maps answer sentences to docs via Jaccard overlap, inserts `[n]` markers + cited-sources (no LLM). |
| HallucinationGuard groundedness (fast) | `_guard/hallucination.py` | works | Default 'fast' = keyword/entity/number-overlap heuristic (NOT benchmarked); NLI DeBERTa opt-in. |
| SecureRAGAgent pipeline | `secure_rag.py` | verified | Composes RBAC + pre-retrieval guards + hybrid RAG + LLM + groundedness + citations + sanitization (E2E verified). |
| CRAGEvaluator (corrective RAG) | `_rag/crag.py` | partial | Score-based proceed/combine/web_search; composable, NOT wired into create_rag/SecureRAG. |
| GraphRAG | `_rag/graph_rag.py` | partial | Regex/co-occurrence entity+relation extraction over GraphMemory; NOT a Microsoft GraphRAG benchmark reproduction. |
| RAG eval metrics (RAGAS-style) | `_rag/eval.py` | partial | LLM-judge faithfulness/relevance/precision/recall; requires a judge agent, not auto-run. |
| SubQuestion + Router query engines | `_rag/query_engines.py` | partial | Decompose-then-synthesize + LLM-routed sub-engine selection; require caller agents. |
| DocumentSummaryIndex | `_rag/summary_index.py` | partial | Summary-index retrieval; standalone composable, not wired into create_rag. |

### Guardrails

| Feature | Module | Status | What it does |
|---|---|---|---|
| GuardrailPipeline (parallel, fail_closed) | `_guard/pipeline.py` | verified | Runs guards concurrently on input/output; `fail_closed=True` so a guard crash blocks (BLOCK → GuardrailBlockedError). |
| create_guardrails / Agent default guards | `guardrails.py`, `agent.py` | verified | Default = PIIGuard(warn) + InjectionGuard, auto-attached when `guardrails_enabled` (default True). |
| InjectionGuard (LLM01/LLM07) | `_guard/injection.py` | verified | Regex/heuristic injection + abuse; PROTECT blocks on 1 high-confidence or ≥2 patterns. |
| PIIGuard (LLM02) | `_guard/pii.py` | verified | Regex PII + secret + financial detection; redact/warn/block; mutates messages in place (default warn). |
| HallucinationGuard (LLM09) | `_guard/hallucination.py` | partial | Groundedness vs `set_context`; 'fast' heuristic (NOT benchmarked), off by default, needs context. |
| ToxicityGuard | `_guard/toxicity.py` | partial | Regex for violence/hate/self-harm/CSAM; off by default; ML (detoxify) opt-in, not installed. |
| TopicGuard | `_guard/topic.py` | works | Keyword/regex allow/blocklist on input+output; off by default; semantic mode needs a classifier. |
| OutputSanitizer (LLM05) | `_guard/output_sanitizer.py` | partial | HTML-escape / strip script/iframe/JS-URI; NOT in default Agent path — only SecureRAGAgent applies it. |
| ToolAccessPolicy (LLM06/ASI02) | `_guard/tool_access.py` | verified | Per-agent allow/deny + rate limit + `re.fullmatch` param validation; enforced only when `policy=` passed. |
| tool_permissions allow/deny | `_core/tools.py` | verified | Engine-level per-tool gate on every call; denial returns a recoverable tool error for self-correction. |
| tool_policy decision engine | `_guard/tool_policy.py` | partial | Risk-aware block/approve/allow per tool verb; pure decision helper — does NOT execute, not wired into loop. |
| KillSwitch | `_guard/kill_switch.py` | verified | File-flag (`~/.largestack/.kill_switch`) checked before every LLM call. |
| RedisKillSwitch | `_guard/redis_kill_switch.py` | opt-in | Distributed backend over Redis; requires redis + explicit construction (engine uses file-flag). |
| InterAgentAuth (ASI07) | `_guard/inter_agent_auth.py` | opt-in | HMAC-SHA256 signing + nonce replay + age check; NOT wired into Team/Swarm; needs `LARGESTACK_INTER_AGENT_SECRET`. |
| MemoryIntegrityChecker (LLM04/ASI06) | `_guard/memory_integrity.py` | partial | Heuristic injection/length/special-char checks + SHA-256 hash on writes; not full provenance. |
| AgentIdentityManager (ASI03) | `_guard/agent_identity.py` | works | Per-agent scoped credentials + permission checks + session expiry + token; standalone. |
| PromptGuard2 (ML injection) | `_guard/prompt_guard.py` | opt-in | Meta 86M Prompt-Guard-2; loads only with `LARGESTACK_ENABLE_PROMPT_GUARD_ML=1` + transformers, else regex fallback. |
| EnhancedPIIGuard (Presidio/spaCy) | `_guard/pii_ml.py` | opt-in | Presidio + spaCy NER passes; `LARGESTACK_ENABLE_ML_PII=1` with deps, else regex fallback. |
| NLIHallucinationGuard (DeBERTa) | `_guard/nli_hallucination.py` | opt-in | DeBERTa-MNLI entailment; `LARGESTACK_ENABLE_NLI_GUARD=1` + transformers, else keyword fallback. |
| provider_policy routing | `_guard/provider_policy.py` | partial | Blocks/redacts sensitive payloads to unapproved providers in strict/bfsi; caller must call it. |
| Guardrail policy/config | `_guard/policy.py`, `_guard/config.py` | works | GuardrailMode OBSERVE/WARN/PROTECT/STRICT + per-risk actions from env; default PROTECT, bfsi → STRICT. |

### Security

| Feature | Module | Status | What it does |
|---|---|---|---|
| CodeSandbox | `_security/code_sandbox.py` | works | Subprocess with parent-env scrubbed + AST import allowlist; NO kernel isolation (warns). Standalone. |
| E2B / LocalSandbox bridge | `_security/e2b_bridge.py`, `_core/e2b_sandbox.py` | opt-in | Firecracker microVM via `backend='e2b'`; needs e2b-code-interpreter + `E2B_API_KEY`, else scrubbed subprocess. |
| SSRF protection (builtin web tools) | `_core/builtin_tools/_url_validator.py` | verified | `validate_url` default in http_request/web_fetch/browser_navigate; rejects private/loopback/metadata IPs after DNS. |
| NetworkPolicy (ASI-SSRF) | `_security/network.py` | works | Standalone policy: resolved-IP deny ranges, public_only/lockdown, ports/methods/rate-limit; NOT auto-attached to tools. |
| EncryptionManager | `_security/encryption.py` | works | AES-GCM encrypt/decrypt + PBKDF2 derivation + key rotation; verified roundtrip. Standalone. |
| SecretStore (vault) | `_security/vault.py` | works | Encrypted local secret store: get/set/rotate; standalone. |
| MTLSManager | `_security/mtls.py` | works | Self-signed CA + per-agent cert issuance/rotation for mutual-TLS; not in default transport. |
| SBOMGenerator (LLM03) | `_security/sbom.py` | works | CycloneDX/SPDX SBOM (`largestack sbom`); supply-chain artifact, complements CI pip-audit/bandit/trivy. |
| Permissions / PermissionEnforcer | `_security/permissions.py` | works | Action + resource-limit checks with presets + optional audit; not auto-wired into the loop. |

### Governance & Enterprise

| Feature | Module | Status | What it does |
|---|---|---|---|
| RBAC (ASI03) | `_enterprise/rbac.py` | verified | Roles/permissions + wildcard + tenant scoping + `require()`/`check()`; SecureRAGAgent gates queries via `rbac.check`. |
| AuditTrail (ASI-AUDIT) | `_enterprise/audit.py` | verified | Append-only SQLite + HMAC-keyed hash chain (key off-DB); `verify_integrity` catches tampering. |
| SiemExporter | `_enterprise/siem.py` | works | Streams audit chain to syslog/CEF/LEEF/webhook via `largestack siem-export`; file+CEF live-verified, network sinks are seams. |
| HumanInTheLoop (LLM06) | `_core/hitl.py` | works | Pause-for-human (terminal/callback/queue) with timeout; an `ask_human` `@tool`. Opt-in. |
| SSOProvider / Session | `_enterprise/sso.py` | works | OIDC/SSO session issuance with TTL/refresh/expiry; standalone. |
| TenantManager (LLM08) | `_enterprise/tenant.py` | works | Per-tenant registration, rate-limit, allowed-model checks; feeds RBAC/vector-store isolation. |
| SessionStore | `_enterprise/session_store.py` | works | Pluggable session persistence (InMemory default; Redis available) + cleanup_expired. |
| PaymentWebhook / billing | `_enterprise/payment.py`, `_enterprise/billing.py` | works | Signature-verified Stripe/LemonSqueezy webhooks + license validation + UsageMeter/BudgetEnforcer. Monetization, not a guard. |
| OWASP coverage matrix | `owasp.py` | verified | Honest machine-readable self-assessment (covered/partial/not_covered) of LLM Top-10 + ASI; inspection only. |

### Observability & Monitoring

| Feature | Module | Status | What it does |
|---|---|---|---|
| Trace logging (traces.db) | `_observe/traces_db.py` | verified | Single canonical `traces` table; one row per run (success + failure), secret-redacted + truncated. |
| Monitor (public facade) | `observability.py` | verified | Self-hosted reader: list/get traces, feedback, evaluate_trace, summary (error_rate/cost/latency). |
| Prometheus metrics | `_observe/metrics.py` | verified | Thread-safe O(1)-bucket histograms + counters/gauges; `track_llm_call` (gateway) + `track_tool_call` (engine) on by default. |
| OTel SQLite span exporter | `_observe/sqlite_exporter.py` | works | Writes OTel spans to `spans` table (WAL) + query API + percentiles + retention. |
| OTel exporter setup | `_observe/otel_export.py` | opt-in | `setup_exporter()` picks langfuse/otlp/jaeger/console/sqlite; non-sqlite needs platform dep/keys; secret-redacting processor. |
| Engine OTel parent span | `_observability/otel.py` | opt-in | `agent.run` span only if `setup_otel()` ran with OTLP endpoint; `get_tracer()` is None by default (no-op). |
| gen_ai.* SDK instrumentor | `_observe/gen_ai_instrumentor.py` | partial | Patches OpenAI SDK for gen_ai.* spans; not auto-wired. |
| Log redaction filter | `_observe/log_redaction.py` | verified | Regex redaction of API keys/Bearer/JWT; auto-installed on import (off via `LARGESTACK_DISABLE_LOG_REDACTION`). |
| Anomaly detector | `_observe/anomaly.py` | works | Z-score + CUSUM + Bollinger; alerts when 2/3 agree; standalone, not auto-wired. |
| Cost dashboard monitor | `_observe/cost_dashboard.py` | partial | In-memory CostMonitor by agent/model/hour with threshold alert; standalone, not in default path. |
| Cost tracking + pricing registry | `_core/cost.py` | verified | `CostTracker.calc()` with built-in pricing + YAML overrides + longest-prefix match. |
| Per-tenant budget tracker | `_core/budget.py` | opt-in | day/month/total limits over Memory/Redis; `check_and_record` raises BudgetExceededError; caller-instantiated. |
| Self-hosted dashboard (10 views) | `_dashboard/app.py` | works | FastAPI HTML over traces.db/audit.db + Chart.js, X-API-Key auth, CSP nonces, optional RBAC + React SPA mount. |
| Dashboard JSON API | `_dashboard/api.py` | works | REST `/api/*` (overview/traces/costs/agents/guards/metrics/alerts) with API-key auth + CORS allowlist. |

### Providers

| Feature | Module | Status | What it does |
|---|---|---|---|
| Provider capability matrix | `provider_matrix.py` | verified | 26 rows, honest status: 5 verified (openai, deepseek, google, ollama, ollama_openai), 6 adapter_only, 15 partial. |
| Provider adapters | `_core/providers/` | partial | 26 `*_prov.py`; all construct (unit-tested) but most are OpenAI-compatible paths pending live verification. |
| `check_connection()` live self-test | `provider_matrix.py` | works | Minimal real call behind a model string → `{ok,detail,cost}`; honest per-key verification (needs key). |
| Native structured output (per provider) | `_core/structured.py` | verified | OpenAI json_schema, Anthropic tool_use, Gemini response_schema, Ollama format; deepseek/cohere prompt fallback. |
| Structured output retry/validation | `_core/structured_output.py` | works | `validate_json_against_schema` + `parse_with_retry` re-prompts on failure (StructuredOutputError after N). |

### Protocols

| Feature | Module | Status | What it does |
|---|---|---|---|
| MCP server | `_core/mcp_server.py` | works | Public `MCPServer` builds MCP servers from Largestack tools via `@tool/@resource/@prompt` over JSON-RPC/stdio. |
| MCP client | `_core/mcp_client.py` | works | Public `MCPClient` connects out to MCP servers (JSON-RPC 2.0 over stdio + Streamable HTTP) + capability negotiation. |
| A2A protocol v1.0 | `_core/a2a_v1.py` | partial | A2A v1.0 types: JSON-RPC, agent-card.json + JWS, SCREAMING_SNAKE task states; reference impl, not public top-level. |
| A2A reference + v0.3 + multimodal | `_a2a/` | partial | AgentCard/A2AServer/A2AClient/A2ATask, SSE streaming + signed cards, multimodal parts; seam to official SDK. |
| AG-UI protocol (public) | `_core/ag_ui.py` | works | `AGUIServer` streams 26 SSE event types (lifecycle/text/tool/state/custom); exported in top-level API. |
| AG-UI v1 event types | `_core/agui_v1.py` | partial | Alternate 25-event dataclass set (adds chunk/reasoning/raw); parallel impl, not in public top-level. |

---

## 3. Orchestration patterns

| Pattern | Module | Status | Routing / combine mechanism |
|---|---|---|---|
| Sequential | `_orchestrate/sequential.py` (also `team.py`) | verified | A→B→C, context accumulation, transform hook, per-stage timeout, fail/skip/retry. |
| Parallel | `_orchestrate/parallel.py` (also `team.py`) | verified | Concurrent fan-out, combine via concat/best/vote/first/custom, partial-error handling. |
| Router | `_orchestrate/router.py` | works | Classifier agent categorizes → dispatches to specialist route + default fallback + stats. |
| Supervisor (LLM) | `_core/multiagent.py::Supervisor` | verified | Central supervisor picks a named specialist each round until FINAL_ANSWER / max_iterations. |
| Supervisor (Erlang restart) | `_orchestrate/supervisor.py` | works | Process restart: one_for_one / one_for_all / rest_for_one with bounded restart budget (distinct class). |
| Swarm (LLM) | `_core/multiagent.py::Swarm` | verified | Self-route via `HANDOFF: <name>` marker until one agent answers (no supervisor). |
| Swarm (marker) | `_orchestrate/swarm.py::Swarm` | works | `[HANDOFF:x]`/`[TRANSFER_TO:x]` regex routing + `handoff_to` allowlists (separate impl). |
| Debate | `_orchestrate/debate.py` | works | N rounds parallel critique-and-revise; rounds / consensus / judge strategies. |
| DAG | `_orchestrate/dag.py` | verified | Auto-parallel by dependency, cycle + missing-dep validation; accepts Agent objects. |
| State machine | `_orchestrate/state_machine.py` | verified | Cyclic, conditional transitions. |
| MapReduce | `_orchestrate/map_reduce.py` | works | Semaphore-bounded parallel mapper over items → reducer synthesis, skip/fail handling. |

The public `Orchestrator` facade (`orchestrator.py`, verified) exposes only **7 stable strategies**: sequential, parallel, dag, state_machine, router, supervisor, map_reduce. Swarm / debate / Flow remain reachable only via their `_orchestrate.*` modules while their APIs evolve.

**Two easily-confused class pairs:** `multiagent.Supervisor` (LLM picks specialist) vs `_orchestrate.supervisor.Supervisor` (Erlang restart); and `multiagent.Swarm` (`HANDOFF: name`) vs `_orchestrate.swarm.Swarm` (`[HANDOFF:x]` markers + allowlists).

---

## 4. Honest gaps

- **Default-on guards are only two:** PIIGuard(warn) + InjectionGuard. Everything else (toxicity, topic, hallucination, ToolAccessPolicy, NetworkPolicy, sandbox, RBAC, audit, HITL, mTLS, vault, encryption, tenant, SSO) is opt-in / caller-wired even when implemented and unit-tested.
- **ML guards are opt-in and not installed by default:** PromptGuard2 (`LARGESTACK_ENABLE_PROMPT_GUARD_ML=1`), EnhancedPIIGuard/Presidio (`LARGESTACK_ENABLE_ML_PII=1`), NLIHallucinationGuard/DeBERTa (`LARGESTACK_ENABLE_NLI_GUARD=1`), ToxicityGuard ML (detoxify). All fall back to regex/keyword heuristics. The "fast" HallucinationGuard groundedness is an un-benchmarked overlap heuristic, and it only fires when a context is set (effectively RAG-only).
- **Embeddings default to token-overlap, not semantics:** SemanticMemory, memory `vector_store`, and the RAG default path use a bag-of-words / hashing embedder unless you supply a real `embed_fn` or install sentence-transformers. Default RAG is BM25 keyword-only; hybrid (dense) and reranking are opt-in.
- **OutputSanitizer is not in the default Agent path** — only `SecureRAGAgent` applies it by default. Sanitize yourself at the render/exec sink otherwise.
- **Tool enforcement has two layers:** engine `tool_permissions` (always enforced when set) vs the optional `ToolAccessPolicy` (rate + `re.fullmatch` param rules, only when `policy=` passed). SSRF is split too — builtin web tools use `_url_validator` (on by default), while `NetworkPolicy` is a richer standalone policy NOT auto-attached.
- **Documented integration seams (not default transport / require external services):** Qdrant/Postgres long-term store and Mem0/Zep memory adapters; SIEM network sinks (syslog/webhook); LangSmith/Langfuse/OTLP/Jaeger OTel backends (sqlite is the only no-dep path); RedisKillSwitch; InterAgentAuth (needs `LARGESTACK_INTER_AGENT_SECRET`, not the default Team/Swarm transport); E2B microVM sandbox; HITL approval.
- **Providers:** exactly 5 are live-verified (openai, deepseek, google, ollama, ollama_openai). The **Anthropic adapter is adapter_only** (structurally complete, not live-verified); 6 are adapter_only and 15 partial. 26 adapter files ≠ 26 matrix rows 1:1 (fireworks/together have files but no row; local/ollama_openai are rows without a dedicated adapter). `check_connection()` is the honest per-key verification path. See [Provider Support](provider-support.md).
- **Partial OWASP rows:** LLM03/04/05/07/08, ASI06 (memory poisoning — heuristic checker, not full provenance), ASI07 (inter-agent auth not default transport), ASI-SANDBOX (subprocess, no kernel isolation), LLM08 (vector — RBAC/tenant isolation only). LLM09 is covered but via heuristic fast-mode + citations. `owasp.py` is the self-assessment source of truth.
- **Flow (`@start`/`@listen`) is the weakest orchestration link** — `run()` executes only the `@start` function; `@listen` handlers fire via manual `emit()`, not automatic chaining from start output. Marked partial.
- **Durable checkpoints are run-level, not per-node replay** — `durable=True` persists started/completed/failed + resume_completed only; it does not replay individual DAG nodes.

---

## Next

- [Getting Started](getting-started.md) — run your first agent step by step.
- [Agent Concepts](concepts/agents.md) · [Tools](concepts/tools.md) · [Workflows](concepts/workflows.md) · [Guardrails](concepts/guardrails.md)
- [Provider Support](provider-support.md) · [Known Limitations](known-limitations.md) · [CLI Reference](cli-reference.md)
