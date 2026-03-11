.PHONY: test lint format install dev-install clean

test:
	PYTHONPATH=src python -m pytest tests/ -v --tb=short

lint:
	ruff check src/ tests/

format:
	ruff check --fix src/ tests/
	ruff format src/ tests/

install:
	pip install -e .

dev-install:
	pip install -e ".[dev,nmr]"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
