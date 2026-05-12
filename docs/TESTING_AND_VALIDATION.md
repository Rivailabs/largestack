# Testing And Validation

## Full Test Suite

```bash
python -m pytest tests -q --tb=short --disable-warnings -ra --timeout=180 --timeout-method=thread --durations=30
```

Expected release gate: `0 failed`, no timeout. Skips must be provider/env gated with clear reasons.

## Live DeepSeek

```bash
export LARGESTACK_DEEPSEEK_API_KEY=<deepseek-api-key>
python -m pytest tests/integration/test_deepseek_integration.py tests/integration/test_deepseek_automation.py tests/integration/test_agent_e2e.py -q -ra --timeout=180 --timeout-method=thread
```

## Examples

```bash
python examples/00_offline_test_model.py
python examples/rag_basic/rag_basic.py
for f in examples/01_hello/main.py examples/02_tools/main.py examples/03_team/main.py examples/04_guards/main.py examples/05_rag_knowledge/main.py examples/10_full_app/main.py; do timeout 120s python "$f"; done
```

## Smoke And Scenarios

```bash
python scripts/smoke_test_e2e.py
python scripts/scenario_kyc_nbfc.py
python scripts/scenario_rag_legaltech.py
python scripts/scenario_breach_dpdp.py
```

## Security

```bash
bandit -r largestack -x tests
bandit -r largestack -x tests --severity-level medium
pip-audit
gitleaks detect --source . --no-git
```

## Package

```bash
rm -rf dist build *.egg-info
python -m build
twine check dist/*
```

## One Command

```bash
scripts/final_release_validate.sh
```

Logs are written under `/tmp/largestack-final-validate-<timestamp>`.
