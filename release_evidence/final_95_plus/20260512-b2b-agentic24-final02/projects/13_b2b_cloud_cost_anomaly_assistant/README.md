# B2B Cloud Cost Anomaly Assistant

A deterministic B2B cloud cost anomaly detection and remediation planning module.

## Features

- **detect_anomalies**: Detects spend spikes against baseline with service driver explanations.
- **remediation_plan**: Generates a remediation plan requiring approval before shutdown/resizing actions.
- **LARGESTACK integration**: Smoke test exercising agent_tool_cost and guardrails_pii features.

## Project Structure

```
b2b_cloud_cost_anomaly_assistant/
├── cloud_cost.py
├── largestack_app.py
├── policies/
│   └── cost_policy.yaml
├── data/
│   └── sample_usage.json
├── tests/
│   ├── test_cloud_cost.py
│   └── test_largestack_features.py
└── README.md
```

## Requirements

- Python 3.8+
- `largestack` package (for LARGESTACK features)

## Installation

```bash
pip install largestack
```

## Usage

### Cloud Cost Anomaly Detection

```python
from cloud_cost import detect_anomalies, remediation_plan

usage = [
    {'service': 'compute', 'daily_cost': 100, 'baseline': 40},
    {'service': 'storage', 'daily_cost': 20, 'baseline': 22}
]
anoms = detect_anomalies(usage, threshold=2.0)
print(anoms)

plan = remediation_plan(anoms)
print(plan)
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
# Run all tests
python -m pytest tests/

# Run specific test file
python -m pytest tests/test_cloud_cost.py
python -m pytest tests/test_largestack_features.py
```

## Notes

- No real API keys or network calls are used.
- All agent calls are overridden with TestModel to avoid side effects.
- Risky actions (shutdown/resizing) return `approval_required=True` and `executed=False`.
