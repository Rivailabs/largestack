# Background Verification Portal

A simple background verification portal with candidate submission, document verification, and case status tracking.

## Requirements

- Python 3.8+
- `largestack` library (for LARGESTACK features)
- `pytest` (for running tests)

## Installation

```bash
pip install largestack pytest
```

## Usage

### Basic BGV Portal

```python
from bgv_portal import submit_candidate, verify_document, case_status

c = submit_candidate('A', 'a@example.com', consent=True)
print(verify_document(c['id'], 'id_proof', 'valid'))
print(case_status(c['id']))
```

### LARGESTACK Smoke Test

```python
import asyncio
from largestack_app import run_largestack_smoke

result = asyncio.run(run_largestack_smoke())
print(result)
```

## Running Tests

```bash
pytest tests/
```

## Project Structure

- `bgv_portal.py` - Core BGV portal logic
- `largestack_app.py` - LARGESTACK smoke test with rag_citations and tool_policy_approval
- `data/policy_documents.txt` - Sample policy documents for RAG
- `policies/approval_policy.txt` - Sample approval policy
- `tests/test_bgv_portal.py` - Tests for BGV portal
- `tests/test_largestack_features.py` - Tests for LARGESTACK features
