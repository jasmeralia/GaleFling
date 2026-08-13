# GaleFling Debug State

## Issue Summary

**1. App crash opening a WebView login window (Settings dialog) — fix applied, verify in build**

Fatal Python error: Aborted on CrBrowserMain after page loaded successfully. Root cause:
`WebViewLoginDialog` was never explicitly deleted after `exec()` returned — it persisted
as a live child widget holding an active Chromium WebContents open against the shared
`QWebEngineProfile`. When a new login dialog created a new page on the same profile,
two WebContents existed simultaneously on the same browser context, causing a VSync service
conflict and abort. Fix: `dialog.deleteLater()` added after `exec()` in both
`settings_dialog.py` and `setup_wizard.py`. Not yet built/installed at time of last
triage.

> **OnlyFans login window removed.** GaleFling no longer offers embedded OnlyFans login
> (auth.json import only). Reproduce this crash using Fansly, FetLife, or another
> WebView platform that still has a login window.

**2. OnlyFans 2FA checkbox — closed (obsolete flow)**

The 2FA "remember this device" checkbox debug thread is **no longer relevant**. GaleFling
does not log in to OnlyFans in the embedded browser. Functional tests do not cover
OnlyFans composer checkboxes; add interaction tests only if a future functional test
demonstrates a real failure. See `docs/testing/WEBVIEW_TEST_PLAN.md` Phase 6.

---

## Reproduction Steps (crash)

1. Open the app
2. Open Settings → Fansly (or FetLife) → Open Login Window
3. Log in (or just open and close the window)
4. Open Settings → same platform → Open Login Window again
5. App crashes with `Fatal Python error: Aborted` on CrBrowserMain

(May also reproduce after previously using the Setup Wizard for any WebView platform in the same process lifetime.)

## Observed Behavior (crash)

- `VSyncService: Failed to find adapter (via EnumAdapters1)` — twice during WebView creation
- `Page load finished ok=True`
- `QDxgiVSyncService not destroyed in time`
- `QEventDispatcherWin32::wakeUp: Failed to post a message (Invalid window handle.)`
- `Fatal Python error: Aborted` on `CrBrowserMain`
- Traceback: `settings_dialog.py` → `_open_webview_login_window` → `dialog.exec()`

## Expected Behavior

Login window opens without crash.

---

## Current Hypotheses (MAX 5)

1. [High — fix applied] Stale Chromium WebContents from previous dialog — `WebViewLoginDialog` persisted as child widget after `exec()`, holding live WebContents against the shared `QWebEngineProfile`. Second dialog on same profile → two active WebContents → VSync conflict → abort. Fix: `dialog.deleteLater()` added.

---

## Evidence

**Crash:**
- `app_20260328_115651.log` 12:33:09 — full sequence above
- `fatal_errors.log` — Aborted on CrBrowserMain, traceback to `settings_dialog.py`

---

## What Has Been Tried

- Crash fix (not yet built): `dialog.deleteLater()` added after `exec()` in `settings_dialog.py` and `setup_wizard.py`

---

## Files / Components of Interest

- `src/gui/settings_dialog.py` — `_open_webview_login_window` (crash fix applied)
- `src/gui/setup_wizard.py` — `_open_login_window` (crash fix applied)

---

## Current Build Info

- App version at last triage: 1.7.20 (crash fix not yet in that build)
- Log analyzed: `app_20260328_115651.log`
- Run timestamp: 2026-03-28 12:33

---

## Next Step (SINGLE ACTION)

Build and install a new version with the crash fix, then re-open a WebView login window
(Fansly or FetLife) from Settings to confirm no abort.
