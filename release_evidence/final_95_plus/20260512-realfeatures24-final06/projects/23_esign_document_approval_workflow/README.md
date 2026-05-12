# eSign Document Approval Workflow

This project implements an offline e-sign document approval workflow with an audit trail.

## Files

- `esign_workflow.py`: Core module with functions `create_envelope`, `add_signer`, `send_decision`, `audit_trail`.
- `largestack_app.py`: Async function `run_largestack_smoke()` that exercises LARGESTACK typed decorator and observability trace features.
- `data/sample_policy.txt`: Sample policy file.
- `policies/approval_policy.json`: Approval policy configuration.
- `tests/test_esign_workflow.py`: Tests for the e-sign workflow.
- `tests/test_largestack_features.py`: Tests for the LARGESTACK smoke function.

## Requirements

- Python 3.8+
- `largestack` package (install via `pip install largestack`)

## Running Tests

```bash
# Install dependencies
pip install pytest

# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_esign_workflow.py
pytest tests/test_largestack_features.py
```

## Usage Example

```python
from esign_workflow import create_envelope, add_signer, send_decision, audit_trail

e = create_envelope('contract.pdf')
add_signer(e['id'], 'a@example.com')
result = send_decision(e['id'])
assert result['executed'] is False
audit = audit_trail(e['id'])
print(audit)
```

## Notes

- `send_decision` never actually sends the envelope; it returns `executed=False` and logs that approval is required.
- The LARGESTACK smoke test uses `TestModel` overrides to avoid any network calls.
