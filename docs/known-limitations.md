# Known Limitations

LARGESTACK is a **production-grade candidate** Python framework. This document lists verified limitations, optional-backend constraints, and launch gates so production claims stay evidence-based.

## Runtime

- **Cost tracker is module-global, not per-run.** Two concurrent agents share the same `CostTracker` instance and its `run_cost`/`run_tokens` accumulate together. For per-run accounting, instantiate separate `Agent` objects with separate `LLMGateway` instances, or read `AgentResult.total_cost` / `total_tokens` only — these are populated correctly per call.
- **Tool idempotency cache has no TTL or size bound.** It grows unbounded for long-lived agents. Reset with `agent._tool_exec._idem.clear()` between batches, or restart the process periodically.
- **Vision path bypasses some engine logic.** Image messages skip parts of the loop guard / memory write-back / tool retry path.

## Provider Layer

- **Error normalization completed for**: OpenAI, Anthropic, Google, Cohere, Ollama, Bedrock, DeepSeek, Groq (via OpenAI base). Other 17+ adapters inherit from OpenAIProvider, so basic HTTP errors are wrapped, but provider-specific quirks (Azure deployment URLs, Vertex auth, etc.) may bypass `ProviderError` and not trigger fallback.
- **Structured output forwarded for**: OpenAI (response_format, tool_choice, seed, top_p, stop), Anthropic (tool_choice, top_p, top_k, stop_sequences), Google (responseMimeType + responseSchema), Cohere (response_format, tool_choice). Other providers ignore unknown kwargs.
- **Bedrock requires `boto3`** to be installed. Without it, `BedrockProvider` raises `ProviderError` (was `ImportError`) so fallback works.

## Schema Generation

Supported in `_type_to_schema` (used by `@tool`):

- primitives: `str`, `int`, `float`, `bool`
- `Optional[X]`, `X | None` (PEP 604)
- `Union[X, Y]`, `X | Y` (PEP 604) → `anyOf`
- `list[X]`, `List[X]` → array with `items`
- `dict[K, V]`, `Dict[K, V]` → object with `additionalProperties`
- `Literal["a", "b"]` → enum
- `Enum` subclass → enum with values
- Pydantic `BaseModel` → `model_json_schema()`

Not yet:

- Discriminated unions
- Custom `Annotated[...]` constraints (e.g., `conint`, `Field`)
- Forward references resolved across modules
- TypedDict beyond simple cases

## Cache

- Semantic cache key includes `tools`, `temperature`, `max_tokens`, `response_format`, `tool_choice`, `top_p`, `seed`. Other behavior-affecting kwargs are not in the key.
- Cache is in-memory only; not shared between processes.

## Enterprise

- **RBAC**: SQLite-backed in `largestack._enterprise.rbac.RBAC` with optional tenant scoping via `add_user_for_tenant()` / `check_for_tenant()`. JWT/OIDC integration via the `_enterprise/sso.py` scaffolding. Tenant isolation is opt-in (call the `_for_tenant` variants); the bare `check()` method is global.
- **Audit trail**: hash-chain implementation exists; storage is SQLite by default. Signed export and retention policies are configurable via the `audit:` block in `agent.yaml`.
- **SSO**: SAML/OIDC scaffolding only — no E2E integration tests in CI.
- **Billing/metering**: SQLite-based; no concurrent-safe per-tenant boundaries.
- **Vault**: `largestack._security.vault.SecretStore` supports local file, HashiCorp Vault, AWS Secrets Manager, and Azure Key Vault backends (KMS-grade integrations). All require their respective SDKs (`boto3`, `hvac`, `azure-keyvault-secrets`).
- **Sandbox**: Python-level isolation by default; E2B remote sandbox is opt-in via `largestack._security.e2b_bridge`.

## RAG

- Retrieval works; **rerank, faithfulness check, citation confidence are partially implemented**.
- Vector store is in-memory by default; pgvector adapter exists but tenant filters and metadata indices are not enforced.
- Graph RAG is conceptual.

## Deployment

- Dockerfile copies source before pip install; runs as non-root `largestack` user; healthcheck imports the package (does not hit a live endpoint).
- docker-compose has dev defaults (`POSTGRES_PASSWORD=largestack_dev_change_me` fallback). For production, override via `.env` or use the Helm chart.
- Helm charts ship under `deploy/helm/largestack/` and `deploy/helm/largestack/`. Chart versions are pinned independently from package version per Helm convention.
- Production secrets via `largestack._security.vault.SecretStore` — supports HashiCorp Vault, AWS Secrets Manager, Azure Key Vault.

## Tests

- Unit test count is high, but a meaningful share are source-inspection or import-only tests. Genuine runtime E2E tests for typed-agent concurrency, structured-output flow-through, and provider fallback under HTTP 500 / timeout / malformed JSON are present in v0.3.3+ but coverage is not exhaustive.
- No CI smoke test for Docker container startup yet.
- No CLI smoke tests (`largestack new`, `largestack dev`, `largestack run`).

## Documentation

- Per-version CHANGELOG entries are CI-verified for accurate test counts. Other claims (LOC, component counts) are author-provided and may drift.

---

If anything here is wrong or out of date, file an issue. Honest framing is a release blocker, not a nice-to-have.
