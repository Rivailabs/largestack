# B2B Partner Onboarding Approval

## Overview

This project implements a deterministic B2B partner onboarding approval module. It validates compliance attestations, region, revenue tier, support readiness, and conflicts. The approval packet is maker-checker gated.

## Files

- `partner_onboarding.py`: Core logic with `evaluate_partner` and `approval_packet` functions.
- `largestack_app.py`: LARGESTACK agentic smoke test exercising `rag_citations` and `observability_trace` features.
- `policies/compliance_rules.json`: Policy file defining allowed regions and revenue tiers.
- `data/partners_fixture.json`: Fixture data for testing.
- `tests/test_partner_onboarding.py`: Unit tests for partner onboarding logic.
- `tests/test_largestack_features.py`: Async test for LARGESTACK smoke test.

## How to Run

### Prerequisites

- Python 3.8+
- Install dependencies:
  ```bash
  pip install largestack pytest pytest-asyncio
  ```

### Run Tests

```bash
pytest tests/
```

### Run LARGESTACK Smoke Test Directly

```python
import asyncio
from largestack_app import run_largestack_smoke

result = asyncio.run(run_largestack_smoke())
print(result)
```

## Notes

- No network calls are made; all LARGESTACK agents use `TestModel` overrides.
- The project uses only Python standard library for business logic.
- No real API keys or secrets are included.
