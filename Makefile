.PHONY: dev test lint build clean dashboard doctor

dev:
	pip install -e ".[dev]"

test:
	pytest tests/ -v

lint:
	ruff check largestack/

format:
	ruff format largestack/

build:
	python -m build

clean:
	rm -rf dist/ build/ *.egg-info

dashboard:
	largestack dashboard

doctor:
	largestack doctor

docs:
	pip install -e ".[docs]"
	mkdocs serve

docs-build:
	pip install -e ".[docs]"
	mkdocs build -d site/
