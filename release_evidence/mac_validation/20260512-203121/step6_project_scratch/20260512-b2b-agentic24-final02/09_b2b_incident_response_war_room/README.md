# B2B Incident Response War Room

A deterministic module for triaging incidents, generating response plans, and enforcing maker-checker approval for external notices.

## Files

- `incident_war_room.py` – Core logic: `triage_incident`, `response_plan`, `approval_gate`
- `largestack_app.py` – LARGESTACK integration with workflow_dag and rag_citations features
- `policies/severity_rules.json` – Severity classification thresholds
- `data/fixture_incidents.json` – Sample incident data for RAG
- `tests/test_incident_war_room.py` – Unit tests for core logic
- `tests/test_largestack_features.py` – Integration test for LARGESTACK features

## Run Tests

```bash
pip install pytest pytest-asyncio largestack
pytest tests/
```

## Usage

```python
from incident_war_room import triage_incident, response_plan, approval_gate

incident = {
    'data_exposed': True,
    'customers_affected': 1200,
    'service_down_minutes': 30,
    'source': 'prod alert'
}
triage = triage_incident(incident)
plan = response_plan(triage)
gate = approval_gate('customer_notice', triage)
```

## LARGESTACK Smoke Test

```python
import asyncio
from largestack_app import run_largestack_smoke

result = asyncio.run(run_largestack_smoke())
print(result)
```

No real API keys or network calls required. All LARGESTACK features use TestModel overrides.
