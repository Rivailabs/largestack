# Resume Builder

A small project that generates a data analyst resume in markdown format with metadata.

## Files

- `resume_builder.py` - Main module with `build_resume(profile)` function.
- `largestack_app.py` - Async function `run_largestack_smoke()` demonstrating LARGESTACK features.
- `data/sample_profile.json` - Sample profile for testing.
- `tests/test_resume_builder.py` - Tests for resume builder.
- `tests/test_largestack_features.py` - Tests for largestack smoke.

## Requirements

- Python 3.8+
- `largestack` package (install via `pip install largestack`)

## Run Tests

```bash
python -m pytest tests/
```

## Usage

```python
from resume_builder import build_resume

profile = {'name': 'Alice', 'role': 'data analyst'}
md, meta = build_resume(profile)
print(md)
print(meta)
```

## LARGESTACK Smoke

```python
import asyncio
from largestack_app import run_largestack_smoke

result = asyncio.run(run_largestack_smoke())
print(result)
```
