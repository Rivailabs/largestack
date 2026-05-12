# Largestack AI Productization Pillars

Largestack AI uses `largestack` for package/import/CLI and **Largestack AI** for the product brand.

## Onboarding

- First command path: `pip install largestack`, `largestack init support-ticket-ai`, `largestack doctor`, `largestack explain project`, `largestack run app/main.py`.
- Beginner config lives in YAML. Advanced implementation lives under `app/`.
- Generated projects include comments, examples, a file-by-file README, offline tests, and safe defaults.

## Templates

Flagship: `support-ticket`.

Catalog:

- `support-ticket`
- `rag`
- `code-review`
- `ml-automation`
- `website-builder`
- `video-pipeline`
- `social-media`
- `bfsi`
- `document-extraction`

Every template must pass: `init`, `doctor`, `explain`, `graph`, `run`, and generated `pytest`.

## Integrations

Integration metadata lives in `largestack/_integrations/registry.py`.

Initial registry:

- Jira, Slack, GitHub
- Postgres, pgvector
- Qdrant, Chroma, OpenSearch
- YouTube
- Stripe, Razorpay
- MCP

Every integration entry declares env vars, risk type, approval behavior, install hint, test command, and example usage.

## RAG Depth

Beginner commands:

- `largestack rag build`
- `largestack rag test`
- `largestack rag explain`
- `largestack rag inspect`

Supported starter modes are local, vector, hybrid, graph, and SQL+vector. Optional vector database SDKs remain optional; commands explain missing extras instead of crashing.

## Visual Workflows

Beginner commands:

- `largestack graph`
- `largestack graph --mermaid`
- `largestack graph --write`
- `largestack graph --html`

Generated reports show route, mode, RAG, tools, approvals, and Mermaid text. The HTML report is intentionally local/static and safe to open.

## Observability UI

Supported product surface:

- `largestack dashboard`
- `largestack trace`
- `largestack cost`

The dashboard remains the local/self-hosted UI. It is protected by API-key auth in production, includes security headers, and is validated by dashboard/security tests.

## Enterprise Governance

Existing controls are reused rather than duplicated:

- Guardrail modes: warn, protect, strict, custom.
- BFSI strict config: approved providers, maker-checker, audit.
- RBAC/SSO/tenant/audit modules under `largestack/_enterprise`.
- Deployment guidance under `docs/DEPLOYMENT.md`, `docs/SOAK_TEST.md`, and `docs/CONTROL_PLANE_READINESS.md`.

## Ecosystem Maturity

Release confidence comes from:

- Full unit/security/integration test gates.
- Template matrix smoke validation.
- `scripts/productization_100.py` for 100 real product-surface scenarios.
- DeepSeek live benchmark and 100+ live scenario sweep when a key is exported.
- Docker, Helm, Bandit, pip-audit, gitleaks, package build, and twine checks.
