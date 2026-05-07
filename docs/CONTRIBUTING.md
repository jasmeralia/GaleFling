# Contributing

Thanks for helping improve GaleFling. This guide covers development setup, testing, and releases.

## Prerequisites

- Python 3.11+
- pip
- Windows for building the installer

## Setup

```bash
python -m venv venv
source venv/bin/activate    # Linux/macOS
venv\Scripts\activate       # Windows

pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## Run

```bash
make run
# or
python src/main.py
```

## Lint & Test

```bash
make lint
make test
make test-cov
```

## Build

```bash
make build
make installer
```

## Release Process

1. Bump `APP_VERSION` in `src/utils/constants.py`
2. Update the README current version and Release Build badge tag
3. Add an entry to `CHANGELOG.md`
4. Commit and push:
   ```bash
   git commit -m "Release vX.Y.Z"
   git push origin master
   ```
5. The GitHub Action creates tag `vX.Y.Z` from `APP_VERSION`, builds a Windows executable, and publishes a **pre-release** with the installer attached.

If a `master` push does not include a fresh version, GitHub Actions automatically commits the next patch version before tagging and building.

## Project Structure

```
galefling/
├── src/
│   ├── main.py                      # Application entry point
│   ├── gui/                         # GUI layer
│   ├── platforms/                   # Platform integrations
│   ├── core/                        # Core services
│   └── utils/                       # Constants/helpers
├── infrastructure/                  # Log upload backend
├── resources/                       # Icons/config templates
├── tests/                           # Test suite
├── build/                           # Build scripts
└── .github/workflows/               # CI/CD
```
