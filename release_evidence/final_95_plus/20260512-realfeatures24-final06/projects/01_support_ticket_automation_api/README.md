# Support Ticket Automation API

A simple support ticket automation system that categorizes requests and determines approval requirements.

## Files
- `support_ticket.py` - Core module with `handle_ticket(text)` function.
- `largestack_app.py` - LARGESTACK integration demonstrating agent tool cost and policy approval features.
- `policies/approval_policy.txt` - Sample approval policy file.
- `tests/test_support_ticket.py` - Tests for support_ticket module.
- `tests/test_largestack_features.py` - Tests for LARGESTACK integration.

## Requirements
- Python 3.8+
- `largestack` package (for LARGESTACK features)
- `pytest` (for running tests)

## Running Tests
```bash
pytest tests/
```

## Usage
```python
from support_ticket import handle_ticket

result = handle_ticket('duplicate payment refund')
print(result)
# {'category': 'refund', 'approval_required': True, 'response': 'Approval required for refund request.'}

result = handle_ticket('login reset')
print(result)
# {'category': 'login_reset', 'approval_required': False, 'response': 'Identity verification required. Please verify your identity to reset login.'}
```

## LARGESTACK Integration
Run `largestack_app.py` to execute the LARGESTACK smoke test:
```bash
python largestack_app.py
```
