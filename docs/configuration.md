# Configuration

Largestack AI uses a 4-level configuration hierarchy:

1. **Defaults** — sensible built-in values
2. **Environment variables** — `LARGESTACK_*` prefix (e.g., `LARGESTACK_OPENAI_API_KEY`)
3. **YAML config** — `largestack.yaml` in project root or `~/.largestack/config.yaml`
4. **Code** — `Agent(cost_budget=10.0)` overrides everything

### Provider API keys
- A `.env` in the project (or a parent dir) **auto-loads** on `import largestack` — it never overrides an already-set variable (real shell/CI/Docker secrets win). Disable with `LARGESTACK_NO_DOTENV=1`.
- Key resolution per provider: `LARGESTACK_<PROVIDER>_API_KEY` → the provider's conventional name (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`/`GOOGLE_API_KEY`, …) → a `*_api_key` field in `providers.yaml`.
- `largestack setup` writes a `.env` for you (and gitignores it).

## Full Configuration Reference

```yaml
# largestack.yaml

# ── Agent defaults ──
default_llm: openai/gpt-4o-mini
max_turns: 25
cost_budget: 5.0

# ── LLM Provider Keys ──
# Set via env vars (LARGESTACK_OPENAI_API_KEY) or here
# openai_api_key: <openai-api-key>
# anthropic_api_key: <anthropic-api-key>
# deepseek_api_key: <deepseek-api-key>
# google_api_key: ...
# groq_api_key: gsk_...
# mistral_api_key: ...
# together_api_key: ...
# fireworks_api_key: ...
# cohere_api_key: ...
# azure_openai_key: ...
# azure_openai_endpoint: https://your-resource.openai.azure.com
# bedrock_region: us-east-1
# ollama_base_url: http://localhost:11434

# ── Observability ──
trace_enabled: true
trace_db_path: ~/.largestack/traces.db
metrics_enabled: true

# ── Guardrails ──
guardrails_enabled: true
pii_detection: true
injection_detection: true
hallucination_detection: false   # Enable for RAG apps
toxicity_detection: false
# topic_blocklist: "politics,religion"

# ── Kill Switch ──
kill_switch_backend: file        # file or redis
# redis_url: redis://localhost:6379

# ── Smart Features ──
smart_routing: false             # Thompson Sampling model selection
semantic_cache: true             # 3-tier response caching
context_compression: false       # LLMLingua for long contexts

# ── Dashboard ──
dashboard_host: 127.0.0.1
dashboard_port: 8787
```
