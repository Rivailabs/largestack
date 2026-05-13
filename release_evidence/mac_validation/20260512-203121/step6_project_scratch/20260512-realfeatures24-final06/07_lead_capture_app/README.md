# Lead Capture App

A simple lead capture application with email validation, consent checking, qualification logic, and CSV export.

## Requirements

- Python 3.8+
- No external dependencies (standard library only)
- For largestack features: `pip install largestack`

## Run Tests

```bash
pytest tests/
```

## Usage

```python
from lead_capture import capture_lead, qualify_lead, export_csv

lead = capture_lead('A', 'a@example.com', consent=True, company='Acme')
assert qualify_lead(lead)['qualified'] is True
assert 'a@example.com' in export_csv([lead])
```

## Largestack Smoke Test

```python
import asyncio
from largestack_app import run_largestack_smoke

result = asyncio.run(run_largestack_smoke())
print(result)
```
