# B2B Field Service Dispatch Optimizer

A deterministic B2B field service dispatch optimizer that assigns technicians to jobs based on skill, region, priority, and available hours, avoiding overbooking and providing explanations for skipped jobs.

## Features

- **Skill matching**: Assigns technicians only to jobs matching their skills.
- **Region matching**: Ensures technicians are assigned to jobs in their region.
- **Priority handling**: High-priority jobs are assigned first.
- **Capacity management**: Avoids overbooking by respecting available hours.
- **Explanation**: Provides human-readable explanations for skipped jobs.
- **LARGESTACK integration**: Demonstrates team_parallel and tool_policy_approval features.

## Project Structure

```
b2b_field_service_dispatch_optimizer/
├── field_dispatch.py          # Core dispatch logic
├── largestack_app.py          # LARGESTACK integration
├── data/
│   ├── technicians.json       # Sample technician data
│   └── jobs.json              # Sample job data
├── policies/
│   └── dispatch_policy.json   # Dispatch policy configuration
├── tests/
│   ├── test_field_dispatch.py # Tests for dispatch logic
│   └── test_largestack_features.py # Tests for LARGESTACK features
└── README.md
```

## Installation

No external dependencies required. Uses Python standard library only.

## Running Tests

```bash
python -m pytest tests/
```

Or run individual test files:

```bash
python -m pytest tests/test_field_dispatch.py
python -m pytest tests/test_largestack_features.py
```

## Usage

```python
from field_dispatch import schedule_jobs, explain_assignment

techs = [
    {'id': 'T1', 'skills': ['hvac'], 'region': 'north', 'available_hours': 4},
    {'id': 'T2', 'skills': ['network'], 'region': 'south', 'available_hours': 2}
]
jobs = [
    {'id': 'J1', 'skill': 'hvac', 'region': 'north', 'duration_hours': 3, 'priority': 'high'},
    {'id': 'J2', 'skill': 'hvac', 'region': 'north', 'duration_hours': 3, 'priority': 'low'}
]
schedule = schedule_jobs(techs, jobs)
print(explain_assignment(schedule))
```

## LARGESTACK Features

Run the LARGESTACK smoke test:

```python
import asyncio
from largestack_app import run_largestack_smoke

result = asyncio.run(run_largestack_smoke())
print(result)
```
