# dpdp_breach_response_workflow

A Python project implementing a personal data breach response workflow.

## Files

- `dpdp_breach.py` – Contains `classify_incident`, `notification_plan`, and `containment_steps`.
- `largestack_app.py` – Async smoke test using LARGESTACK features (orchestrator_router, agent_tool_cost).
- `policies/breach_policy.txt` – Sample policy file.
- `tests/test_dpdp_breach.py` – Unit tests for breach response functions.
- `tests/test_largestack_features.py` – Tests for LARGESTACK smoke function.

## Requirements

- Python 3.9+
- `largestack` package (install via `pip install largestack`)
- `pytest` and `pytest-asyncio` for running tests

## Running Tests

```bash
pip install pytest pytest-asyncio
pytest tests/
```

## Usage

```python
from dpdp_breach import classify_incident, notification_plan, containment_steps

inc = 'customer personal data leaked'
print(classify_incident(inc))  # personal_data_breach
print(notification_plan(inc))
print(containment_steps(inc))
```
