# Changelog

The authoritative, full changelog lives in
[`CHANGELOG.md`](https://github.com/Rivailabs/largestack/blob/main/CHANGELOG.md) at the
repository root, and releases are listed on
[GitHub Releases](https://github.com/Rivailabs/largestack/releases).

## Latest — v1.1.1

- **Correctness:** litellm error-mapping crash, cost-budget double-count, DAG `cost_budget`,
  tool-argument coercion, denied-tool recovery, cost prefix-matching, Debate cost, Flow
  listener duplication, `UsageMeter.record()`.
- **Security:** HMAC-keyed audit chain, SSRF name+IP blocking, sandbox env-scrub + AST
  imports, `ToolAccessPolicy` enforced + `re.fullmatch`, fail-closed webhook + Ed25519
  license signing, KDF hardening, inter-agent-auth secret.
- **Observability:** failure-path tracing, real `finish_reason`, OTel parent span + trace
  correlation, trace-content redaction, corrected dashboard queries.
- **Wedge:** `SecureRAGAgent` (see the [Secure RAG guide](guides/secure_rag.md)), an
  [OWASP coverage matrix + red-team](owasp-coverage.md) (`largestack owasp` / `largestack redteam`),
  RAG hybrid retrieval + BM25 stemming, Ollama native structured output, SIEM exporter,
  SBOM, `OutputSanitizer`, SSO-OIDC tests.
- **Honesty:** provider matrix kept truthful (Anthropic `adapter_only`); no
  competitor-replacement claims; OWASP rows marked `partial` where controls are opt-in.

For the complete, per-version history see the root `CHANGELOG.md` linked above.
