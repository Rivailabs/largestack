# B2B Sales Forecast Copilot

A deterministic B2B sales forecast copilot that stores opportunities in memory, computes weighted pipeline, commit pipeline, and coverage ratio against a target, and returns concrete risks when coverage is below 3x target.

## Features
- Add opportunities with amount, stage, probability, close quarter, and owner.
- Forecast weighted pipeline and commit pipeline for a given quarter.
- Explain pipeline risks when coverage ratio is below 3x target.
- LARGESTACK integration with agent_tool_cost and tool_policy_approval features.

## Setup

No external dependencies required. Uses Python standard library only.

## Run Tests

```bash
python -m pytest tests/ -v
```

## Usage

```python
from sales_forecast import add_opportunity, forecast_quarter, explain_pipeline_risk

add_opportunity('O1', amount=100000, stage='proposal', probability=0.5, close_quarter='2026Q2', owner='A')
add_opportunity('O2', amount=50000, stage='commit', probability=0.9, close_quarter='2026Q2', owner='A')

forecast = forecast_quarter('2026Q2', target=100000)
print(forecast)

risk = explain_pipeline_risk(forecast)
print(risk)
```

## LARGESTACK Smoke Test

```bash
python -c "import asyncio; from largestack_app import run_largestack_smoke; print(asyncio.run(run_largestack_smoke()))"
```

## Project Structure

```
b2b_sales_forecast_copilot/
├── sales_forecast.py
├── largestack_app.py
├── data/
│   └── opportunities.csv
├── policies/
│   └── approval_policy.txt
├── tests/
│   ├── test_sales_forecast.py
│   └── test_largestack_features.py
└── README.md
```
