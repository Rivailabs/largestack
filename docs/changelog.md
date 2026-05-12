# Largestack AI — Changelog

## v0.1.1 (April 2026) — Research-Driven Release


### Security — OWASP Agentic Top 10
- **ASI02 Tool Access Control** — `ToolAccessPolicy`: per-agent allow/deny lists, rate limiting, parameter regex validation, output size caps
- **ASI03 Agent Identity** — `AgentIdentityManager`: scoped credentials per agent, permission checks, session TTL, token verification
- **ASI06 Memory Integrity** — `MemoryIntegrityChecker`: 10 injection patterns, SHA-256 tamper detection, content length limits
- **ASI07 Inter-Agent Auth** — `InterAgentAuth`: HMAC-SHA256 message signing, replay protection, message age expiry

### Bug Fixes
- Fixed `.jpg` MIME detection (was missing leading dot)
- Fixed nested JSON parsing in structured output (balanced brace counting replaces regex)
- Fixed `self.max_retries` → `self.retries` AttributeError on retry
- Fixed Lepton provider URL (was hardcoded to llama3 model)
- Fixed session encryption fallback now logs warning when `cryptography` not installed
- Removed dead `messages = []` code block in session.py
- Version bumped to 0.1.1 in pyproject.toml

### Protocol Trifecta
- **AG-UI protocol server** — LARGESTACK supports MCP + A2A + AG-UI protocols

### Observability
- **OTEL export** to Langfuse, OTLP (Jaeger/Grafana/Datadog), Console (was SQLite-only)
- **Agent health monitoring** — status, error rates, latency tracking per agent

### Providers
- **25 LLM providers** (was 12): +Perplexity, +Cerebras, +SambaNova, +OpenRouter, +xAI/Grok, +AI21, +Lepton, +NVIDIA NIM, +Replicate, +Databricks, +Cloudflare, +Voyage, +Anyscale

### Evaluation
- **LLM-as-judge** — evaluate agent outputs with configurable criteria
- **Regression testing** — golden test suites with automatic regression detection

### Security
- **Sandboxed code execution** — subprocess (resource limits) + Docker (network isolation) + E2B (cloud)

### Agent Capabilities
- **Vision/image support** — `agent.run("Describe", images=["photo.png"])`
- **Structured output** — `agent.run("Analyze", response_model=MySchema)`
- **Agent-level retry + fallback** — `Agent(max_retries=3, fallback=backup_agent)`
- **Completion callbacks** — `Agent(on_complete=fn, on_error=fn)`

### Multi-Agent
- **Structured AgentContext** — full metadata between agents (not string-only)
- **Error recovery** — skip, retry, or fallback per agent in Team
- **Workflow cost budget** — `Team(cost_budget=2.00)`, `Workflow(cost_budget=5.00)`
- **DAG/StateMachine accept Agent objects** — no wrapper needed
- **Agent registry** — discover agents by capability

### Sessions
- **3 backends** — SQLite, Redis, PostgreSQL
- **Session TTL** — automatic cleanup of expired sessions
- **Session export** — export conversation history as JSON

### Developer Experience
- **REST API server** — `largestack serve agent.py` → POST /run, /stream
- **K8s probes** — /readyz, /livez endpoints
- **5 project templates** — `largestack init my-project --template research`
- **Human-in-the-loop** — terminal, callback, or async queue backends

## v0.1.0 (April 2026) — Initial Release

- 13 LLM providers with real streaming
- Steering hooks (programmatic agent control)
- Circuit breaker per provider
- Kill switch (file + Redis)
- 5-layer loop guard
- 7 guardrail types
- 8 memory types
- 10 orchestration patterns
- MCP client + server
- A2A server
- RAG pipeline (BM25 + hybrid)
- Cost tracking + budget enforcement
- CLI (11 commands)
- Dashboard (10 views)
- 28 documentation pages
