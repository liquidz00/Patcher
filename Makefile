SHELL := /bin/bash

install:
	python3 -m pip install --upgrade --force-reinstall --editable '.[dev]'

uninstall:
	python3 -m pip uninstall -y -r <(python3 -m pip freeze)

lint:
	black --check src tests
	ruff check src tests
