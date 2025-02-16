SHELL := /bin/bash
.PHONY: docs switcher

install:
	python3 -m pip install --upgrade --force-reinstall --editable '.[all]'

install-dev:
	python3 -m pip install --upgrade --force-reinstall --editable '.[dev]'

install-docs:
	python3 -m pip install --upgrade --force-reinstall --editable '.[docs]'

uninstall:
	python3 -m pip uninstall -y -r <(python3 -m pip freeze)

restore:
	rm -rf build/ dist/ src/*.egg-info **/__pycache__ .coverage .pytest_cache/ .ruff_cache/

clean:
	rm -rf docs/_build/*

test:
	pytest tests

lint:
	black --check src tests
	ruff check src tests

format:
	black src tests
	ruff check src tests --fix

build:
	python3 -m build --sdist --wheel

switcher:
	python3 docs/generate_switcher.py

docs: switcher
	sphinx-build -b html docs/ docs/_build/

