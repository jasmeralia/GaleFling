# Debug Instrumentation Plan

Targeted logging additions to help diagnose two known issues without requiring a HAR
capture or Chrome DevTools session. These are small, self-contained changes that can
be shipped independently of the WebView2 migration.

---

## 1. OnlyFans — 2FA checkbox DOM dump

### Problem

The 2FA "remember me" checkbox on OnlyFans is intermittently unclickable in the embedded
WebView. The checkbox fix script in `onlyfans.py` already emits `[GaleFling] checkbox
found ...` diagnostics via `console.log`, which are captured by
`_LoggingWebEnginePage.javaScriptConsoleMessage` at DEBUG log level. However, the fix
script fires on every DOM mutation, and it is not clear whether the fix is being applied
before or after the checkbox becomes unclickable, or whether the Cloudflare Turnstile
iframe is still covering the element at click time.

### Change

In `OnlyFansPlatform`, override `_on_load_finished` (or connect an additional handler
after the base class `loadFinished` + `SESSION_EXPIRED_CHECK_DELAY_MS` window) to run a
`runJavaScript` call that dumps the rendered DOM state of every checkbox and the 2FA
form container.

**Trigger:** After `SESSION_EXPIRED_CHECK_DELAY_MS` (4,000 ms) has elapsed following
`loadFinished`. This ensures Vue.js has mounted and the 2FA form (if present) is in the
DOM before the snapshot is taken.

**JS to run:**

```javascript
(function () {
    var results = [];
    document.querySelectorAll(
        'input[type="checkbox"], .b-chckbox, .b-loginreg__form, iframe'
    ).forEach(function (el) {
        var s = window.getComputedStyle(el);
        var r = el.getBoundingClientRect();
        results.push({
            tag: el.tagName,
            id: el.id || null,
            className: el.className || null,
            type: el.getAttribute('type') || null,
            disabled: el.disabled || false,
            checked: el.checked !== undefined ? el.checked : null,
            display: s.display,
            visibility: s.visibility,
            pointerEvents: s.pointerEvents,
            opacity: s.opacity,
            zIndex: s.zIndex,
            position: s.position,
            width: Math.round(r.width),
            height: Math.round(r.height),
            top: Math.round(r.top),
            left: Math.round(r.left),
            src: el.src || null
        });
    });
    return JSON.stringify(results);
})()
```

**Log output:** Emit the result at DEBUG level via `_log_webview_debug`, labelled
`'2FA form DOM snapshot'`. Each element is logged as a structured field so it is
grep-able from a log file.

### What this tells us

- Whether the checkbox exists in the DOM at all after the delay
- Whether `pointer-events` is still `none` on the checkbox or its container (would mean
  the fix script is not running, or running but being overridden)
- Whether a Cloudflare iframe is present with `position: fixed` and a non-zero z-index
  that could be intercepting clicks above the checkbox
- Whether the checkbox is `disabled` at snapshot time

### Files changed

- `src/platforms/onlyfans.py` — add DOM snapshot trigger after the session-expired check
  delay

---

## 2. FetLife — cookie diagnostic logging

### Problem

`FetLifePlatform.test_connection` currently returns cookie-only results: it calls
`has_valid_session()` and returns `True` or `WV-SESSION-EXPIRED` without performing a
live page load. This is intentional — the headless `QWebEnginePage` used by the base
class live test is fingerprinted by Cloudflare and always redirected to login regardless
of cookie validity, making the live test unreliable. See `fetlife.py` docstring for full
rationale.

The immediate problem is that when `has_valid_session()` returns `False`, there is no
log output indicating *why* — which cookie names were found, which were missing, whether
the DB was locked or corrupt. Users see only `WV-SESSION-EXPIRED` with no actionable
detail.

### Change

In `BaseWebViewPlatform._has_valid_session_in_db` (or a FetLife-specific override of
`has_valid_session`), add DEBUG-level logging when the session check fails, recording:

- The cookie DB path checked
- The cookie names actually found in the DB for the relevant domains (names only,
  never values)
- Which required auth cookie names were present vs missing
- Whether the failure was due to a missing DB, locked DB, missing table, or simply no
  matching cookies

**Example log output (DEBUG):**

```
FetLife [webview]: session check failed
  db_path='C:\...\webprofiles\fetlife_1\Cookies'
  domains_checked=['fetlife.com']
  required_names=['_fl_sessionid', 'remember_user_token', '_fl_session_remember_me']
  found_names=['cf_clearance', '__utmz']
  missing=['_fl_sessionid', 'remember_user_token', '_fl_session_remember_me']
  reason='no_auth_cookie_match'
```

Keep the existing fast-path (`COOKIE_DB_TIMEOUT_SECONDS = 0.01`) — this is only
additional logging, not a behavioural change.

### Files changed

- `src/platforms/base_webview.py` — extend `_has_valid_session_in_db` (or add a
  `_log_session_check_failure` helper) to emit structured failure detail at DEBUG level

### Deferred: real live connection test for FetLife

A genuine live connection test (page load, not just cookie presence) for FetLife is
deferred until after the WebView2 migration. The reason the live test was disabled is
that Qt's headless `QWebEnginePage` is fingerprinted by Cloudflare. WebView2's headless
context uses the same fingerprint as system Edge and is expected to pass Cloudflare
challenges without issue. Once `FetLifePlatform` is migrated to `BaseWebView2Platform`,
the `test_connection` override in `fetlife.py` should be removed and the base class live
test re-enabled. This should be validated explicitly as part of Phase 4 of the WebView2
migration (see `docs/plans/SNAPCHAT.md`).
