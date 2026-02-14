.PHONY: help install install-dev lint lint-fix format test test-cov build installer clean

PYTHON ?= python
PIP ?= pip

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install runtime dependencies
	$(PIP) install -r requirements.txt

install-dev: install ## Install runtime + dev dependencies
	$(PIP) install -r requirements-dev.txt

lint: ## Run ruff linter and formatter check
	ruff check src/ tests/ infrastructure/
	ruff format --check src/ tests/ infrastructure/
	shellcheck infrastructure/deploy.sh scripts/commit_with_changelog_notes.sh

lint-fix: ## Auto-fix lint issues and format code
	ruff check --fix src/ tests/ infrastructure/
	ruff format src/ tests/ infrastructure/

format: lint-fix ## Alias for lint-fix

test: ## Run test suite
	$(PYTHON) -m pytest tests/ -v

test-cov: ## Run tests with coverage report
	$(PYTHON) -m pytest tests/ -v --cov=src --cov-report=term-missing --cov-report=html

build: ## Build standalone executable with PyInstaller
	pyinstaller build/build.spec --distpath dist/ --workpath build/tmp --clean

installer: build ## Build NSIS installer (requires makensis)
	makensis build/installer.nsi

run: ## Run the application
	$(PYTHON) src/main.py

clean: ## Remove build artifacts
	rm -rf dist/ build/tmp/ htmlcov/ .pytest_cache/ .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true
