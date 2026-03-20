# GaleFling — Suggested Commands

## Windows (primary — no make available in PATH by default)
```
# Lint
.venv/Scripts/python.exe -m ruff check src tests

# Tests with coverage
.venv/Scripts/python.exe -m pytest tests/ --cov=src

# Functional tests (require real credentials + network)
.venv/Scripts/python.exe -m pytest tests/functional/ -v

# Build exe
.venv/Scripts/python.exe -m PyInstaller build/build.spec --noconfirm

# Build installer (requires NSIS installed)
"C:/Program Files (x86)/NSIS/makensis.exe" build/installer.nsi

# Run the app (dev)
.venv/Scripts/python.exe src/main.py
```

## Linux / WSL (make available)
```
make lint PYTHON=.venv/bin/python
make test-cov PYTHON=.venv/bin/python
```

## Key Paths
| Resource           | Windows                                          | WSL                                              |
|--------------------|--------------------------------------------------|--------------------------------------------------|
| App data root      | C:\Users\storm\AppData\Roaming\GaleFling\        | /mnt/c/Users/storm/AppData/Roaming/GaleFling/    |
| Logs               | ...\logs\                                        | .../logs/                                        |
| WebView profiles   | ...\webprofiles\<account_id>\                    | .../webprofiles/<account_id>/                    |
| Cookie DB          | ...\webprofiles\<account_id>\Cookies             | .../webprofiles/<account_id>/Cookies             |
| Dist exe           | f:\git\GaleFling\dist\GaleFling.exe              |                                                  |
| Installer output   | f:\git\GaleFling\build\GaleFling-Setup-vX.Y.Z.exe|                                                  |
