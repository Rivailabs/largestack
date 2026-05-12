# B2B Renewal Churn Forecaster

A deterministic B2B renewal churn forecaster that assesses account risk based on usage decline, open tickets, champion loss, renewal proximity, and contract value. It generates a risk score and a playbook of mitigation actions.

## Project Structure

- `renewal_risk.py` - Core business logic: `assess_renewal_risk()` and `save_playbook()`
- `largestack_app.py` - LARGESTACK integration with map-reduce orchestrator and sequential team smoke test
- `policies/risk_thresholds.json` - Risk scoring thresholds and weights
- `tests/test_renewal_risk.py` - Unit tests for renewal risk module
- `tests/test_largestack_features.py` - Tests for LARGESTACK smoke function

## Requirements

- Python 3.8+
- `largestack` package (install via `pip install largestack`)

## Running Tests

```bash
# Install dependencies
pip install pytest

# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_renewal_risk.py
pytest tests/test_largestack_features.py
```

## Usage Example

```python
from renewal_risk import assess_renewal_risk, save_playbook

acct = {
    'usage_trend': -45,
    'open_tickets': 8,
    'champion_left': True,
    'renewal_days': 30,
    'arr': 250000
}
risk = assess_renewal_risk(acct)
print(risk)  # {'score': 85.0, 'risk_level': 'high'}

playbook = save_playbook(acct, risk)
print(playbook)
# {'actions': [...], 'approval_required': True, 'executed': False}
```

## LARGESTACK Smoke Test

Run the LARGESTACK integration smoke test:

```python
import asyncio
from largestack_app import run_largestack_smoke

result = asyncio.run(run_largestack_smoke())
print(result)
```

## Notes

- No external network calls are made; all LARGESTACK agents are overridden with `TestModel`.
- Business logic uses only Python standard library.
- Risky actions return `approval_required=True` and `executed=False`.
