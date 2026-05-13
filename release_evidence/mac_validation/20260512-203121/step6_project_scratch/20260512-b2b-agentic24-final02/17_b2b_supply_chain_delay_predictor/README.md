# B2B Supply Chain Delay Predictor

A deterministic B2B supply chain delay predictor with risk estimation and mitigation planning, plus a LARGESTACK integration demonstrating workflow DAG and tool policy approval features.

## Project Structure

- `supply_chain_delay.py` - Core module with `predict_delay()` and `mitigation_plan()` functions.
- `largestack_app.py` - LARGESTACK integration with `run_largestack_smoke()`.
- `policies/approval_policy.json` - Approval policy for high-risk actions.
- `data/shipment_fixtures.json` - Realistic shipment fixtures for testing.
- `tests/test_supply_chain_delay.py` - Tests for the core module.
- `tests/test_largestack_features.py` - Tests for LARGESTACK features.

## How to Run

1. Install dependencies:
   ```
   pip install largestack pytest pytest-asyncio
   ```

2. Run all tests:
   ```
   pytest tests/
   ```

3. Run specific test file:
   ```
   pytest tests/test_supply_chain_delay.py
   pytest tests/test_largestack_features.py
   ```

## Usage Example

```python
from supply_chain_delay import predict_delay, mitigation_plan

shipment = {
    'supplier_score': 55,
    'port_congestion': 'high',
    'inventory_days': 5,
    'demand_spike': True,
    'criticality': 'high'
}
risk = predict_delay(shipment)
print(risk)  # {'risk_level': 'high', 'delay_days_estimate': 7}

plan = mitigation_plan(shipment, risk)
print(plan)  # {'actions': [...], 'approval_required': True}
```

## LARGESTACK Features

- **workflow_dag**: Demonstrates a DAG workflow with two agents.
- **tool_policy_approval**: Demonstrates tool permissions with denied dangerous actions.

All LARGESTACK features use `TestModel` overrides to avoid network calls.
