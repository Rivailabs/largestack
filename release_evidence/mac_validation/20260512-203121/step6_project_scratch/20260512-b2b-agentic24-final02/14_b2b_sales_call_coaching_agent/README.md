# B2B Sales Call Coaching Agent

A deterministic B2B sales call coaching agent that scores transcripts on a 100-point rubric, flags risks, and generates coaching plans. Includes LARGESTACK integration with router and memory isolation features.

## Project Structure

```
b2b_sales_call_coaching_agent/
├── sales_call_coach.py          # Core scoring and coaching logic
├── largestack_app.py            # LARGESTACK integration (router, memory)
├── data/
│   └── sample_transcripts.json  # Sample transcripts for testing
├── policies/
│   └── scoring_policy.json      # Scoring policy configuration
├── tests/
│   ├── test_sales_call_coach.py # Tests for core logic
│   └── test_largestack_features.py # Tests for LARGESTACK features
└── README.md
```

## Installation

No external dependencies required for core logic. For LARGESTACK features, install:

```bash
pip install largestack
```

## Usage

### Core API

```python
from sales_call_coach import score_call, coaching_plan

transcript = "What are your needs? Next step: schedule a follow-up."
score = score_call(transcript)
plan = coaching_plan(score)
print(score['total_score'], score['risk_flags'])
print(plan['actions'])
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

## Scoring Rubric

- **Discovery** (20 points): Rep must ask/record discovery questions (e.g., "what are your needs", "pain point").
- **Objection Handling** (20 points): Rep must address objections (e.g., budget, timeline).
- **Pricing Risk** (20 points): Avoid risky pricing language (e.g., "guaranteed ROI").
- **Next Step Clarity** (20 points): Clear next step (e.g., "schedule follow-up") not negated.
- **Compliance Disclaimer** (20 points): Include compliance language (e.g., "disclaimer").

Total: 100 points. Each missing item subtracts 20.

## LARGESTACK Features

- **orchestrator_router**: Uses Orchestrator with router strategy to classify and route tasks.
- **memory_isolation**: Uses separate memory buffers for different users to prevent cross-user leaks.
