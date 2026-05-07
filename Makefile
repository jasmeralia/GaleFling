.PHONY: help install install-dev lint lint-fix format test test-cov test-functional test-functional-xvfb test-functional-cmd venv-win build installer clean

PYTHON ?= python
PIP ?= pip
WIN_PYTHON ?= py

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install runtime dependencies
	$(PIP) install -r requirements.txt

install-dev: ## Install all dependencies (runtime + dev)
	$(PIP) install -r requirements-dev.txt

lint: ## [Linux/WSL] Run ruff linter, formatter check, and mypy
	$(PYTHON) -m ruff check src/ tests/ infrastructure/ scripts/
	$(PYTHON) -m ruff format --check src/ tests/ infrastructure/ scripts/
	$(PYTHON) -m mypy src/ scripts/sync_release_version.py
	shellcheck infrastructure/deploy.sh scripts/commit_with_changelog_notes.sh

lint-fix: ## [Linux/WSL] Auto-fix lint issues and format code
	$(PYTHON) -m ruff check --fix src/ tests/ infrastructure/ scripts/
	$(PYTHON) -m ruff format src/ tests/ infrastructure/ scripts/

format: lint-fix ## [Linux/WSL] Alias for lint-fix

test: ## [Linux/WSL] Run test suite
	QT_QPA_PLATFORM=offscreen $(PYTHON) -m pytest tests/ -v

test-cov: ## [Linux/WSL] Run tests with coverage (excludes functional)
	QT_QPA_PLATFORM=offscreen $(PYTHON) -m pytest tests/ -v -m "not functional" --cov=src --cov-report=term-missing --cov-report=html --cov-report=xml:coverage.xml --junitxml=junit.xml -o junit_family=legacy

test-functional: ## [Linux/WSL] Run functional tests directly (WebView tests skipped without display)
	$(PYTHON) -m pytest tests/functional/ -m functional -v --no-header

test-functional-xvfb: ## [Linux/WSL] Run functional tests under Xvfb virtual display
	xvfb-run -a $(PYTHON) -m pytest tests/functional/ -m functional -v --no-header

POWERSHELL := /mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe

venv-win: ## [WSL→Win] Create Windows venv at .venv-win via PowerShell (run once first)
	@WIN_DIR=$$(wslpath -w "$(CURDIR)"); \
	printf "Set-Location '%s'; $(WIN_PYTHON) -m venv .venv-win; .venv-win\\\\Scripts\\\\pip install -r requirements-dev.txt\n" "$$WIN_DIR" | \
	$(POWERSHELL) -NoProfile -Command -

test-functional-cmd: ## [WSL→Win] Run functional tests via PowerShell (native GPU/display, use this in WSL)
	@WIN_DIR=$$(wslpath -w "$(CURDIR)"); \
	printf "Set-Location '%s'; .venv-win\\\\Scripts\\\\python.exe -m pytest tests\\\\functional -m functional -v --no-header\n" "$$WIN_DIR" | \
	$(POWERSHELL) -NoProfile -Command -

build: ## [Windows] Build standalone executable with PyInstaller
	pyinstaller build/build.spec --distpath dist/ --workpath build/tmp --clean

installer: build ## [Windows] Build exe + NSIS installer
	makensis build/installer.nsi

build-wsl: ## [WSL→Win] Build standalone executable via PowerShell dispatch to .venv-win
	@WIN_DIR=$$(wslpath -w "$(CURDIR)"); \
	printf "Set-Location '%s'; .venv-win\\\\Scripts\\\\python.exe -m PyInstaller build/build.spec --distpath dist/ --workpath build/tmp --clean\n" "$$WIN_DIR" | \
	$(POWERSHELL) -NoProfile -Command -

installer-wsl: build-wsl ## [WSL→Win] Build exe + NSIS installer via PowerShell (use this in WSL)
	@WIN_DIR=$$(wslpath -w "$(CURDIR)"); \
	printf "Set-Location '%s'; & 'C:\\\\Program Files (x86)\\\\NSIS\\\\makensis.exe' build\\\\installer.nsi\n" "$$WIN_DIR" | \
	$(POWERSHELL) -NoProfile -Command -

run: ## [Linux/WSL] Run the application
	$(PYTHON) src/main.py

clean: ## Remove build artifacts
	rm -rf dist/ build/tmp/ htmlcov/ .pytest_cache/ .ruff_cache/ 2>/dev/null || true
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true
