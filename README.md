# GaleFling

Windows desktop application for posting to multiple social media platforms simultaneously. Built with PyQt5 for a non-technical end user, with robust error handling and remote troubleshooting via log uploads.

**Current Version:** 0.2.55 (Phase 0)

## Supported Platforms

| Platform | API | Auth Method |
|----------|-----|-------------|
| Twitter | Tweepy (v2 + v1.1 media) | OAuth 1.0a |
| Bluesky | AT Protocol (atproto) | App password |

## Features

- Post text + optional image to Twitter and Bluesky simultaneously
- Live character counters per platform (280 Twitter / 300 Bluesky)
- Automatic image resize and compression per platform specs
- Tabbed image preview showing per-platform processing results
- Bluesky link facets (URLs auto-detected and made clickable)
- Clickable post URLs in results dialog with copy buttons
- Error code system with user-friendly messages
- First-run setup wizard for credential entry
- Log upload to remote endpoint for remote troubleshooting
- Auto-update checker via GitHub Releases
- Draft auto-save with restore on restart
- Screenshot capture on errors
- Help > About with credits and license info
- View menu theme toggle (System/Light/Dark) with persistent setting

## Quick Start

### Prerequisites

- Python 3.11+
- pip

### Setup

```bash
python -m venv venv
source venv/bin/activate    # Linux/macOS
venv\Scripts\activate       # Windows

pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### Run

```bash
make run
# or
python src/main.py
```

### Development

```bash
make lint        # Check code with ruff
make lint-fix    # Auto-fix lint issues and format
make test        # Run test suite
make test-cov    # Run tests with coverage report
make build       # Build standalone .exe with PyInstaller
make installer   # Build NSIS installer (requires makensis)
make clean       # Remove build artifacts
```

## Project Structure

```
galefling/
├── src/
│   ├── main.py                      # Application entry point
│   ├── gui/
│   │   ├── main_window.py           # Main application window
│   │   ├── setup_wizard.py          # First-run credential setup
│   │   ├── post_composer.py         # Text input + image selection
│   │   ├── platform_selector.py     # Platform checkboxes
│   │   ├── image_preview_tabs.py    # Tabbed per-platform image previews
│   │   ├── results_dialog.py        # Post results with clickable links
│   │   └── settings_dialog.py       # Debug, updates, log upload config
│   ├── platforms/
│   │   ├── base.py                  # Abstract platform interface
│   │   ├── twitter.py               # Twitter via Tweepy
│   │   └── bluesky.py               # Bluesky via atproto (with link facets)
│   ├── core/
│   │   ├── image_processor.py       # Resize/compress per platform
│   │   ├── error_handler.py         # Error codes + user messages
│   │   ├── logger.py                # File logging + screenshot capture
│   │   ├── config_manager.py        # App settings persistence
│   │   ├── auth_manager.py          # Credential storage
│   │   ├── log_uploader.py          # HTTP POST logs to endpoint
│   │   └── update_checker.py        # GitHub release checking
│   └── utils/
│       ├── constants.py             # Platform specs, error codes
│       └── helpers.py               # Utility functions
├── infrastructure/
│   ├── template.yaml                # CloudFormation (Lambda + API GW + SES)
│   ├── lambda_function.py           # Log upload Lambda handler
│   └── deploy.sh                    # One-command CFT deployment
├── resources/
│   └── default_config.json          # Default settings template
├── tests/
│   ├── test_platforms.py
│   ├── test_image_processor.py
│   └── test_error_handler.py
├── build/
│   ├── build.spec                   # PyInstaller specification
│   ├── version_info.txt             # Windows exe metadata
│   └── installer.nsi                # NSIS installer script
├── scripts/
│   └── commit_with_changelog_notes.sh # Commit helper using changelog notes
├── .github/workflows/
│   └── release.yml                  # Draft release on tag push
├── Makefile
├── pyproject.toml                   # ruff + pytest config
├── requirements.txt
├── requirements-dev.txt
├── CHANGELOG.md
├── LICENSE.md
└── AGENTS.md
```

## Backend Infrastructure

The log upload endpoint is deployed to AWS via CloudFormation:

- **Endpoint:** `https://galepost.jasmer.tools/logs/upload`
- **Stack:** Lambda (Python 3.11) + HTTP API Gateway + SES
- **Notifications:** Email to `morgan@windsofstorm.net` via SES

See [infrastructure/](infrastructure/) for the CFT and deployment script.

## Releasing

1. Bump the version in `src/utils/constants.py`, `resources/default_config.json`, `build/version_info.txt`, and `build/installer.nsi`
2. Add an entry to `CHANGELOG.md`
3. Update this README if features changed
4. Commit, tag, and push:
   ```bash
   git tag v0.2.55
   git push origin v0.2.55
   ```
5. The GitHub Action builds a Windows executable and creates a **draft release** with commit history
6. Review the draft on GitHub and publish when ready

## License

MIT License - Copyright (c) 2026 Morgan Blackthorne

## Roadmap

- **Phase 0** (current): Twitter + Bluesky, single image, core features
- **Phase 1**: Additional platforms (SuicideGirls, etc.), multi-image, platform-specific text
- **Phase 2**: Video support with FFmpeg encoding and progress bars; add macOS build pipeline
