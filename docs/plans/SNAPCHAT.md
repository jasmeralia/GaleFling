# Snapchat WebView2 Migration Plan

## Background

Snapchat's web app (`www.snapchat.com/web/`) crashes Qt's embedded Chromium renderer
with `STATUS_ACCESS_VIOLATION` (exit code `-1073741819`) approximately 1,200 ms after
the page HTML is received. Analysis of a HAR capture confirmed the following:

- `web.snapchat.com/` is a redirect stub — it returns `301 → www.snapchat.com/web/`
  unconditionally. The actual Snapchat web app lands at `www.snapchat.com/web/`.
- An **8.3 MB JS bundle** unique to `www.snapchat.com/web/` is served instantly from a
  Service Worker cache. The crash timing (~1,200 ms, variance < 20 ms across 82 cycles)
  is consistent with JS parse and initial execution of this bundle in Chromium 134.
- The page's CSP includes `worker-src blob:`, indicating the bundle spawns a Web Worker
  and likely instantiates WASM from a `blob:` URL. This does not appear as a network
  request in a HAR, but is the probable `ACCESS_VIOLATION` trigger inside the renderer.
- Disabling GPU acceleration (`--disable-gpu`) does not prevent the crash — it is a JS
  execution issue, not a GPU rendering issue.
- The SSO login flow redirects to `web.snapchat.com/#ticket=<token>`, which follows the
  301 to `www.snapchat.com/web/`. The JS there is designed to read the ticket from
  `window.location.hash` and complete authentication. The crash fires before this can
  happen, creating a 82-cycle crash loop in the recorded session (driven by the page's
  own JS re-initiating SSO on each failed load).

**Root cause:** The crash is in Chromium 134's renderer, specific to Qt's embedding
context. The same page works in system Chrome/Edge. PyQt6-WebEngine 6.10.0 (Chromium 134)
is the latest available on PyPI as of the writing of this plan. There is no newer
PyQt6-WebEngine version to upgrade to.

## Solution: Migrate webview platforms to WebView2

WebView2 uses the system Edge installation, which is updated automatically by Windows
Update. The Chromium version on the user's machine will be significantly newer than 134
and will either already have the crash fixed or receive the fix silently. No GaleFling
release is required for the fix to take effect once the migration is done.

Secondary benefits:
- FetLife's `test_connection` currently bypasses the live WebView probe because Cloudflare
  fingerprints the headless `QWebEnginePage` context and rejects it. WebView2's headless
  context fingerprint is indistinguishable from system Edge, so the live test should pass
  through Cloudflare. This eliminates the need for a separate visible-window workaround.
- The `--disable-gpu` compatibility mode setting becomes irrelevant.
- DevTools access becomes a single button click (`OpenDevToolsWindow()`) rather than
  port configuration.

---

## Dependency

Add to `requirements.txt` as a Windows-only conditional:

```
comtypes>=1.4.0; sys_platform == "win32"
```

`comtypes` is a pure Python COM interop library. It installs on Linux (keeping CI green)
but is only used at runtime on Windows. The WebView2 Runtime is pre-installed on all
Windows 10 1903+ and Windows 11 systems via Windows Update — no bundling required.

---

## New file: `src/platforms/base_webview2.py`

Replaces `src/platforms/base_webview.py` as the base for all webview platforms.
Contains two classes:

### `WebView2Widget(QWidget)`

A `QWidget` that hosts a `CoreWebView2Controller` as a Win32 child window embedded
within its own HWND. This is what `create_webview()` returns — it is still a `QWidget`,
so all GUI code (`QTabWidget.addTab`, `QLayout.addWidget`) works unchanged.

Responsibilities:
- On first `showEvent`: call `CreateCoreWebView2EnvironmentWithOptions` with the
  account's `UserDataFolder` path, then `CreateCoreWebView2Controller` with
  `self.winId()` as the parent HWND.
- On `resizeEvent`/`moveEvent`: update the WebView2 controller bounds via
  `put_Bounds` so the embedded window tracks the Qt widget's geometry.
- On `focusInEvent`: forward focus to the WebView2 controller via
  `MoveFocus(COREWEBVIEW2_MOVE_FOCUS_REASON_PROGRAMMATIC)`.

### `BaseWebView2Platform(BasePlatform)`

Same public interface as `BaseWebViewPlatform`. All platform subclass constants
(`COMPOSER_URL`, `TEXT_SELECTOR`, `SESSION_EXPIRED_SELECTORS`, `COOKIE_DOMAINS`,
`AUTH_COOKIE_NAMES`, etc.) are unchanged.

**Module-level import safety:** All Windows COM calls live inside method bodies, never
at module level. The module must be importable on Linux (for CI) without error. Any
attempt to call `create_webview()` on a non-Windows platform raises `RuntimeError`.

---

## API surface mapping

| Current (Qt WebEngine) | WebView2 equivalent |
|---|---|
| `QWebEngineProfile` with `setPersistentStoragePath` | WebView2 environment with `UserDataFolder` = same `webprofiles/{account_id}` path |
| `QWebEngineView` | `WebView2Widget(QWidget)` |
| `page.urlChanged` | `SourceChanged` event on `ICoreWebView2` |
| `page.loadStarted` | `NavigationStarting` event |
| `page.loadFinished` | `NavigationCompleted` event |
| `page.loadProgress` | No direct equivalent; omit or use CDP `Page.loadEventFired` |
| `acceptNavigationRequest` returning `False` | `NavigationStarting` event args with `Cancel = True` |
| `renderProcessTerminated` | `ProcessFailed` event on `ICoreWebView2` |
| `javaScriptConsoleMessage` override | CDP `Runtime.consoleAPICalled` via `CallDevToolsProtocolMethodAsync` |
| `page.runJavaScript(js, callback)` | `ExecuteScriptAsync(js)` with completion callback |
| `QWebEngineScript` at `DocumentReady` | `AddScriptToExecuteOnDocumentCreated` |
| `profile.scripts().insert(script)` | `AddScriptToExecuteOnDocumentCreated` (per environment) |
| `QTWEBENGINE_REMOTE_DEBUGGING` port | `OpenDevToolsWindow()` — native DevTools window, no port |
| Cookie DB at `webprofiles/{id}/Cookies` | Cookie DB at `webprofiles/{id}/EBWebView/Default/Cookies` — same Chromium SQLite schema, different path |

The cookie DB schema is identical between Qt's Chromium and Edge/WebView2. The existing
`_has_valid_session_in_db()` logic is reused unchanged; only `_get_cookie_db_path()`
needs updating to reflect the new subdirectory.

---

## Threading

WebView2 COM event callbacks arrive on the WebView2 thread, not the Qt main thread.
Every callback that touches Qt objects must be marshalled back to the main thread.

Establish a `_dispatch_to_main(fn)` helper in `BaseWebView2Platform`:

```python
def _dispatch_to_main(self, fn):
    QTimer.singleShot(0, fn)
```

All WebView2 event handlers route through this before touching any Qt state.
Getting this wrong causes non-deterministic crashes. This is the highest-risk part
of the implementation.

---

## Changes to existing files

### `src/platforms/snapchat.py`, `onlyfans.py`, `fansly.py`, `fetlife.py`

Change the import:
```python
# before
from src.platforms.base_webview import BaseWebViewPlatform
# after
from src.platforms.base_webview2 import BaseWebView2Platform
```

Change the base class declaration. No other changes to class constants or business logic.

The `_inject_2fa_checkbox_fix` in `onlyfans.py` currently uses `QWebEngineScript` —
this is ported to `AddScriptToExecuteOnDocumentCreated` with equivalent injection point
and world settings.

### `src/gui/webview_panel.py`

No changes required. `create_webview()` still returns a `QWidget`; `addTab` and
`addWidget` calls are unaffected.

### `src/gui/setup_wizard.py`

Line 697 already has `if hasattr(self._view, 'page')` guard — no change needed there.

The `profile.cookieAdded` signal (used for login detection) must move into the platform
class. `BaseWebView2Platform` exposes a `cookie_added` callback attribute that
`WebViewLoginDialog` can connect to, replacing the Qt profile signal.

### `src/gui/settings_dialog.py`

- Remove the remote debug port spinbox and label.
- Replace "Enable remote debugging" checkbox with an "Open DevTools" button that calls
  `platform.get_webview().open_devtools()` on the currently active platform.
- The compatibility mode checkbox (`--disable-gpu`) can be left as a labelled no-op for
  one release, then removed.

### `src/main.py`

- `_apply_remote_debugging()` becomes a no-op / is removed.
- `_apply_webview_compatibility_flags()` becomes a no-op / is removed.
- `_WEBVIEW_COMPAT_FLAGS` constant is removed.

### `requirements.txt`

- Add `comtypes>=1.4.0; sys_platform == "win32"`.
- `PyQt6-WebEngine>=6.6.0` is removed once all platforms are migrated (Phase 5).

---

## Test suite impact

Unit tests in `tests/test_webview_platform.py` and `tests/test_webview_platforms.py`
test pure Python business logic (cookie checking, URL patterns, result building,
platform names). These import the platform modules at the top level. As long as
`base_webview2.py` defers all COM calls to method bodies (no module-level Windows API
usage), these imports succeed on Linux and the tests pass without change.

Tests that exercise `create_webview()` (e.g. `test_base_webview_create_webview_and_navigation_signals`)
monkeypatch the underlying classes. The monkeypatching targets must be updated to patch
the WebView2 equivalents (`WebView2Widget`, etc.) instead of Qt WebEngine classes.

The CI workflow (`ubuntu-latest`) is unaffected provided the conditional requirement
`comtypes; sys_platform == "win32"` keeps `comtypes` off the Linux install.

---

## Migration sequence

1. **Spike** — Build a minimal standalone `WebView2Widget` (outside GaleFling) that
   opens a URL in a QWidget to validate: HWND embedding, COM callback thread marshalling,
   and `UserDataFolder` isolation. Do not proceed to production code until all three
   are confirmed working.

2. **`src/platforms/base_webview2.py`** — Full implementation of `WebView2Widget` and
   `BaseWebView2Platform`. Unit tests updated in parallel.

3. **Snapchat** — Switch `SnapchatPlatform` to `BaseWebView2Platform`. Validate the full
   login flow (SSO ticket exchange at `www.snapchat.com/web/`, navigation to web app,
   posting) end-to-end.

4. **Remaining platforms** — Migrate `OnlyFansPlatform`, `FanslyPlatform`,
   `FetLifePlatform` one at a time. Validate `test_connection` for FetLife now passes
   Cloudflare without the visible-window workaround.

5. **Cleanup** — Remove `src/platforms/base_webview.py`, remove `PyQt6-WebEngine` from
   `requirements.txt` and CI apt installs, clean up settings UI.

`BaseWebViewPlatform` and `BaseWebView2Platform` coexist during steps 2–4. No platform
is broken while others are being migrated.

---

## Open question

The spike must confirm whether `comtypes`-generated WebView2 COM bindings handle the
async `CreateCoreWebView2EnvironmentWithOptions` callback correctly within Qt's Windows
message loop (which Qt drives via its own event dispatcher). If the COM message pump
requires explicit `CoWaitForMultipleObjects` or `MsgWaitForMultipleObjects` calls that
conflict with Qt's dispatcher, an alternative dispatch strategy (e.g. a dedicated thread
for COM with cross-thread queuing) will be needed before proceeding to step 2.
