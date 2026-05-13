# BFSI AML Transaction Monitoring

A Python project for AML transaction monitoring with screening, SAR drafting, and policy Q&A.

## Features
- `screen_transaction`: Flags high-risk transactions based on sanctions, amount spikes, keywords, and KYC.
- `draft_sar`: Drafts a Suspicious Activity Report (never files externally).
- `policy_answer`: Answers policy questions using token-overlap retrieval.
- LARGESTACK integration: Demonstrates router, RAG citations, and observability.

## Usage
```python
from aml_monitoring import screen_transaction, draft_sar, policy_answer

# Example screening
txn = {'transaction_id': 'T1', 'amount': 10000, 'country': 'IR', 'counterparty_country': 'US'}
customer = {'customer_id': 'C1', 'average_monthly_volume': 1000}
watchlist = {'blocked_countries': ['IR'], 'high_risk_keywords': ['sanctions']}
result = screen_transaction(txn, customer, watchlist)
print(result)
```

## Testing
```bash
python -m pytest tests/
```

## LARGESTACK Smoke Test
```bash
python -m pytest tests/test_largestack_features.py -v
```
