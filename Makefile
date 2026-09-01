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
DESKTOP_SESSION_RUNNER := scripts/run-with-desktop-session.sh
WIN_VM_RUNNER := tools/windows-vm/run-tests.sh
WIN_VM_BUILD_RUNNER := tools/windows-vm/build-installer.sh
PYTEST_ARGS   ?=
BUILD_ARGS    ?=

.PHONY: help venv deps version-file lint lintfix format test test-ci test-cov \
        test-functional test-functional-non-mutating test-functional-mutating \
        test-functional-mutating-leave-up \
        test-functional-linux test-functional-xvfb test-functional-cmd \
        test-functional-win-vm test-functional-win-vm-clean \
        win-vm-installer win-vm-installer-clean \
        venv-win build-wsl build-linux installer-wsl run clean

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
	$(PY) -m ruff check src/ tests/ infrastructure/ scripts/ tools/oauth/ tools/validate_import_file.py tools/screenshots/
	$(PY) -m ruff format --check src/ tests/ infrastructure/ scripts/ tools/oauth/ tools/validate_import_file.py tools/screenshots/
	$(PY) -m mypy src/ scripts/release_info.py scripts/write_version.py
	shellcheck infrastructure/deploy.sh build/linux/appimage/AppRun $(DESKTOP_SESSION_RUNNER)
	shellcheck -x tools/windows-vm/*.sh

lintfix: ## Auto-fix lint issues and format code
	$(PY) -m ruff check --fix src/ tests/ infrastructure/ scripts/ tools/oauth/ tools/validate_import_file.py tools/screenshots/
	$(PY) -m ruff format src/ tests/ infrastructure/ scripts/ tools/oauth/ tools/validate_import_file.py tools/screenshots/

format: lintfix  ## Alias for lintfix

test: ## Run test suite (excludes functional)
	QT_QPA_PLATFORM=offscreen $(PY) -m pytest tests/ -v -m "not functional"

test-ci: ## Run the CI test suite with coverage (excludes functional)
	QT_QPA_PLATFORM=offscreen $(PY) -m pytest tests/ -v -m "not functional" \
		--cov=src \
		--cov-report=term-missing \
		--cov-report=html \
		--cov-report=xml:coverage.xml \
		--junitxml=junit.xml \
		-o junit_family=legacy

test-cov: test-ci  ## Alias for test-ci (deprecated; kept for one release)

test-functional: ## Run functional tests in strict mode
	GALEFLING_STRICT_FUNCTIONAL=1 $(PY) -m pytest tests/functional/ -m "functional and not disabled_platform" -v --no-header

test-functional-non-mutating: ## [Linux] Run strict tests that do not change platform state
	GALEFLING_STRICT_FUNCTIONAL=1 $(DESKTOP_SESSION_RUNNER) \
		$(PY) -m pytest tests/functional/ -m "functional and non_mutating and not disabled_platform" -v --no-header

test-functional-mutating: ## [Linux] Run strict tests that create or change real posts
	GALEFLING_STRICT_FUNCTIONAL=1 $(DESKTOP_SESSION_RUNNER) \
		$(PY) -m pytest tests/functional/ -m "functional and mutating and not disabled_platform" -v --no-header

test-functional-mutating-leave-up: ## [Linux] As above, but leave API posts on the live account for inspection
	GALEFLING_STRICT_FUNCTIONAL=1 $(DESKTOP_SESSION_RUNNER) \
		$(PY) -m pytest tests/functional/ -m "functional and mutating and not disabled_platform" \
		-v --no-header --leave-mutating-artifacts

test-functional-linux: ## [Linux] Run all strict functional tests on the live desktop
	GALEFLING_STRICT_FUNCTIONAL=1 $(DESKTOP_SESSION_RUNNER) \
		$(PY) -m pytest tests/functional/ -m "functional and not disabled_platform" -v --no-header

test-functional-xvfb: ## [Linux/WSL] Run functional tests under Xvfb virtual display
	xvfb-run -a $(PY) -m pytest tests/functional/ -m functional -v --no-header

test-functional-win-vm: ## [Linux→VM] Run functional tests in the Windows VM over SSH (PYTEST_ARGS="...")
	$(WIN_VM_RUNNER) $(PYTEST_ARGS)

test-functional-win-vm-clean: ## [Linux→VM] As above, reverting to the baseline snapshot first (discards guest changes)
	$(WIN_VM_RUNNER) --revert $(PYTEST_ARGS)

win-vm-installer: ## [Linux→VM] Build the Windows exe + NSIS installer in the VM over SSH, no tag needed (BUILD_ARGS="--exe-only" to skip NSIS)
	$(WIN_VM_BUILD_RUNNER) $(BUILD_ARGS)

win-vm-installer-clean: ## [Linux→VM] As above, reverting to the baseline snapshot first (discards guest changes)
	$(WIN_VM_BUILD_RUNNER) --revert $(BUILD_ARGS)

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

build-linux: ## [Linux] Build standalone Linux executable via PyInstaller
	$(PY) -m PyInstaller build/build.spec --distpath dist/ --workpath build/tmp --clean

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
