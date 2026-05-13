# b2b_msp_ticket_router_sla_agent

Deterministic B2B MSP ticket routing and SLA breach risk module with safe handoff, plus a LARGESTACK smoke test.

## Project Structure

- `msp_ticket_router.py` - Core routing, SLA risk, and handoff logic
- `largestack_app.py` - LARGESTACK smoke test with map-reduce and PII guardrails
- `policies/routing_rules.json` - Routing policy rules
- `tests/test_msp_ticket_router.py` - Tests for ticket router
- `tests/test_largestack_features.py` - Tests for LARGESTACK features
- `README.md` - This file

## Requirements

- Python 3.8+
- `largestack` package (for LARGESTACK features)
- `pytest` and `pytest-asyncio` (for tests)

## Installation

```bash
pip install largestack pytest pytest-asyncio
```

## Running Tests

```bash
pytest tests/
```

## Usage

```python
from msp_ticket_router import route_ticket, sla_breach_risk, handoff_plan

ticket = {'customer_tier': 'platinum', 'severity': 'p1', 'system': 'payments', 'region': 'apac', 'age_minutes': 50}
route = route_ticket(ticket)
risk = sla_breach_risk(ticket, sla_minutes=60)
handoff = handoff_plan(ticket, route, risk)

print(route)   # {'queue': 'payments_p1', 'priority': 'urgent'}
print(risk)    # {'breach_risk': 'high', 'minutes_remaining': 10}
print(handoff) # {'notify_executed': False, 'approval_required': True, ...}
```

## LARGESTACK Smoke Test

```python
import asyncio
from largestack_app import run_largestack_smoke

result = asyncio.run(run_largestack_smoke())
print(result)
```

## Notes

- No real network calls or external notifications.
- All risky actions return `approval_required=True` and `executed=False`.
- LARGESTACK features use `TestModel` overrides to avoid real LLM calls.
