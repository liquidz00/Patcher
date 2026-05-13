SHELL 			:= /bin/bash
UV 				:= uv
PYPROJECT 		:= pyproject.toml
VENV_DIR 		:= .venv

.PHONY: docs all clean test install pre-commit pre-commit-run pre-commit-update

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

venv:  ## Create virtual environment if missing
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo "Creating virtual environment..."; \
		$(UV) venv; \
	else \
		echo "Virtual environment already exists at $(VENV_DIR)"; \
	fi

install: venv  ## Install base dependencies (Patcher only)
	$(UV) sync

dev: venv  ## Install everything for monorepo development (Patcher + API + all extras)
	$(UV) sync --all-packages --all-extras

uninstall:  ## Remove the .venv directory
	rm -rf $(VENV_DIR)

clean:  ## Remove caches, build artifacts, and the .venv
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf .venv coverage/ dist/ build/ .coverage htmlcov/ docs/_build/

lint:  ## Check code style with ruff
	$(UV) run ruff format --check .
	$(UV) run ruff check .

format:  ## Auto-format code with ruff
	$(UV) run ruff format .
	$(UV) run ruff check . --fix

lock:  ## Update uv.lock
	$(UV) lock

upgrade:  ## Upgrade all dependencies to latest versions
	$(UV) lock --upgrade
	$(UV) sync --all-packages --all-extras

test:  ## Run Patcher unit tests (excludes integration)
	$(UV) run pytest tests/ -v -m "not integration"

test-integration:  ## Run Patcher integration tests only
	$(UV) run pytest tests/ -v -m integration

test-api:  ## Run Patcher API tests
	cd api && $(UV) run pytest

pre-commit:  ## Install pre-commit hooks
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo "Virtual environment not found. Creating and installing dev dependencies..."; \
		$(MAKE) dev; \
	fi
	$(UV) run pre-commit install

pre-commit-run:  ## Run pre-commit on all files
	$(UV) run pre-commit run --all-files

pre-commit-update:  ## Update pre-commit hooks to latest versions
	$(UV) run pre-commit autoupdate

build:  ## Build distribution packages (sdist + wheel)
	$(UV) build --sdist --wheel

docs:  ## Build Sphinx documentation
	$(UV) run sphinx-build -b html docs/ docs/_build/
