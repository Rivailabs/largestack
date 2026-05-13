# BFSI AML Transaction Monitoring

A lightweight AML transaction monitoring system for BFSI.

## Features
- **screen_transaction**: Flags high-risk transactions based on sanctions, amount spikes, keywords, and KYC.
- **draft_sar**: Drafts a Suspicious Activity Report (never files externally).
- **policy_answer**: Answers policy questions using token-overlap retrieval.
- **largestack smoke test**: Exercises orchestrator_router, rag_citations, and observability_trace.

## Usage

```python
from aml_monitoring import screen_transaction, draft_sar, policy_answer

# Example
txn = {'amount': 50000, 'currency': 'USD', 'counterparty_country': 'IR', 'date': '2025-03-01'}
customer = {'avg_monthly_volume': 5000, 'kyc_risk': 'low'}
watchlist = [{'entity': 'Iran', 'type': 'sanctions_country'}]

result = screen_transaction(txn, customer, watchlist)
print(result)
```

## Testing

```bash
pytest tests/
```

## Largestack Smoke

```bash
python -c "import asyncio; from largestack_app import run_largestack_smoke; print(asyncio.run(run_largestack_smoke()))"
```
