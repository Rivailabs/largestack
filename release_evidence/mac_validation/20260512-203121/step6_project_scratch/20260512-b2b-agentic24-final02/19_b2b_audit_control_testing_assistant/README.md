# B2B Audit Control Testing Assistant

A deterministic B2B audit control testing assistant that samples transactions by risk, evaluates control evidence, and summarizes exceptions. Includes a LARGESTACK integration with team_parallel and memory_isolation features, using TestModel overrides to avoid network calls.

## Project Structure

- `audit_testing.py` - Core business logic: risk-based sampling and control evaluation.
- `largestack_app.py` - LARGESTACK integration with async smoke test.
- `policies/large_transactions_policy.json` - Policy file for large transaction approval.
- `data/sample_transactions.json` - Sample transaction data for testing.
- `tests/test_audit_testing.py` - Tests for audit testing logic.
- `tests/test_largestack_features.py` - Tests for LARGESTACK features.
- `README.md` - This file.

## How to Run

### Prerequisites
- Python 3.8+
- Install LARGESTACK: `pip install largestack`
- Install pytest and pytest-asyncio: `pip install pytest pytest-asyncio`

### Run Tests

```bash
pytest tests/
```

### Run LARGESTACK Smoke Test

```python
import asyncio
from largestack_app import run_largestack_smoke

result = asyncio.run(run_largestack_smoke())
print(result)
```

## Usage

```python
from audit_testing import sample_transactions, evaluate_control

txns = [
    {'id': '1', 'amount': 1000, 'approved': True},
    {'id': '2', 'amount': 90000, 'approved': False},
    {'id': '3', 'amount': 50000, 'approved': True}
]
sample = sample_transactions(txns, limit=2)
result = evaluate_control(sample, rule='large_transactions_require_approval')
print(result)
```

## Features

- **Deterministic Risk Sampling**: Samples transactions by risk score (amount and approval status).
- **Control Evaluation**: Checks transactions against configurable rules.
- **LARGESTACK Integration**: Uses Team with parallel strategy and memory isolation.
- **No Network Calls**: All LARGESTACK features use TestModel overrides.
