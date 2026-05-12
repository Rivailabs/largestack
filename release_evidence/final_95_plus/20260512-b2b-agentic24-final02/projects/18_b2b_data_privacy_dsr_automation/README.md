# B2B Data Privacy DSR Automation

A deterministic B2B data privacy module for automating Data Subject Requests (DSR).

## Features
- Classify DSR requests (access, export, delete)
- Fulfillment planning with identity verification and approval for deletion
- PII redaction in logs
- LARGESTACK integration with typed decorator API and guardrails PII redaction

## Run

```bash
python dsr_automation.py
```

## Test

```bash
pytest tests/
```

## Files
- `dsr_automation.py` - Core business logic
- `largestack_app.py` - Async smoke test with LARGESTACK features
- `policies/privacy_policy.yaml` - Privacy policy file
- `data/sample_request.json` - Sample DSR request fixture
- `tests/test_dsr_automation.py` - Unit tests for core logic
- `tests/test_largestack_features.py` - Tests for LARGESTACK integration
