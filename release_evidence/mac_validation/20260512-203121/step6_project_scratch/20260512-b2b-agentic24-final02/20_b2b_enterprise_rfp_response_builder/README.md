# B2B Enterprise RFP Response Builder

A deterministic RFP response builder with citation-backed drafting, compliance gap analysis, and LARGESTACK agentic smoke test.

## Setup

```bash
pip install largestack
```

## Run Tests

```bash
pytest tests/
```

## Usage

```python
from rfp_response import ingest_qa, draft_response, compliance_gap

# Ingest a policy document
with open('policies/security.md') as f:
    content = f.read()
ingest_qa('security.md', content)

# Draft a response
resp = draft_response('Do you support audit logs and SSO?')
print(resp['answer'])
print(resp['citations'])

# Check compliance gaps
gap = compliance_gap(['SOC2', 'HIPAA'], available=['SOC2'])
print(gap['missing'])
```

## LARGESTACK Smoke Test

```bash
python -c "import asyncio; from largestack_app import run_largestack_smoke; print(asyncio.run(run_largestack_smoke()))"
```
