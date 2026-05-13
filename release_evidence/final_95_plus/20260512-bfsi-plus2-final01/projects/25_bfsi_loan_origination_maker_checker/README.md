# BFSI Loan Origination Maker-Checker

A loan origination system with maker-checker approval workflow.

## Features
- `assess_application(applicant)`: Validates applicant data and returns decision.
- `create_approval_plan(applicant, assessment)`: Creates approval plan with maker-checker.
- `largestack_app.py`: Async smoke test for largestack features.

## Testing
```bash
pytest tests/
```

## Policy
See `policies/credit_policy.md` for credit policy details.
