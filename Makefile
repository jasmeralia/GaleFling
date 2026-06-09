VENV     := .venv

ifeq ($(OS),Windows_NT)
PYTHON   := python
VENV_BIN := $(VENV)/Scripts
PY       := $(VENV_BIN)/python.exe
else
PYTHON   := python3
VENV_BIN := $(VENV)/bin
PY       := $(VENV_BIN)/python
endif

PIP          := $(PY) -m pip
VERSION_FILE := src/utils/_version.py
POWERSHELL   := /mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe
WIN_PYTHON   ?= py

.PHONY: help venv deps version-file lint lint-fix format test test-cov \
        test-functional test-functional-xvfb test-functional-cmd \
        venv-win build-wsl installer-wsl run clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

venv: ## Create virtualenv at .venv
	@command -v $(PYTHON) >/dev/null 2>&1 || \
		{ echo "ERROR: $(PYTHON) not found. Install Python 3.11+."; exit 1; }
	$(PYTHON) -m venv $(VENV)
	@echo "Virtualenv created at $(VENV). Run 'make deps' next."

version-file: $(VERSION_FILE)  ## Generate src/utils/_version.py (dev version from git describe)

$(VERSION_FILE):
	$(PYTHON) scripts/write_version.py --root .

deps: venv version-file  ## Install all dependencies into .venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	$(PIP) install -r requirements-dev.txt

lint: ## Run ruff, mypy, and shellcheck
	$(PY) -m ruff check src/ tests/ infrastructure/ scripts/
	$(PY) -m ruff format --check src/ tests/ infrastructure/ scripts/
	$(PY) -m mypy src/ scripts/release_info.py scripts/write_version.py
	shellcheck infrastructure/deploy.sh

lint-fix: ## Auto-fix lint issues and format code
	$(PY) -m ruff check --fix src/ tests/ infrastructure/ scripts/
	$(PY) -m ruff format src/ tests/ infrastructure/ scripts/

format: lint-fix  ## Alias for lint-fix

test: ## Run test suite (excludes functional)
	QT_QPA_PLATFORM=offscreen $(PY) -m pytest tests/ -v -m "not functional"

test-cov: ## Run tests with coverage (excludes functional)
	QT_QPA_PLATFORM=offscreen $(PY) -m pytest tests/ -v -m "not functional" \
		--cov=src \
		--cov-report=term-missing \
		--cov-report=html \
		--cov-report=xml:coverage.xml \
		--junitxml=junit.xml \
		-o junit_family=legacy

test-functional: ## [Linux/WSL] Run functional tests directly (WebView tests skipped without display)
	$(PY) -m pytest tests/functional/ -m functional -v --no-header

test-functional-xvfb: ## [Linux/WSL] Run functional tests under Xvfb virtual display
	xvfb-run -a $(PY) -m pytest tests/functional/ -m functional -v --no-header

venv-win: ## [WSL→Win] Create Windows venv at .venv-win via PowerShell (run once first)
	@WIN_DIR=$$(wslpath -w "$(CURDIR)"); \
	printf "Set-Location '%s'; $(WIN_PYTHON) -m venv .venv-win; .venv-win\\\\Scripts\\\\pip install -r requirements-dev.txt\n" "$$WIN_DIR" | \
	$(POWERSHELL) -NoProfile -Command -

test-functional-cmd: ## [WSL→Win] Run functional tests via PowerShell (native GPU/display, use this in WSL)
	@WIN_DIR=$$(wslpath -w "$(CURDIR)"); \
	printf "Set-Location '%s'; .venv-win\\\\Scripts\\\\python.exe -m pytest tests\\\\functional -m functional -v --no-header\n" "$$WIN_DIR" | \
	$(POWERSHELL) -NoProfile -Command -

build-wsl: ## [WSL→Win] Build standalone executable via PowerShell dispatch to .venv-win
	@WIN_DIR=$$(wslpath -w "$(CURDIR)"); \
	printf "Set-Location '%s'; .venv-win\\\\Scripts\\\\python.exe -m PyInstaller build/build.spec --distpath dist/ --workpath build/tmp --clean\n" "$$WIN_DIR" | \
	$(POWERSHELL) -NoProfile -Command -

installer-wsl: build-wsl  ## [WSL→Win] Build exe + NSIS installer via PowerShell (use this in WSL)
	@WIN_DIR=$$(wslpath -w "$(CURDIR)"); \
	printf "Set-Location '%s'; & 'C:\\\\Program Files (x86)\\\\NSIS\\\\makensis.exe' build\\\\installer.nsi\n" "$$WIN_DIR" | \
	$(POWERSHELL) -NoProfile -Command -

run: deps  ## Run the application
	$(PY) src/main.py

clean: ## Remove build artifacts, venv, and generated files
	rm -rf dist/ build/tmp/ htmlcov/ .pytest_cache/ .ruff_cache/ .mypy_cache/ 2>/dev/null || true
	rm -f $(VERSION_FILE) coverage.xml junit.xml 2>/dev/null || true
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true
