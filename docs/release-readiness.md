# Release Readiness Gate

Run this gate before any public stable release.

```bash
python -m compileall -q largestack tests scripts examples
python -c "import largestack; print(largestack.__version__)"
python -m largestack._cli.main --help
pytest --collect-only -q tests
pytest -q tests/security tests/unit/test_sandbox.py tests/unit/test_workflow.py
python scripts/smoke_test_e2e.py
python scripts/scenario_kyc_nbfc.py
python scripts/scenario_rag_legaltech.py
python scripts/scenario_breach_dpdp.py
python scripts/scenarios_100.py
python -m build --wheel
bash scripts/build_production_wheel.sh
docker compose -f deploy/docker-compose.yml config
```

Release criteria:

- All commands above pass in a clean environment.
- Test-count claims in docs match `pytest --collect-only`.
- Provider support claims match `docs/provider-support.md`.
- Production deployment uses strong secrets and protected internal services.
- Any remaining limitations are documented in `docs/known-limitations.md`.
