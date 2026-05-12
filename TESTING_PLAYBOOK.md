# LARGESTACK v0.14.0 — Complete Testing Playbook

**Last verified:** 2026-05-04
**Framework status:** 2280 unit tests, 64-check integration smoke, 3 scenario runs all passing

This is the playbook you follow **before every deploy**. Six layers, in order. Each layer catches different bugs.

---

## The 6 Test Layers

```
┌──────────────────────────────────────────────────────────┐
│  Layer 6: Production canary (real users, 5% traffic)     │
├──────────────────────────────────────────────────────────┤
│  Layer 5: Load test (RPS, latency, memory)               │
├──────────────────────────────────────────────────────────┤
│  Layer 4: Scenario tests (KYC, RAG, breach — REAL flows) │  ← scripts/scenario_*.py
├──────────────────────────────────────────────────────────┤
│  Layer 3: Smoke test (every subsystem, single run)       │  ← scripts/smoke_test_e2e.py
├──────────────────────────────────────────────────────────┤
│  Layer 2: Integration tests (cross-module)               │
├──────────────────────────────────────────────────────────┤
│  Layer 1: Unit tests (2280 of them)                      │  ← pytest tests/
└──────────────────────────────────────────────────────────┘
```

**You must pass each layer before promoting to the next.** No skipping.

---

## Layer 1 — Unit Tests (2280 tests, ~60 sec)

**What it catches:** Logic bugs, regressions, edge cases in individual modules.

**Run:**
```bash
cd largestack-agentic-ai-v0.14.0
python -m pytest tests/ -q --tb=no
```

**Pass criteria:** `2280 passed, 30 skipped, 0 failed`

**If failures:**
- One module bug — read the traceback, fix, re-run
- Many module failures — check that optional deps installed: `pip install -e .[all]`

**Tests organized by phase:**

| Test file | Tests | Phase |
|---|--:|---|
| `test_v140_studio_compare.py` | 10 | Phase 11 |
| `test_v140_pyodide_eval.py` | 8 | Phase 12 |
| `test_v140_pr_diff.py` | 15 | Phase 13 |
| `test_v140_alerts.py` | 13 | Phase 14 |
| `test_v140_semantic_chunking.py` | 14 | Phase 15 |
| `test_v140_dpdp_breach.py` | 17 | Phase 16 |
| `test_v140_e2b.py` | 14 | Phase 17 |
| `test_v140_typed_agent.py` | 17 | Phase 18 |
| `test_v140_subgraph.py` | 12 | Phase 19 |
| `test_v140_a2a_multimodal.py` | 15 | Phase 20 |
| `test_v140_langfuse.py` | 14 | Phase 21 |
| `test_v140_phoenix.py` | 15 | Phase 22 |
| (v0.13 carry-forward) | 142 | Phases 1-10 |
| (v0.12 carry-forward) | 1974 | Pre-v0.13 |
| **Total** | **2280** | |

**Coverage gaps to know about:**
- E2B sandbox: only mock-tested (real E2B costs $$)
- Postgres backend: only mock-tested (no real DB in CI)
- A2A signed cards (RS256): tested when `cryptography` installed

---

## Layer 2 — Integration Tests (cross-module)

**What it catches:** Bugs at module boundaries. "Memory module works, A2A works, but they don't compose."

**Run:**
```bash
python -m pytest tests/integration/ -q
```

**Critical integrations to verify:**

| Cross-module path | What's being tested |
|---|---|
| `LongTermMemoryManager` + `VectorMemoryStore` | Vector search uses correct backing |
| `Agent` + `LongTermMemoryManager` | Memory tools registered on agent |
| `A2AServer` + `Agent` | Agent exposed via A2A protocol |
| `StudioBuilder` + `LongTermMemoryManager` | `from_memory_manager()` works |
| `eval-block` CLI + `extensions_v130` | Similarity assertion routes correctly |
| `compliance-check` + agent.yaml | YAML schema honored |

**Pass criteria:** All cross-module tests pass.

**If you don't have integration tests yet:** Write at least 5 covering the paths above. Aim for 30-50 integration tests over time.

---

## Layer 3 — End-to-End Smoke Test (every subsystem, single run)

**What it catches:** "Did anything break across the whole framework?"

**Run:**
```bash
python scripts/smoke_test_e2e.py
```

**Pass criteria:** `64 passed (100.0%)`

**What it covers (16 subsystems):**

```
1.  Framework imports & version          → Import works
2.  Long-term memory (Letta-pattern)     → 3-tier add/search/get
3.  Multi-tenant isolation               → ⚠️ AUDITOR PROBE
4.  Vector backend                       → Semantic search ranking
5.  Self-editing memory tools            → 5 OpenAI-format tools
6.  A2A Protocol                         → Sign/verify/stream
7.  A2A multi-modal                      → Image/file/text parts
8.  Studio export + compare              → HTML output
9.  Eval framework + similarity          → PR diff + alerts
10. Document loaders                     → XLSX + semantic chunk
11. DPDP §8 breach                       → Detection + notification
12. LiteLLM + India residency            → China blocked
13. Per-tenant rate limits               → Isolation verified
14. compliance-check CLI                 → Pre-deploy validator
15. Generic typed Agent                  → mypy-strict ready
16. Sub-graph Workflow                   → Composition works
```

**Run time:** ~15 seconds.

**If it fails:** A subsystem is broken in isolation OR the integration broke. Fix before proceeding.

---

## Layer 4 — Scenario Tests (real production flows)

**What it catches:** "Does the actual business workflow end-to-end produce correct results at expected latency?"

### 4.1 — KYC Pipeline (NBFC use case)

```bash
python scripts/scenario_kyc_nbfc.py
```

**What it tests:**
- 51 KYC cases through full pipeline
- Parallel calls to PAN + Aadhaar + CIBIL
- Memory writes with DPDP markers
- Studio export
- compliance-check on agent.yaml
- Cross-tenant isolation probe

**Pass criteria:**
- 100% of cases complete (approved/rejected/manual_review)
- Per-case latency <200ms (with mocked aggregators)
- Tenant isolation verified
- agent.yaml passes all DPDP/RBI/PMLA checks

**Last verified output:**
```
Total cases:        51
Approved:           50
Rejected:           1
Wall clock:         4.18s
Per-case latency:   82.0ms avg
Throughput:         12 req/s
```

### 4.2 — RAG Pipeline (legal-tech use case)

```bash
python scripts/scenario_rag_legaltech.py
```

**What it tests:**
- Semantic chunking on 7 mixed documents
- Vector embedding indexing
- 5 realistic queries across compliance topics
- Tenant isolation in RAG
- Studio export

**Pass criteria:**
- ≥80% retrieval accuracy (right doc in top-3)
- Tenant isolation verified
- Studio export ≥5KB

**Last verified:** **100% retrieval accuracy** (5/5).

### 4.3 — Breach Detection (DPDP §8 use case)

```bash
python scripts/scenario_breach_dpdp.py
```

**What it tests:**
- Normal traffic baseline (no false positives)
- Mass-read detection (1500 records by single user)
- Cross-tenant attempt detection
- Unauthorized export detection
- DPB notification template generation
- Principal notification template (plain language)
- 72-hour deadline tracking

**Pass criteria:** All 7 phases complete; no false positives on baseline; correct severity classification.

---

## Layer 5 — Load Tests

**What it catches:** "Does the framework hold up at production scale?"

**You DON'T have load tests yet — write them with `locust` or `k6`:**

### 5.1 KYC Throughput
```python
# locustfile.py
from locust import HttpUser, task, between

class KYCUser(HttpUser):
    wait_time = between(0.1, 1.0)

    @task
    def kyc_submit(self):
        self.client.post("/agents/kyc/run", json={
            "pan": "AAACR1234C",
            "aadhaar_otp_token": "OTP-123",
        })
```

```bash
locust -f locustfile.py --headless -u 100 -r 10 -t 5m \
  --host http://localhost:8000
```

**Targets for production:**
- p50 latency: <100ms
- p99 latency: <500ms
- Throughput: ≥50 req/s per pod
- No memory leaks over 5 min sustained load
- No DB connection exhaustion

### 5.2 Memory Backend Stress
- Add 100K archival entries → search latency stays <50ms
- Per-tenant rate limiter: 1000 tenants × 100 RPS = 100K RPS aggregate

### 5.3 A2A Streaming
- 50 concurrent SSE streams sustained for 5 min — no leaks
- Stream cancel mid-task → resources cleaned up

---

## Layer 6 — Production Canary

**What it catches:** "Real users hit weird inputs we didn't think of."

**Process:**
1. Deploy new version to 5% of traffic (Kubernetes canary deployment)
2. Watch Phoenix dashboard (Phase 22) for drift
3. Watch Langfuse dashboard (Phase 21) for cost/latency anomalies
4. Eval CI runs every hour against the canary
5. If pass-rate drops >2% → auto-rollback
6. After 24 hours stable → promote to 50%
7. After 48 hours stable → promote to 100%

**Auto-rollback conditions:**
- Eval pass-rate drops >5%
- p99 latency rises >50%
- Error rate >1%
- Any DPDP §8 breach indicator fires

---

## Pre-Release Checklist

Before publishing to PyPI, run all six layers:

```bash
# Layer 1: Unit
python -m pytest tests/ -q --tb=no
# Expected: 2280 passed

# Layer 2: Integration (if you have them)
python -m pytest tests/integration/ -q

# Layer 3: Smoke
python scripts/smoke_test_e2e.py
# Expected: 64 passed (100%)

# Layer 4: Scenarios
python scripts/scenario_kyc_nbfc.py
python scripts/scenario_rag_legaltech.py
python scripts/scenario_breach_dpdp.py
# All three: ✅ VERIFIED PRODUCTION-READY

# Build
rm -rf dist/ build/ *.egg-info/
python -m build --wheel --sdist

# Verify in fresh venv
python -m venv /tmp/verify
/tmp/verify/bin/pip install dist/largestack_agentic_ai-0.14.0-py3-none-any.whl
/tmp/verify/bin/python -c "import largestack; print(largestack.__version__)"

# compliance-check the example
largestack compliance-check examples/agents/kyc.yaml --strict
# Expected: 0 errors, 0 warnings (strict mode)

# Honesty CI: changelog tests count == actual
bash scripts/check_changelog.sh
# Expected: CHANGELOG count OK: 2280

# THEN ship
twine upload dist/*  # PyPI
git tag v0.14.0
git push origin v0.14.0
```

---

## Failure Triage Decision Tree

```
Test failure?
├── Layer 1 fails?
│   ├── 1-3 tests → fix logic, re-run
│   ├── many tests → optional dep missing? → pip install -e .[all]
│   └── all tests → broken import path → check pyproject.toml
│
├── Layer 3 (smoke) fails?
│   └── Subsystem boundary issue → check the failing subsystem in isolation
│
├── Layer 4 (scenario) fails?
│   ├── KYC throughput drops → check rate limiter, memory backend
│   ├── RAG accuracy drops → tune embedder, chunking thresholds
│   └── Breach false positives → adjust BreachDetectorConfig thresholds
│
├── Layer 5 (load) fails?
│   ├── Latency rises → profile hot paths
│   ├── Memory leak → check connection pooling
│   └── Connection exhaust → tune asyncpg pool_max_size
│
└── Layer 6 (canary) fails?
    └── AUTO-ROLLBACK → investigate offline before retry
```

---

## Per-Subsystem Test Commands

When you change a specific subsystem, run JUST its tests:

| Change to | Test command |
|---|---|
| Memory module | `pytest tests/unit/test_v120_memory.py tests/unit/test_v130_postgres.py tests/unit/test_v130_vector.py tests/unit/test_v130_memory_tools.py -q` |
| A2A protocol | `pytest tests/unit/test_v120_a2a.py tests/unit/test_v130_a2a_v03.py tests/unit/test_v140_a2a_multimodal.py -q` |
| Eval framework | `pytest tests/unit/test_v120_cli.py tests/unit/test_v130_eval_extensions.py tests/unit/test_v140_pr_diff.py tests/unit/test_v140_alerts.py -q` |
| Studio | `pytest tests/unit/test_v120_studio.py tests/unit/test_v140_studio_compare.py tests/unit/test_v140_pyodide_eval.py -q` |
| Compliance | `pytest tests/unit/test_v130_compliance_check.py tests/unit/test_v140_dpdp_breach.py -q` |
| Loaders | `pytest tests/unit/test_v130_office_loaders.py tests/unit/test_v140_semantic_chunking.py -q` |
| Code-gen | `pytest tests/unit/test_v110_code_agent.py tests/unit/test_v140_e2b.py -q` |

---

## Honest Coverage Gaps

**Things LARGESTACK unit tests DON'T cover (and why):**

| Gap | Why | Mitigation |
|---|---|---|
| Real LLM calls | Cost + nondeterminism | Mock LiteLLM in unit; real LLM in scenario |
| Real Postgres | CI infrastructure cost | Mock asyncpg in unit; spin up Postgres in staging |
| Real E2B sandbox | $$ per test | Mock in unit; real run before each release |
| Real Aadhaar/PAN APIs | Production data risk | Mock signzy/idfy; sandbox test with Signzy test keys |
| Real Langfuse/Phoenix | External services | Mock SDK; real dashboard verified pre-release |
| Browser rendering of Studio HTML | No browser in CI | Visual smoke test on staging |
| Pyodide actual eval execution | Browser-only | Manual smoke test |
| Real Slack/Teams webhook delivery | Spam risk | Mock urllib; real delivery in staging only |

**These gaps are documented intentionally** — they require staging environment, not CI.

---

## When You're About to Ship

The shortest version of this playbook:

```
1. pytest tests/                       → 2280 passing
2. python scripts/smoke_test_e2e.py    → 64 passing
3. python scripts/scenario_kyc_nbfc.py
4. python scripts/scenario_rag_legaltech.py
5. python scripts/scenario_breach_dpdp.py
6. python -m build --wheel --sdist
7. Install wheel in fresh venv → import largestack → version OK
8. tag + push
```

If all 8 steps green → SHIP IT.

If any step fails → DON'T ship. Fix and restart from step 1.
