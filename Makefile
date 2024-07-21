SHELL := /bin/bash
.PHONY: docs

install:
	python3 -m pip install --upgrade --force-reinstall --editable '.[dev]'

uninstall:
	python3 -m pip uninstall -y -r <(python3 -m pip freeze)

restore:
	rm -rf build/ dist/ src/*.egg-info **/__pycache__ .coverage .pytest_cache/ .ruff_cache/

test:
	pytest tests

lint:
	black --check src tests
	ruff check src tests

build:
	python3 -m build --sdist --wheel

docs:
	sphinx-build -b html docs/ docs/_build/
