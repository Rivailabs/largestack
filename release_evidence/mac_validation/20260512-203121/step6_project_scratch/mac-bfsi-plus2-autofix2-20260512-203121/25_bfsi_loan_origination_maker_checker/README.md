# BFSI Loan Origination Maker-Checker

A loan origination system with maker-checker approval workflow.

## Features
- `assess_application(applicant)`: Validates applicant data and returns decision.
- `create_approval_plan(applicant, assessment)`: Creates approval plan requiring maker-checker for high amounts or manual review.
- LARGESTACK integration: workflow DAG, tool policy, guardrails PII.

## Testing
```bash
pytest tests/
```

## Policies
See `policies/credit_policy.md` for credit policy details.