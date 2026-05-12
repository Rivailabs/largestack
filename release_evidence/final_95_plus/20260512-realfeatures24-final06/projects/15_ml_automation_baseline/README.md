# ml_automation_baseline

A minimal ML automation project that detects regression vs classification tasks and computes a baseline metric (MAE for regression, accuracy for classification). Includes a LARGESTACK integration with map-reduce and sequential team features, using TestModel overrides to avoid network calls.

## Run / Test Instructions

1. Install dependencies:
   - Python 3.8+
   - `largestack` package (for LARGESTACK features)
   - `pytest` for running tests

2. Run tests:
   ```bash
   pytest tests/
   ```

3. Run the LARGESTACK smoke test directly:
   ```bash
   python largestack_app.py
   ```

## Project Structure

- `ml_automation.py` - Core ML automation functions: `detect_task()` and `baseline()`.
- `largestack_app.py` - LARGESTACK integration with async smoke test.
- `data/sample_data.csv` - Sample data file.
- `policies/sample_policy.txt` - Sample policy file.
- `tests/test_ml_automation.py` - Tests for ml_automation.
- `tests/test_largestack_features.py` - Tests for LARGESTACK features.
