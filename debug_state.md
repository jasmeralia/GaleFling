# GaleFling Debug State

## Issue Summary

Two separate open issues:

**1. App crash opening OnlyFans login window (Settings dialog)**
Fatal Python error: Aborted on CrBrowserMain after page loaded successfully. Root cause: `WebViewLoginDialog` was never explicitly deleted after `exec()` returned — it persisted as a live child widget holding an active Chromium WebContents open against the shared `QWebEngineProfile`. When a new login dialog created a new page on the same profile, two WebContents existed simultaneously on the same browser context, causing a VSync service conflict and abort. Fix: `dialog.deleteLater()` added after `exec()` in both `settings_dialog.py` and `setup_wizard.py`. Not yet built/installed.

**2. OnlyFans 2FA "remember this device" checkbox — visual and server confirmation pending**
Vue state confirmed accepted (`checked=true` post-tick), but: (a) custom visual may not turn blue (`syncVisual` selector unconfirmed), (b) `remember_me: true` not confirmed reaching the server (no `[GaleFling] OF fetch intercepted` log seen). Session is currently broken — `auth_id` cookie was deleted during debugging; needs manual re-login through the app.

---

## Reproduction Steps (crash)

1. Open the app
2. Open Settings → OnlyFans → Open Login Window
3. Log in (or just open and close the window)
4. Open Settings → OnlyFans → Open Login Window again
5. App crashes with `Fatal Python error: Aborted` on CrBrowserMain

(May also reproduce after previously using the Setup Wizard for any WebView platform in the same process lifetime.)

## Observed Behavior (crash)

- `VSyncService: Failed to find adapter (via EnumAdapters1)` — twice during WebView creation
- `Page load finished ok=True`
- `QDxgiVSyncService not destroyed in time`
- `QEventDispatcherWin32::wakeUp: Failed to post a message (Invalid window handle.)`
- `Fatal Python error: Aborted` on `CrBrowserMain`
- Traceback: `settings_dialog.py:1010 _open_webview_login_window` → `dialog.exec()`

## Expected Behavior

Login window opens without crash.

---

## Current Hypotheses (MAX 5)

1. [High — fix applied] Stale Chromium WebContents from previous dialog — `WebViewLoginDialog` persisted as child widget after `exec()`, holding live WebContents against the shared `QWebEngineProfile`. Second dialog on same profile → two active WebContents → VSync conflict → abort. Fix: `dialog.deleteLater()` added.
2. [Medium] OnlyFans `syncVisual` selector mismatch — `.b-input-radio__label` may not match the actual DOM; no log confirmation the color update runs.
3. [Medium] OnlyFans fetch interceptor timing — no `[GaleFling] OF fetch intercepted` log entry seen; `remember_me: true` reaching the server unconfirmed.

---

## Evidence

**Crash:**
- `app_20260328_115651.log` 12:33:09 — full sequence above
- `fatal_errors.log` — Aborted on CrBrowserMain, traceback to `settings_dialog.py:1010`

**OnlyFans checkbox:**
- `[GaleFling] OF checkbox change dispatched, checked=true`
- `[GaleFling] OF checkbox post-tick (Vue re-render window), checked=true`
- No `[GaleFling] OF fetch intercepted` entry observed

---

## What Has Been Tried

- Crash fix (not yet built): `dialog.deleteLater()` added after `exec()` in `settings_dialog.py` and `setup_wizard.py`
- OnlyFans remember_me: prototype setter + `input`/`change` events — Vue accepted. Functionally correct but visual/server unverified.

---

## Files / Components of Interest

- `src/gui/settings_dialog.py:1008` — `_open_webview_login_window` (crash fix applied)
- `src/gui/setup_wizard.py:635` — `_open_login_window` (crash fix applied)
- `src/platforms/onlyfans.py` — `_inject_2fa_checkbox_fix` (`syncVisual`, fetch interceptor)

---

## Current Build Info

- App version: 1.7.20 (crash fix not yet in a build)
- Log analyzed: `app_20260328_115651.log`
- Run timestamp: 2026-03-28 12:33

---

## Next Step (SINGLE ACTION)

Build and install a new version with the crash fix, then re-open the OnlyFans login window from Settings to confirm no abort.

---
