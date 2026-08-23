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

The version is derived from git tags, not stored in source — see AGENTS.md's
"Version Management" for the full breakdown. In short: `scripts/write_version.py`
writes the gitignored `src/utils/_version.py`, which `src/utils/constants.py`
re-exports as `APP_VERSION`; `build/build.spec` generates `build/version_info.txt`
and `build/version.nsh` from that at PyInstaller time. `.github/workflows/release.yml`
computes the next tag from git history on `master` pushes (or reuses an existing
`refs/tags/vX.Y.Z` push) and builds exactly that tag — no version bump is ever
committed back to the repo.

Manual release touchpoints are:
- `CHANGELOG.md`
- `README.md` (only if release-adjacent wording changes)

## Linux Packaging

Releases include sideload-only DEB, RPM, AppImage, and Snap packages for both amd64 and arm64. They are attached to GitHub Releases and are not published to a package repository or app store.

The DEB, RPM, and AppImage builds require glibc 2.39 or newer, matching the Ubuntu 24.04 build environment. DEB and RPM packages enforce this through package dependencies; AppImage checks the host glibc version in `AppRun` and prints a clear error on older systems. Snap uses the glibc supplied by its `core24` base and is unaffected by the host system's glibc version.

The Snap uses classic confinement because GaleFling must read arbitrary user-selected media paths, including files outside the home directory and on external drives. Install it locally with `sudo snap install --classic --dangerous <file>.snap`.

## Update System (App Behavior)
- update check: GitHub releases API
- prerelease/stable behavior controlled by config
- installer downloaded to user Downloads directory
- installer launched after app exit
