# GaleFling

![CI](https://github.com/jasmeralia/GaleFling/actions/workflows/ci.yml/badge.svg?branch=master)
![Release Build](https://img.shields.io/github/actions/workflow/status/jasmeralia/GaleFling/release.yml?label=Release%20Build&event=push)
![Release](https://img.shields.io/github/v/release/jasmeralia/GaleFling?include_prereleases&sort=semver&label=Release)
![Coverage](https://codecov.io/gh/jasmeralia/GaleFling/branch/master/graph/badge.svg)

GaleFling is a Windows desktop app for posting to multiple social platforms at once. It’s designed for non-technical creators, with clear guidance, robust error handling, and one-click log sharing for support.

**Current Version:** 1.3.2 (Phase 1 - Multi-account & WebView platforms)

Docs: [Changelog](CHANGELOG.md) | [Roadmap](docs/ROADMAP.md) | [Contributing](docs/CONTRIBUTING.md) | [Twitter Setup](docs/TWITTER.md) | [Instagram Setup](docs/INSTAGRAM.md)

## Download & Install

Grab the latest installer from the GitHub Releases page and run it on Windows 10/11.

## First-Time Setup

On first launch, the app walks you through adding credentials for each platform. Only platforms with valid credentials are enabled.

### Platform-Specific Guides

- **[Twitter Setup](docs/TWITTER.md)** — Developer portal setup, API keys, and PIN-based OAuth flow (up to 2 accounts).
- **[Instagram Setup](docs/INSTAGRAM.md)** — Graph API credentials, Business/Creator account requirements, and token management.
- **Bluesky** — Enter your handle and an app password (create one at [bsky.app/settings/app-passwords](https://bsky.app/settings/app-passwords)). Supports up to 2 accounts.
- **WebView platforms** (Snapchat, OnlyFans, Fansly, FetLife) — Log in via the embedded browser during setup. Session cookies are stored locally.

## Using GaleFling

- Write your post text and optionally attach an image.
- Select the platforms you want to post to.
- Click **Post Now** to publish to all enabled platforms.

## Updates

GaleFling checks for updates on startup (configurable).  
If you want beta builds, enable **Settings → Enable beta updates**.

## Troubleshooting

If something goes wrong, use **Help → Send Logs to Jas**. This bundles logs and screenshots for troubleshooting.

## Screenshots

Coming soon.

## For Developers

Development docs are in `docs/CONTRIBUTING.md`.
