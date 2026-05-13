# Fintech KYC NBFC Workflow

A simple KYC workflow for NBFCs with validation, risk scoring, and approval decision.

## Run

```bash
python -c "from kyc_nbfc import validate_kyc, risk_score, approval_decision; print(approval_decision({'name':'A','pan':'ABCDE1234F','aadhaar_last4':'1234','income':50000}))"
```

## Test

```bash
pip install pytest
pytest tests/
```

## LARGESTACK Smoke Test

```bash
pip install largestack
python -c "import asyncio; from largestack_app import run_largestack_smoke; print(asyncio.run(run_largestack_smoke()))"
```
