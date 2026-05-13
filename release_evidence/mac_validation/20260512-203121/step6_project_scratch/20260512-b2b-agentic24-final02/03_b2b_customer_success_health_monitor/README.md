# B2B Customer Success Health Monitor

A deterministic B2B customer health scoring module that computes a 0-100 health score based on usage, support tickets, NPS, renewal days, and executive sponsor presence. Includes a playbook generator with owner actions referencing signal names.

## Features

- **compute_health_score(account)**: Returns dict with `score`, `risk_level`, and `details`.
- **generate_playbook(account, health)**: Returns dict with `owner_actions` list and `approval_required` bool.
- **LARGESTACK integration**: Workflow DAG and observability trace features using TestModel overrides.

## Setup

No external dependencies required. Uses Python standard library only for product logic.

## Running Tests

```bash
python -m pytest tests/ -v
```

## Usage Example

```python
from customer_health import compute_health_score, generate_playbook

account = {
    'usage_percent': 35,
    'open_p1_tickets': 2,
    'nps': 4,
    'renewal_days': 45,
    'executive_sponsor': False
}
health = compute_health_score(account)
print(health)
plan = generate_playbook(account, health)
print(plan)
```

## Project Structure

- `customer_health.py` - Core scoring and playbook logic
- `largestack_app.py` - LARGESTACK integration with workflow and observability
- `policies/health_policy.json` - Scoring policy configuration
- `data/sample_accounts.json` - Sample account data for testing
- `tests/test_customer_health.py` - Tests for customer health module
- `tests/test_largestack_features.py` - Tests for LARGESTACK features
