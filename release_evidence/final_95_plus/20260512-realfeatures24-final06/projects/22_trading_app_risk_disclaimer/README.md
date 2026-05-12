# Trading App Risk Disclaimer

A small project demonstrating trading risk disclaimer, signal evaluation, and order decision logic.

## Files
- `trading_risk.py`: Core module with `evaluate_signal`, `risk_disclaimer`, and `place_order_decision`.
- `largestack_app.py`: LARGESTACK integration with workflow_dag and team_sequential features.
- `data/sample_policy.txt`: Sample policy file.
- `policies/disclaimer_policy.txt`: Disclaimer policy file.
- `tests/test_trading_risk.py`: Tests for trading_risk module.
- `tests/test_largestack_features.py`: Tests for LARGESTACK integration.

## Run Tests
```bash
pip install pytest
pytest tests/
```

## Run LARGESTACK Smoke
```bash
python largestack_app.py
```

## Requirements
- Python 3.8+
- `largestack` package (for LARGESTACK features)
