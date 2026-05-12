# B2B Procurement Contract Triage

A deterministic module for extracting obligations, flagging risks, and determining approval routes from procurement contract text.

## Files
- `procurement_triage.py` – core logic
- `largestack_app.py` – async smoke test using LARGESTACK router and parallel team patterns
- `policies/approval_rules.yaml` – approval policy reference
- `data/sample_contract.txt` – sample contract text
- `tests/test_procurement_triage.py` – unit tests for triage logic
- `tests/test_largestack_features.py` – async test for LARGESTACK features

## Run Tests

```bash
pip install pytest pytest-asyncio
pytest tests/
```

## Usage

```python
from procurement_triage import extract_obligations, flag_contract_risks, approval_route

text = 'Agreement auto-renews annually. Payment terms Net 15. No liability cap is stated. DPA not attached. Governing law Mars.'
ob = extract_obligations(text)
risks = flag_contract_risks(text)
route = approval_route(risks)
print(ob, risks, route)
```

## LARGESTACK Smoke

```python
import asyncio
from largestack_app import run_largestack_smoke

result = asyncio.run(run_largestack_smoke())
print(result)
```
