# Expense Tracker

A Python project for tracking expenses with policy violation detection.

## Setup

No external dependencies required for core functionality. For largestack features, install:
```
pip install largestack
```

## Running Tests

```
python -m pytest tests/
```

## Usage

```python
from expense_tracker import add_expense, monthly_summary, flag_policy_violations

e = add_expense('2026-05-01', 'travel', 250, 'card')
print(monthly_summary('2026-05'))  # {'total': 250, 'count': 1}

violations = flag_policy_violations([add_expense('2026-05-02', 'gift', 600, 'cash')])
print(violations)  # [{'date': '2026-05-02', 'category': 'gift', 'amount': 600, 'payment_method': 'cash'}]
```

## Largestack Integration

Run the largestack smoke test:
```
python largestack_app.py
```
