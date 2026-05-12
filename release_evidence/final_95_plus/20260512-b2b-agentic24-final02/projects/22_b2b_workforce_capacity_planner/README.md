# B2B Workforce Capacity Planner

Deterministic module to compare demand hours to available capacity by role, flag overload, and recommend staffing without protected-class logic.

## Run Tests

```bash
python -m pytest tests/
```

## Usage

```python
from workforce_capacity import capacity_plan, hiring_recommendation

demand = [{'role':'support','hours':220},{'role':'engineering','hours':120}]
capacity = [{'role':'support','fte':1,'hours_per_fte':160},{'role':'engineering','fte':1,'hours_per_fte':160}]
plan = capacity_plan(demand, capacity)
print(plan)
rec = hiring_recommendation(plan)
print(rec)
```

## LARGESTACK Smoke Test

```bash
python -m pytest tests/test_largestack_features.py -v
```

## Files
- `workforce_capacity.py` - core logic
- `largestack_app.py` - LARGESTACK agentic smoke test
- `data/roles.json` - sample capacity data
- `policies/hiring_policy.txt` - hiring policy
- `tests/test_capacity.py` - unit tests for capacity planner
- `tests/test_largestack_features.py` - tests for LARGESTACK features
