# AI Security Gateway Website

A static website project demonstrating AI Security Gateway concepts.

## Run Instructions

1. Open `index.html` in a browser to view the site.
2. Run `python site_check.py` to verify required content.
3. Run tests with `python -m pytest tests/`.

## Test Instructions

```bash
pip install pytest
pytest tests/
```

## Largestack Features

Run `python -m pytest tests/test_largestack_features.py -v` to test largestack integration.

Note: No network calls are made; all agent calls use TestModel overrides.