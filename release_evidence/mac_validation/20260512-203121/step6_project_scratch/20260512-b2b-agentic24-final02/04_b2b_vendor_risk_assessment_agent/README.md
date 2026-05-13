# B2B Vendor Risk Assessment Agent

A deterministic B2B vendor risk assessment module with security, financial, privacy, country, and criticality scoring. Includes policy question answering with citation support, approval workflow, and a LARGESTACK integration demonstrating RAG citations and PII guardrails.

## Project Structure

- `vendor_risk.py` - Core risk assessment logic
- `largestack_app.py` - LARGESTACK integration with RAG and guardrails
- `policies/vendor_policy.md` - Sample policy document
- `data/vendor_fixture.json` - Sample vendor data
- `tests/test_vendor_risk.py` - Tests for vendor risk module
- `tests/test_largestack_features.py` - Tests for LARGESTACK features

## Running Tests

```bash
pip install largestack
pytest tests/
```

## Usage

```python
from vendor_risk import assess_vendor, approval_requirements, policy_answer

vendor = {'name':'DataCo','soc2':False,'dpdp_ready':False,'country':'US','criticality':'high','financial_score':45}
risk = assess_vendor(vendor)
print(risk)

approval = approval_requirements(risk)
print(approval)

docs = {'vendor_policy.md': 'High criticality vendors without SOC2 require security committee approval.'}
ans = policy_answer('when security committee approval vendor?', docs)
print(ans)
```

## LARGESTACK Smoke Test

```python
import asyncio
from largestack_app import run_largestack_smoke
result = asyncio.run(run_largestack_smoke())
print(result)
```
