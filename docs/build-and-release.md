# Build and Release

## Environment
Use the project virtual environment for commands:
- `PYTHON=.venv/bin/python`

## Core Commands
- Lint: `make lint PYTHON=.venv/bin/python`
- Tests + coverage: `make test-cov PYTHON=.venv/bin/python`
- Run app: `.venv/bin/python src/main.py`
- Build exe: `pyinstaller build/build.spec`
- Build installer: `makensis build/installer.nsi`

## Tooling
- Ruff: lint + formatting
- Pytest (+ pytest-qt, pytest-cov)
- Mypy
- PyInstaller + NSIS
- GitHub Actions workflows in `.github/workflows/`

## Release Mechanics
Operational release checklist remains in `AGENTS.md` and is mandatory unless explicitly waived by the user.

Version/update touchpoints commonly include:
- `src/utils/constants.py`
- `resources/default_config.json`
- `build/installer.nsi`
- `build/version_info.txt`
- `README.md`
- `CHANGELOG.md`

## Update System (App Behavior)
- update check: GitHub releases API
- prerelease/stable behavior controlled by config
- installer downloaded to user Downloads directory
- installer launched after app exit
