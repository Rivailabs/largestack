# hal_mosaic_ticket_domain_workflow

A Python project implementing MOSAIC ticket classification, routing, and SLA computation, plus a LARGESTACK smoke test with map-reduce and PII guardrails.

## Run Instructions

1. Install dependencies:
   ```bash
   pip install largestack pytest
   ```

2. Run the main module tests:
   ```bash
   pytest tests/test_hal_mosaic.py -v
   ```

3. Run the LARGESTACK smoke test:
   ```bash
   pytest tests/test_largestack_features.py -v
   ```

## Test Instructions

- All tests use Python standard library and largestack testing overrides.
- No network calls or external side effects.
- The public API is defined in `hal_mosaic.py`.
