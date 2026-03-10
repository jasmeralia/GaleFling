# GaleFling

![CI](https://github.com/jasmeralia/GaleFling/actions/workflows/ci.yml/badge.svg?branch=master)
![Release Build](https://img.shields.io/github/actions/workflow/status/jasmeralia/GaleFling/release.yml?event=push&branch=v1.5.15&label=Release%20Build)
![Release](https://img.shields.io/github/v/release/jasmeralia/GaleFling?include_prereleases&sort=semver&label=Release)
![Coverage](https://codecov.io/gh/jasmeralia/GaleFling/branch/master/graph/badge.svg)

GaleFling is a Windows desktop app for posting to multiple social platforms at once. It’s designed for non-technical creators, with clear guidance, robust error handling, and one-click log sharing for support.

**Current Version:** 1.5.15

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

- Write your post text and optionally attach media (images or video).
- Select the platforms you want to post to.
- Click **Post Now** to publish to all enabled platforms.

### Media Support

GaleFling handles images and videos with automatic per-platform processing:

- **Images:** JPEG, PNG, GIF (animated), WEBP, BMP — resized and compressed to fit each platform's limits.
- **Videos:** MP4, MOV, AVI, MKV, WEBM — resized, trimmed, and re-encoded (H.264 + AAC) as needed.
- **Automatic format conversion:** Static images are converted to a platform-supported format when needed (for example, WEBP can be converted to PNG/JPEG automatically).
- **Format restrictions:** Platforms are only disabled when automatic conversion is not possible (for example, animated GIF support remains platform-specific).
- **Video-only platforms:** Snapchat stories support video uploads. Static image attachments are auto-converted to MP4, and for multiple images you can choose `Use first image only` or `Create slideshow video` in the composer.
- **Snapchat framing controls:** For Snapchat media that needs portrait reframing, choose `Crop to vertical` or `Rotate to vertical` in the composer.
- **Text warnings:** Platforms that don't support text (e.g., Snapchat) show a warning if you've entered text.
- **Preview:** Click "Preview Media" to see how your image or video will look on each platform after processing.

## Updates

GaleFling checks for updates on startup (configurable).  
If you want beta builds, enable **Settings → Advanced Settings → Enable beta updates**.

## Troubleshooting

If something goes wrong, use **Help → Send Logs to Jas**. This bundles logs and screenshots for troubleshooting, along with your detected ffmpeg binary version.
For WebView login debugging, use **Settings → (WebView platform tab) → Export ... Cookies** to inspect stored browser cookies.
You can also quickly open the local logs folder via **Help → Open Log Directory**.

## Screenshots

Coming soon.

## For Developers

Development docs are in `docs/CONTRIBUTING.md`.
