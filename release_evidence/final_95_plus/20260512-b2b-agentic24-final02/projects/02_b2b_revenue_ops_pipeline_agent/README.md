# B2B Revenue Ops Pipeline Agent

A deterministic B2B lead processing module with LARGESTACK integration.

## Files
- `revops_pipeline.py` - Core logic: normalize_lead, route_account, build_sla_plan
- `largestack_app.py` - Async smoke test for LARGESTACK features
- `policies/routing_rules.json` - Routing policy rules
- `data/sample_leads.json` - Sample lead data
- `tests/test_revops_pipeline.py` - Unit tests for core logic
- `tests/test_largestack_features.py` - Tests for LARGESTACK smoke

## Run Tests
```bash
pip install largestack pytest
pytest tests/
```

## Usage
```python
from revops_pipeline import normalize_lead, route_account, build_sla_plan
lead = normalize_lead({'email':'Buyer@ACME.COM','company':'  Acme Inc. ','employees':1500,'source':'web','last_touch_days':5})
print(route_account(lead))
print(build_sla_plan(lead))
```

## LARGESTACK Smoke
```bash
python largestack_app.py
```
