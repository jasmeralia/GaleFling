# Architecture Overview

## High-Level Model
GaleFling posts to multiple platforms from one composer, using an account-based architecture with two execution paths:
- API path: automatic posting in background worker threads
- WebView path: user-confirmed posting in embedded browser tabs

Core goals:
- isolate platform/account behavior
- keep failures localized to each platform
- preserve user context (drafts, session cookies, processed media)

## Core Subsystems
- `src/gui/main_window.py`
  - orchestrates compose -> preview -> post
  - splits API vs WebView platform flow
  - coordinates update checks, logs, drafts, setup wizard
- `src/gui/webview_panel.py`
  - hosts WebView post-confirm tabs and statuses
- `src/platforms/*`
  - API adapters (`twitter.py`, `bluesky.py`, `instagram.py`)
  - WebView adapters (`snapchat.py`, `onlyfans.py`, `fansly.py`, `fetlife.py`, `threads.py`)
- `src/platforms/base_webview.py`
  - shared WebView profile/session mechanics
  - composer navigation and prefill hooks
  - post confirmation/result handling
- `src/core/*`
  - media processing (`image_processor.py`, `video_processor.py`)
  - state/config/auth (`config_manager.py`, `auth_manager.py`)
  - troubleshooting (`logger.py`, `log_uploader.py`)

## Account Model
Account metadata is stored as account records keyed by `account_id`.
Typical fields:
- `platform_id`
- `account_id`
- `profile_name`
- `enabled`

This model allows multiple accounts per platform and independent enable/disable control.

## Two-Tier Posting Flow
1. User composes text/media and selects enabled accounts.
2. Main window partitions selected accounts into:
   - API platforms
   - WebView platforms
3. API platforms run first via `PostWorker`.
4. WebView platforms are prepared with text/media and opened in `WebViewPanel`.
5. Final results merge API + WebView outcomes in `ResultsDialog`.

## WebView Sessions
Each WebView account has its own persistent profile directory under app data.
This keeps cookies/session state isolated per account and avoids cross-account contamination.

## Results Semantics
WebView result states distinguish:
- user-confirmed posting
- URL successfully captured vs unavailable

For SPA-heavy sites, "posted (link unavailable)" is an expected non-error state.

## Reliability Features
- auto-save drafts and restore prompt
- file logs + screenshot capture + upload workflow
- non-blocking per-platform posting behavior
