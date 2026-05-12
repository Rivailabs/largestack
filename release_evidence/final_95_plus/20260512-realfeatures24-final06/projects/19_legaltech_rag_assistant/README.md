# LegalTech RAG Assistant

A simple legal RAG assistant that stores case notes and answers queries.

## Files

- `legal_rag.py` - Core module with `add_case_note` and `answer_legal_query`.
- `largestack_app.py` - Async smoke test for LARGESTACK features (team_parallel, memory_isolation).
- `data/sample_policy.md` - Sample policy file for testing.
- `tests/test_legal_rag.py` - Pytest tests for legal_rag.
- `tests/test_largestack_features.py` - Pytest tests for largestack_app.

## Requirements

- Python 3.8+
- `largestack` package (install via `pip install largestack`)

## Running Tests

```bash
pip install pytest
pytest tests/
```

## Usage

```python
from legal_rag import add_case_note, answer_legal_query

add_case_note('contract.md', 'Termination requires 30 days written notice.')
result = answer_legal_query('termination notice')
print(result['answer'])
print(result['citations'])
```

## LARGESTACK Smoke Test

```python
import asyncio
from largestack_app import run_largestack_smoke

result = asyncio.run(run_largestack_smoke())
print(result)
```
