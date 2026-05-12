# B2B Invoice Reconciliation Agent

A deterministic B2B invoice reconciliation agent that matches invoice lines against purchase orders and receipts, calculates variances, flags missing receipts and overbilling, and never releases payment without approval.

## Project Structure

- `invoice_reconciliation.py` - Core reconciliation logic
- `largestack_app.py` - LARGESTACK integration with typed decorator API and memory isolation
- `policies/reconciliation_policy.json` - Reconciliation policy rules
- `data/` - Sample data files (PO, invoice, receipts)
- `tests/` - Test files

## Running Tests

```bash
# Install dependencies
pip install pytest pytest-asyncio

# Run all tests
pytest tests/
```

## Usage

```python
from invoice_reconciliation import reconcile_invoice, payment_decision

po = {'po_id': 'PO1', 'lines': [{'sku': 'A', 'qty': 10, 'unit_price': 100}]}
invoice = {'invoice_id': 'I1', 'po_id': 'PO1', 'lines': [{'sku': 'A', 'qty': 12, 'unit_price': 100}]}
receipts = [{'sku': 'A', 'qty': 10}]

rec = reconcile_invoice(po, invoice, receipts)
print(rec['status'])  # 'mismatch'

decision = payment_decision(rec)
print(decision)  # {'approval_required': True, 'executed': False}
```

## LARGESTACK Features

- **Typed Decorator API**: Uses `@agent.tool`, `@agent.tool_plain`, and `@agent.output_validator` with typed dependencies.
- **Memory Isolation**: Separate memory buffers for different users/sessions to prevent cross-user data leaks.

## Notes

- No real network calls or external side effects.
- Payment decisions always require approval for mismatches.
- All tests use `TestModel` overrides to avoid real API calls.
