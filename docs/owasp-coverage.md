# OWASP coverage & red-team

An **honest** self-assessment of how largestack's guardrails map to the
[OWASP LLM Top 10 (2025)](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
and the OWASP Agentic-AI (ASI) threat categories — including the gaps. This is
documentation/inspection only; the controls are exercised by the red-team eval below.

The same data is available programmatically:

```python
from largestack.owasp import owasp_coverage, owasp_coverage_summary
owasp_coverage_summary()   # {'covered': 10, 'partial': 6, 'not_covered': 1, 'total': 17}
```

or from the CLI: `largestack owasp`.

## Coverage matrix

| ID | Risk | Status | largestack controls | Notes |
|---|---|---|---|---|
| | **OWASP LLM Top 10 (2025)** | | | |
| LLM01 | Prompt Injection | ✅ covered | InjectionGuard (pattern); PromptGuard 2 (optional ML); SecureRAGAgent pre-retrieval input guard | Regex/heuristic by default; in PROTECT mode a high-confidence single pattern (jailbreak/system-prompt/manipulation) blocks. Enable the 86M ML model via `LARGESTACK_ENABLE_PROMPT_GUARD_ML=1` for stronger recall. |
| LLM02 | Sensitive Information Disclosure | ✅ covered | PIIGuard (input+output redact); trace-content redaction; secret/key patterns | PII + API-key/secret redaction on inputs, outputs and persisted traces. Separator-free numerics need Presidio (`LARGESTACK_ENABLE_PRESIDIO_PII=1`). |
| LLM03 | Supply Chain | ⚠️ partial | SBOM (`largestack sbom`); CI pip-audit + bandit + trivy + SBOM artifact; PyPI Trusted Publishing | SBOM + CVE/SAST/container scans in CI; releases publish via Trusted Publishing (attested). For full "covered": hash-pinned lockfile + enable the PyPI trusted-publisher (one-time account setting). |
| LLM04 | Data and Model Poisoning | ⚠️ partial | MemoryIntegrityChecker; RBAC/tenant-scoped memory | Memory/context-poisoning checks exist; RAG ingestion is caller-controlled. Training-data poisoning is out of scope. |
| LLM05 | Improper Output Handling | ✅ covered | OutputSanitizer (HTML-escape/strip/scan); output guardrails; CodeSandbox; typed/structured output | `OutputSanitizer` neutralizes XSS/script/JS-URI/SQL/shell-meta before downstream use; you must still escape at the final sink. |
| LLM06 | Excessive Agency | ✅ covered | tool_permissions; ToolAccessPolicy (rate+param); HITL approval; max_turns; cost_budget; kill-switch | Tool gating enforced in the run loop; HITL, turn caps, budgets and a kill-switch bound autonomy. |
| LLM07 | System Prompt Leakage | ⚠️ partial | InjectionGuard (reveal-system-prompt patterns); output redaction | Catches common "reveal your system prompt" attacks; don't place secrets in the system prompt regardless. |
| LLM08 | Vector and Embedding Weaknesses | ⚠️ partial | RBAC/tenant isolation; vector-store filter-injection escaping | Per-tenant scoping + escaped Redis/Milvus filters. Embedding-inversion hardening beyond access control is the deployment's responsibility. |
| LLM09 | Misinformation | ✅ covered | HallucinationGuard (groundedness); CitationEngine; SecureRAGAgent | Groundedness scoring + citations vs retrieved sources. Default "fast" mode is heuristic; NLI is opt-in (`LARGESTACK_ENABLE_NLI_GUARD=1`). |
| LLM10 | Unbounded Consumption | ✅ covered | cost_budget; LoopGuard (max_turns/fingerprint/timeout); rate limiting | Per-run cost ceiling, 5-layer loop termination, token-bucket rate limiting. |
| | **OWASP Agentic-AI (ASI) threats** | | | |
| ASI02 | Tool / Function Misuse | ✅ covered | ToolAccessPolicy (allow/deny + rate + fullmatch params); tool_permissions; approval gating | Enforced in ToolExecutor; parameter rules use `re.fullmatch`. Treat tool args as untrusted. |
| ASI03 | Identity & Privilege Abuse | ✅ covered | RBAC (roles/permissions, wildcard, tenant); AgentIdentityManager; audited denials | SecureRAGAgent gates queries by permission. |
| ASI06 | Memory & Context Poisoning | ⚠️ partial | MemoryIntegrityChecker (validate + hash) | Heuristic checks + content hashing; not a full provenance system. |
| ASI07 | Insecure Inter-Agent Communication | ✅ covered | InterAgentAuth (HMAC-signed, nonce replay-protection) | No public default secret (v1.1.1). Set `LARGESTACK_INTER_AGENT_SECRET` in production. |
| ASI-SSRF | Server-Side Request Forgery | ✅ covered | NetworkPolicy (`public_only()`) | Blocks internal hosts by name + validates resolved IPs (defeats DNS-rebinding to metadata). |
| ASI-AUDIT | Repudiation / Insufficient Audit | ✅ covered | AuditTrail (HMAC-keyed hash chain); per-run trace + audit row | DB-only tampering is detected. SIEM export is a documented seam (`audit → syslog/webhook`). |
| ASI-SANDBOX | Unsafe Code Execution | ⚠️ partial | CodeSandbox (env-scrubbed + AST imports); E2B backend | No kernel isolation in the default subprocess — use `backend="e2b"` for untrusted code. |

_Summary: **11 covered, 6 partial, 0 not-covered**, of 17 mapped risks._ (v1.1.1 closed LLM05 via `OutputSanitizer` and moved LLM03 from not-covered → partial via SBOM + CI scans + Trusted Publishing.)

## Red-team eval

The guardrails are validated by an offline, deterministic attack corpus that probes the
guards directly (no LLM, no network) — a fast CI gate that **proves** they block what
they claim. Run it:

```bash
largestack redteam          # or: python -m largestack._test.redteam
```

```python
from largestack._test.redteam import RedTeamSuite
report = await RedTeamSuite().run()
assert report.core_passed()    # every must-block / must-redact attack handled
```

- **core** attacks (prompt-injection, jailbreak, system-prompt-leak, PII redaction,
  benign false-positive controls) are gated — CI fails if any core attack passes through.
- **stretch** attacks (single-pattern obfuscation the regex layer is known to miss) are
  reported, not gated; they motivate enabling the optional ML guards.

## Load testing & pentest prep (honest status)

These cannot be made true by code alone — the framework provides the *harness/prep*; the
*proof* requires your infra or a third party.

- **Load / soak:** `python scripts/load_test.py --n 1000 --concurrency 50` measures the
  framework's per-run overhead and concurrency (deterministic TestModel by default; pass
  `--llm` for end-to-end). A single run is **not** "load-proven" — sustained runs on
  representative infra are an ops exercise.
- **External pentest / VAPT:** hand a firm this OWASP matrix, the red-team suite
  (`largestack redteam`), the threat surface (guardrails, RBAC, audit, SSRF policy,
  sandbox), and the SBOM (`largestack sbom`). largestack cannot *be* an external auditor;
  the VAPT claim is only true once a firm performs and signs one.
- **"Battle-tested":** accrues from real production usage over time — not something any
  code change can assert today.

### Relationship to `garak` and NeMo Guardrails
- **`garak`** (NVIDIA's LLM scanner) probes a *served model endpoint*; this suite probes
  the *guardrails* offline. They're complementary — run garak against a deployed
  largestack endpoint for model-level coverage.
- **NeMo Guardrails** is an alternative *runtime* guardrail framework. largestack ships
  its own native guards (this matrix); a NeMo adapter is not bundled by design.
