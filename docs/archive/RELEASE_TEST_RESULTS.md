# LARGESTACK 1.0.0 — Final Local Test Results

## Environment

- Date: 2026-05-06
- Python used locally: 3.13.5
- Package version: 1.0.0

## Commands run

```bash
python3 -m compileall -q largestack tests scripts examples
python -c "import largestack; print(largestack.__version__)"
python -m pytest --collect-only -q tests
python -m pytest -q tests/unit/test_monitor_public.py tests/unit/test_provider_matrix_public.py tests/unit/test_orchestrator_durable_public.py tests/unit/test_public_orchestrator_facade.py tests/unit/test_workflow.py tests/unit/test_serve.py tests/unit/test_health.py tests/unit/test_session.py tests/unit/test_v130_ratelimit.py tests/unit/test_guardrails.py tests/unit/test_enhanced_guards.py tests/security --tb=short --disable-warnings
python scripts/smoke_test_e2e.py
python scripts/scenario_kyc_nbfc.py
python scripts/scenario_rag_legaltech.py
python scripts/scenario_breach_dpdp.py
python scripts/scenarios_100.py
python -m build --wheel --sdist
```

## Results

| Gate | Result |
|---|---:|
| Compile | PASS |
| Import | PASS |
| Public API import | PASS |
| Test collection | PASS — 2142 tests collected |
| Focused deterministic/security subset | PASS — 117 passed |
| Smoke E2E | PASS — 64/64 |
| KYC scenario | PASS |
| RAG scenario | PASS — 100% retrieval |
| DPDP breach scenario | PASS |
| 100-scenario suite | PASS — 100 pass, 0 fail |
| Wheel build | PASS |
| sdist build | PASS |

## Notes

- `openpyxl>=3.1` is now included as a core dependency because the bundled smoke test exercises XLSX document loading.
- Docker/cloud/vector DB gates were not executed because those require live infrastructure or credentials.
