# B2B Contract Obligation Tracker

A deterministic B2B contract obligation tracker that extracts obligations from text, checks due-soon items, and provides escalation plans. Includes a LARGESTACK integration with typed decorator API and observability trace features.

## Project Structure

- `obligation_tracker.py` - Core logic: `extract_obligations`, `due_soon`, `escalation_plan`
- `largestack_app.py` - LARGESTACK integration with `run_largestack_smoke()`
- `data/obligations_fixture.json` - Sample fixture data
- `policies/escalation_policy.json` - Escalation policy rules
- `tests/test_obligation_tracker.py` - Tests for core logic
- `tests/test_largestack_features.py` - Tests for LARGESTACK features

## Requirements

- Python 3.9+
- `largestack` package (install via `pip install largestack`)

## Running Tests

```bash
# Install dependencies
pip install largestack pytest

# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_obligation_tracker.py
pytest tests/test_largestack_features.py
```

## Usage

```python
from obligation_tracker import extract_obligations, due_soon, escalation_plan

text = 'Vendor must deliver SOC2 report by 2026-05-20. Customer must renew by 2026-06-01. Owner: security.'
items = extract_obligations(text)
soon = due_soon(items, today='2026-05-12', days=10)
esc = escalation_plan(soon)
print(esc)
```

## LARGESTACK Smoke Test

```python
import asyncio
from largestack_app import run_largestack_smoke

result = asyncio.run(run_largestack_smoke())
print(result)
```

## Notes

- No real API keys or network calls; all LARGESTACK features use TestModel overrides.
- Escalation logic assumes simple date parsing.
- No external side effects; all operations are deterministic.
