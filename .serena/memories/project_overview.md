# GaleFling — Project Overview

**Purpose:** Windows GUI desktop app for posting to multiple social platforms simultaneously.
- Target user: non-technical content creator (Rin)
- Developer/operator: Jas
- Current version: 1.7.9 (active v1.x development)
- Priorities: simplicity, reliability, clear guidance, strong troubleshooting support

## Tech Stack
- Python 3.11+, PyQt6 (GUI + embedded Chromium via QWebEngineView)
- API platforms: Tweepy (Twitter), atproto (Bluesky), requests (Instagram Graph API)
- WebView platforms: Snapchat, OnlyFans, Fansly, FetLife, Threads — session-cookie auth via embedded browser
- Media: Pillow (images), ffmpeg via imageio-ffmpeg (video)
- Packaging: PyInstaller → exe, NSIS → installer
- Lint: ruff (line-length=100, single quotes, rules E/F/W/I/N/UP/B/SIM)
- Tests: pytest, coverage via pytest-cov

## Structure
```
src/
  main.py                 # entry point, Qt app setup
  gui/                    # MainWindow, setup wizard, composer, previews, dialogs
  platforms/              # API + WebView platform adapters (base.py, base_webview.py, per-platform)
  core/                   # auth, config, image/video processing, logging, update checker
  utils/                  # constants (PlatformSpecs, error codes), helpers, theme
tests/
  functional/             # real-credential WebView tests (marked "functional")
resources/                # icon, default_config.json
build/                    # build.spec, installer.nsi, version_info.txt
docs/                     # architecture, media processing, build/release, platform specs
```

## Key Architecture Concepts
- **Multi-account model:** `AccountConfig(platform_id, account_id, profile_name, enabled)` drives platform creation
- **Two-tier posting:** API platforms in background thread, WebView platforms in `WebViewPanel` (user confirms)
- **Shared QWebEngineProfile registry:** `BaseWebViewPlatform._profile_registry[account_id]` — one Chromium context per account for the process lifetime
- **Media prep:** platform-aware, cached per platform-group before posting
- **Drafts:** auto-save/restore; logs + screenshots for remote debugging
