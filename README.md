# Largestack AI

Largestack AI helps you build practical AI agent apps without starting from a blank file. Start with a working support-ticket project, inspect the generated agents/tools/workflow/RAG/guardrails, then edit simple YAML before touching Python.

Public brand: **Largestack AI**. Package, import, and CLI: `largestack`.

## 5-Minute Quickstart

Install, create the flagship support-ticket demo, inspect it, and run it:

```bash
pip install largestack
largestack init support-ticket-ai
cd support-ticket-ai
largestack doctor
largestack explain project
largestack explain agents
largestack explain workflow
largestack explain rag
largestack explain guardrails
largestack graph --mermaid
largestack run app/main.py
largestack test
```

What to edit first:

1. `agents.yaml` — rename roles and responsibilities.
2. `tools.yaml` — add read tools; keep write/delete/send/payment tools approved.
3. `app/rag/knowledge/` — add docs, then run `largestack rag build`.
4. `workflow.yaml` — choose `sequential`, `parallel`, `router`, `supervisor`, or `debate`.
5. `guardrails.yaml` — use `protect` by default, `strict` for BFSI/customer-sensitive work.

## Install Options

For local development from this checkout:

```bash
python3.12 -m venv .venv-final
. .venv-final/bin/activate
python -m pip install -U pip
python -m pip install -e '.[dev,test,rag,guard]'
```

For a wheel install:

```bash
python -m build
python -m pip install dist/largestack-1.0.0-py3-none-any.whl
```

## Templates

Other built-in templates:

```bash
largestack templates
largestack templates explain support-ticket
largestack init rag-demo --template rag
largestack init code-review-demo --template code-review
largestack init ml-demo --template ml-automation
largestack init website-demo --template website-builder
largestack init video-demo --template video-pipeline
largestack init social-demo --template social-media
largestack init bfsi-demo --template bfsi
largestack init extraction-demo --template document-extraction
```

## Productization Pillars

Largestack AI is being hardened around eight beginner and ecosystem surfaces:

- Onboarding: a 5-minute path from install to running app.
- Templates: polished starter projects with generated tests.
- Integrations: registry metadata with risk and approval behavior.
- RAG depth: local, vector, hybrid, graph, and SQL+vector starters.
- Visual workflows: text, Mermaid, and local HTML reports.
- Observability UI: dashboard, trace, cost, guardrail/RAG visibility.
- Enterprise governance: strict/BFSI, audit, RBAC/SSO/tenant controls.
- Ecosystem maturity: 100-scenario productization validation and release gates.

See `docs/PRODUCTIZATION_PILLARS.md`.

Offline, no API key:

```bash
python examples/00_offline_test_model.py
```

Cloud provider examples prefer DeepSeek when configured:

```bash
export LARGESTACK_DEEPSEEK_API_KEY=<deepseek-api-key>
python examples/01_hello/main.py
python examples/02_tools/main.py
python examples/05_rag_knowledge/main.py
```

Use OpenAI explicitly only when that is your intended provider:

```bash
export LARGESTACK_OPENAI_API_KEY=<openai-api-key>
export LARGESTACK_DEFAULT_MODEL=openai/gpt-4o-mini
python examples/01_hello/main.py
```

## Minimal Agent

```python
from largestack import Agent

agent = Agent(name="assistant", llm="deepseek/deepseek-chat", instructions="Be concise.")
result = await agent.run("Say hello")
print(result.content)
```

For deterministic tests, use `TestModel` instead of a cloud provider.

## Main Capabilities

- Core SDK: `Agent`, typed decorator agents, tools, teams, workflows, and testing helpers.
- Providers: DeepSeek, OpenAI, Anthropic, Google, Groq, Cohere, Ollama, Bedrock, LiteLLM, and adapter catalogs.
- Tool calling: sync/async tools, schema generation, idempotency controls, permissions, timeouts, and retries.
- Memory and RAG: buffer, semantic, graph, procedural, shared memory, retrievers, rerankers, vector stores, citations.
- Guardrails and security: PII, injection, toxicity, topic, hallucination checks, RBAC, vault, tenant scoping, audit chain.
- Observability: health monitor, event recorder, traces, cost accounting, dashboard/API, OTEL helpers.
- Deployment: Dockerfiles, Compose, Helm chart tests, release validation script.

## Examples

See `docs/EXAMPLES.md`. Required quick examples:

```bash
python examples/00_offline_test_model.py
python examples/rag_basic/rag_basic.py
python examples/01_hello/main.py
python examples/02_tools/main.py
python examples/03_team/main.py
python examples/04_guards/main.py
python examples/05_rag_knowledge/main.py
python examples/10_full_app/main.py
```

Cloud examples skip cleanly with a clear message when no provider key is configured.

## Testing And Validation

```bash
python -m pytest tests -q --tb=short --disable-warnings -ra --timeout=180 --timeout-method=thread --durations=30
python scripts/smoke_test_e2e.py
python scripts/scenario_kyc_nbfc.py
python scripts/scenario_rag_legaltech.py
python scripts/scenario_breach_dpdp.py
scripts/final_release_validate.sh
```

Live DeepSeek tests run only when `LARGESTACK_DEEPSEEK_API_KEY` is present in the environment. Never commit `.env` or paste keys into source files.

## Security

Before release run Bandit, pip-audit, and a secret scan. Medium/high Bandit findings and known vulnerabilities are release blockers unless explicitly triaged with containment. Low Bandit findings must be documented when retained. See `docs/SECURITY.md`.

## Docker

```bash
docker build -t largestack:test .
docker build -f deploy/Dockerfile -t largestack:deploy-test .
docker run --rm -d --name largestack-test -p 8787:8787 -e LARGESTACK_API_KEY=test-key -e LARGESTACK_DASHBOARD_KEY=test-key largestack:test
curl -i http://localhost:8787/health
curl -i -H 'X-API-Key: test-key' http://localhost:8787/api/metrics
curl -i -H 'X-API-Key: wrong-key' http://localhost:8787/api/metrics
docker rm -f largestack-test
```

## Release Status

Current classification should be based on the latest `FINAL_VALIDATION_SUMMARY.md`, not on old generated reports. Known limitations are tracked in `docs/known-limitations.md` and must be reviewed before public release. A controlled pilot requires: full pytest pass, smoke/scenario pass, DeepSeek live validation when key is configured, clean package build, Bandit medium/high clean, pip-audit clean, Docker build/runtime healthcheck, and no committed secrets.

## Documentation

- `docs/QUICKSTART.md`
- `docs/PROVIDER_SETUP.md`
- `docs/EXAMPLES.md`
- `docs/TESTING_AND_VALIDATION.md`
- `docs/DEPLOYMENT.md`
- `docs/SOAK_TEST.md`
- `docs/CONTROL_PLANE_READINESS.md`
- `docs/PRODUCTIZATION_PILLARS.md`
- `docs/SECURITY.md`
- `docs/PRODUCTION_READINESS.md`
- `docs/TROUBLESHOOTING.md`

## License

Apache 2.0.
