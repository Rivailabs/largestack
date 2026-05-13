# b2b_qa_regression_planner_agent

Deterministic B2B QA regression planner that converts changed files and incidents into a test plan with risk matrix.

## Run

```bash
python -c "from qa_regression_planner import build_test_plan, risk_matrix; changes=['billing/payments.py','auth/sso.py']; incidents=[{'area':'billing','severity':'high'}]; plan=build_test_plan(changes, incidents); print(plan); matrix=risk_matrix(plan); print(matrix)"
```

## Test

```bash
pip install pytest
pytest tests/
```

## LARGESTACK Smoke

```bash
pip install largestack
python -c "import asyncio; from largestack_app import run_largestack_smoke; print(asyncio.run(run_largestack_smoke()))"
```
