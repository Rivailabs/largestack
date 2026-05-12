# B2B Product Feedback Intelligence

## Overview
This project clusters product feedback by themes, computes revenue impact (ARR) and sentiment, and produces evidence-backed roadmap signals. It also includes a LARGESTACK smoke test demonstrating rag_citations and tool_policy_approval features.

## Files
- `feedback_intelligence.py` - Core logic: `cluster_feedback()` and `roadmap_signals()`.
- `largestack_app.py` - LARGESTACK smoke test with async `run_largestack_smoke()`.
- `policies/tool_permissions.yaml` - Policy file for tool permissions.
- `data/feedback_fixture.json` - Sample feedback data.
- `tests/test_feedback_intelligence.py` - Tests for feedback intelligence.
- `tests/test_largestack_features.py` - Tests for LARGESTACK smoke.

## Run & Test

### Install dependencies
```bash
pip install largestack pytest
```

### Run tests
```bash
pytest tests/
```

### Run smoke test manually
```python
import asyncio
from largestack_app import run_largestack_smoke
result = asyncio.run(run_largestack_smoke())
print(result)
```

## Usage Example
```python
from feedback_intelligence import cluster_feedback, roadmap_signals
items = [{'text':'Need SSO for enterprise deal','arr':100000},{'text':'SSO setup is confusing','arr':50000},{'text':'Dark mode please','arr':1000}]
clusters = cluster_feedback(items)
print(clusters)
signals = roadmap_signals(clusters)
print(signals)
```
