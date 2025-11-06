SHELL 			:= /bin/bash
UV 				:= uv
PYPROJECT 		:= pyproject.toml
VENV_DIR 		:= .venv

.PHONY: all clean test install pre-commit pre-commit-run pre-commit-update

# Export Python path for script resolution
export PYTHONPATH := $(shell pwd)

help:
	@echo "Available commands:"
	@echo ""
	@echo "  Installation & Setup:"
	@echo "    make venv             - Create virtual environment"
	@echo "    make install          - Install base dependencies"
	@echo "    make install-dev      - Install dev dependencies (includes docs)"
	@echo "    make uninstall        - Remove virtual environment"
	@echo "    make sync             - Alias for 'make install'"
	@echo ""
	@echo "  Development:"
	@echo "    make lint             - Check code style with ruff"
	@echo "    make format           - Auto-format code with ruff"
	@echo "    make pre-commit       - Install pre-commit hooks"
	@echo "    make pre-commit-run   - Run pre-commit on all files"
	@echo "    make pre-commit-update - Update pre-commit hooks to latest versions"
	@echo ""
	@echo "  Testing:"
	@echo "    make test             - Run all tests (verbose)"
	@echo "    make test-quick       - Run all tests (quiet mode)"
	@echo "    make test-cov         - Run tests with coverage report"
	@echo "    make test-cov-html    - Generate HTML coverage report"
	@echo ""
	@echo "  Building & Documentation:"
	@echo "    make build            - Build distribution packages (wheel & sdist)"
	@echo "    make docs             - Build Sphinx documentation"
	@echo ""
	@echo "  Dependency Management:"
	@echo "    make lock             - Update uv.lock file"
	@echo "    make upgrade          - Upgrade all dependencies to latest versions"
	@echo ""
	@echo "  Cleanup:"
	@echo "    make clean            - Remove build artifacts and cache files"
	@echo "    make flush            - Deep clean (remove all generated files)"
	@echo "    make restore          - Full cleanup (clean + flush)"

venv:
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo "Creating virtual environment..."; \
		$(UV) venv; \
	else \
		echo "Virtual environment already exists at $(VENV_DIR)"; \
	fi

install: venv
	$(UV) sync

install-dev: venv
	$(UV) sync --extra dev

uninstall:
	rm -rf $(VENV_DIR)

restore: clean flush
	@echo "Full cleanup completed"

sync: install

clean:
	rm -rf docs/_build/*
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -delete

flush:
	rm -rf build/ dist/ src/*.egg-info **/__pycache__ .coverage .pytest_cache/ .ruff_cache/ htmlcov/

lint:
	$(UV) run ruff format --check .
	$(UV) run ruff check .

format:
	$(UV) run ruff format .
	$(UV) run ruff check . --fix

lock:
	$(UV) lock

upgrade:
	$(UV) lock --upgrade
	$(UV) sync --extra dev

test:
	@echo "Running unit tests..."
	$(UV) run pytest tests/ -v

test-quick:
	@echo "Running unit tests (quiet mode)..."
	$(UV) run pytest tests/ -q

test-cov:
	@echo "Running unit tests with coverage..."
	$(UV) run pytest tests/ --cov=bin --cov-report=term-missing

test-cov-html:
	@echo "Generating HTML coverage report..."
	$(UV) run pytest tests/ --cov=bin --cov-report=html
	@echo "Coverage report generated in htmlcov/index.html"

pre-commit:
	@echo "Installing pre-commit hooks..."
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo "Virtual environment not found. Creating and installing dev dependencies..."; \
		$(MAKE) install-dev; \
	fi
	$(UV) run pre-commit install
	@echo "Pre-commit hooks installed successfully!"

pre-commit-run:
	@echo "Running pre-commit on all files..."
	$(UV) run pre-commit run --all-files

pre-commit-update:
	@echo "Updating pre-commit hooks to latest versions..."
	$(UV) run pre-commit autoupdate

build:
	$(UV) build --sdist --wheel

docs: install-dev
	$(UV) run sphinx-build -b html docs/ docs/_build/
