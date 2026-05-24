# Contributing to LARGESTACK

We welcome contributions! 

## Setup
```bash
# Public GitHub clone URL should be added after repository visibility is enabled.
cd largestack
pip install -e ".[dev]"
```

## Run tests
```bash
pytest tests/ -q
```

## Code style
- Ruff for linting + formatting
- mypy strict for type checking
- pytest for tests
- All public APIs must have docstrings

## PR checklist
- [ ] Tests pass
- [ ] No new mypy errors
- [ ] Docs updated for public API changes
- [ ] CHANGELOG.md updated
