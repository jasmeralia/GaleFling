# GaleFling — WebView Platform Architecture

## Shared Profile Registry
- `BaseWebViewPlatform._profile_registry: dict[str, QWebEngineProfile]` (class-level)
- One Chromium context per `account_id` for entire process lifetime
- Profile created with `parent=None` to avoid Qt destruction-ordering issues
- All platform instances for the same account share the same Chromium context

## Connection Test Flow
- `test_connection()` → checks SQLite cookies (cold start) or uses active profile
- `_run_live_connection_test()` → loads the platform page in a `QEventLoop`
- Uses `SESSION_EXPIRED_SELECTORS` (CSS selectors) + DOM check to detect expired sessions
- `SESSION_EXPIRED_CHECK_DELAY_MS` — delay before DOM check (OnlyFans=8000ms for CF cold start)
- `CONNECTION_TEST_STARTUP_DELAY_MS` — delay before first page load (OnlyFans=2000ms)
- `CONNECTION_TEST_TIMEOUT_MS` — total timeout (OnlyFans=25000ms)

## Login Detection (WebViewLoginDialog)
Three-layer detection:
1. `cookieAdded` signal — fires when new cookies set on login
2. `loadFinished` + DOM check — detects pre-existing sessions (no new cookies)
3. 3-second polling fallback via `has_valid_session()` SQLite check

## Live Connection Test UI (_ConnectionTestProgressDialog)
- Opens immediately when Test Connections clicked
- Spinner rows (braille chars, 80ms timer) update to ✔/✘ as results arrive
- WebView tests: sequential on main thread (nested QEventLoop, spinners still animate)
- API tests: `_ConnectionTestWorker(QThread)` with `result_ready` signal
- Cancel button: always enabled; Close button: disabled until all tests done
- WV-SESSION-EXPIRED failures show "Open Login Window" button + re-enable callback

## Platform-Specific Notes
- **OnlyFans:** Cloudflare JS challenge on cold start; `_cfuvid` not persisted; 8s DOM delay
- **FetLife:** `opacity:0` checkbox pattern — CSS injection overrides it; `create_webview` override
- **Snapchat:** Video-only; images auto-converted to MP4; `supports_images=False`, `supports_text=False`
- **Threads:** Placeholder; TEXT_SELECTOR and AUTH_COOKIE_NAMES need empirical verification (see AGENTS.md)
