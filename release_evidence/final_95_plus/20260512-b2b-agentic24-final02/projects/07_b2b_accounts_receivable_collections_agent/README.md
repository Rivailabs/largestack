# B2B Accounts Receivable Collections Agent

A deterministic business logic module for prioritizing overdue invoices and drafting collection plans.

## Files

- `ar_collections.py` - Core logic: `prioritize_accounts()` and `draft_collection_plan()`.
- `largestack_app.py` - LARGESTACK smoke test with map-reduce and agent tool cost features.
- `policies/collection_policy.txt` - Sample collection policy.
- `tests/test_ar_collections.py` - Unit tests for business logic.
- `tests/test_largestack_features.py` - Test for LARGESTACK smoke.

## How to Run

```bash
# Install dependencies (largestack required for smoke test)
pip install largestack

# Run all tests
python -m pytest tests/

# Run specific test
python -m pytest tests/test_ar_collections.py -v
```

## Usage

```python
from ar_collections import prioritize_accounts, draft_collection_plan

accounts = [
    {'account': 'A', 'amount_due': 50000, 'days_past_due': 45, 'tier': 'strategic', 'disputed': False},
    {'account': 'B', 'amount_due': 5000, 'days_past_due': 5, 'tier': 'standard', 'disputed': False}
]
ranked = prioritize_accounts(accounts)
plan = draft_collection_plan(ranked[0])
print(plan)
```

## Notes

- No real messages are sent; `send_executed` is always `False`.
- All risky actions require approval (`approval_required` is `True`).
- LARGESTACK smoke test uses `TestModel` overrides to avoid network calls.
