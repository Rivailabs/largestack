# Contributing to LARGESTACK

We welcome contributions! 

## Setup
```bash
git clone https://github.com/rivailabs/largestack-agentic-ai
cd largestack-agentic-ai
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
