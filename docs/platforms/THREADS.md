# Threads Setup Guide

GaleFling posts to Threads via an embedded WebView at `threads.net`. Threads shares its authentication with Instagram — the same Meta session cookies are used.

> **Status: Setup incomplete.** The text composer selector and auth cookie names require empirical verification before this platform can be considered production-ready. See [Verification Steps](#verification-steps) below.

## Account Type

Any Threads account works. GaleFling supports **up to 2 Threads accounts**.

## Credential Setup

Threads uses session cookies stored in a persistent WebView profile. There are no API keys to enter.

### Step 1: Log In via GaleFling

1. Open GaleFling and go to **Settings > Accounts > Threads**.
2. Click **Log In**. An embedded browser opens `threads.net`.
3. Complete the Threads (Instagram/Meta) login flow.
4. Once the Threads home page loads, GaleFling detects the session and closes the login window.

Your session cookies are stored in an isolated profile directory under `%APPDATA%\GaleFling\webprofiles\threads_1\`.

### Session Cookies

GaleFling currently validates session by checking for the following cookie:

| Cookie | Notes |
|---|---|
| `sessionid` | Instagram/Meta shared session cookie |

> **Unverified:** The `sessionid` cookie is used by Instagram and is expected to be present on `threads.net`, but this has not been empirically confirmed. See [Verification Steps](#verification-steps).

### Session Expiry

Threads sessions expire periodically. When your session expires, GaleFling will show a "session expired" warning. Repeat Step 1 to re-establish the session.

## Media Restrictions

### Images

| Constraint | Limit |
|---|---|
| Formats | JPEG, PNG, GIF |
| Max dimensions | 1440 × 1440 px |
| Max file size | 10 MB |
| Max attachments | 10 images per post |

### Videos

| Constraint | Limit |
|---|---|
| Format | MP4 |
| Max dimensions | 1920 × 1080 px |
| Max file size | 1024 MB (1 GB) |
| Max duration | 300 seconds (5 minutes) |

### Text

| Constraint | Limit |
|---|---|
| Max length | 500 characters |
| Text with media | Supported |

## Platform Behavior

- **API type**: `webview` — you confirm the post in the embedded browser panel.
- **Auth method**: `sessionid` Meta session cookie in isolated WebView profile.
- **Text selector**: `[data-lexical-editor="true"]` (unverified — see below).
- **Success URL pattern**: `https://www.threads.net/@<username>/post/<id>` (unverified).
- **Pre-fill delay**: 500 ms SPA hydration delay.

## Verification Steps

The following values require manual verification before Threads can be used reliably. After verifying, update `src/platforms/threads.py` and remove the `THREADS_PLACEHOLDER` comments.

### Verify the Text Composer Selector

1. Open `https://www.threads.net/` in a Chromium-based browser.
2. Log in and click the composer area.
3. Open DevTools Console and run:
   ```js
   document.activeElement.tagName + ' / ' + document.activeElement.getAttribute('data-lexical-editor')
   ```
4. Also check these likely candidates:
   - `[data-lexical-editor="true"]`
   - `[contenteditable="true"][role="textbox"]`
   - `div[aria-label*="thread"]`
5. Verify that setting `.textContent` + dispatching an `input` event actually updates the composer state.

### Verify Auth Cookie Names

1. Open DevTools → **Application → Cookies** for `threads.net`.
2. Log in and observe which cookies are set.
3. Log out and confirm which cookies disappear or become invalid.
4. Update `AUTH_COOKIE_NAMES` in `src/platforms/threads.py` with the confirmed set.

### After Verification

1. Update `TEXT_SELECTOR` and `AUTH_COOKIE_NAMES` in `src/platforms/threads.py`.
2. Remove `THREADS_PLACEHOLDER` comments.
3. Update `tests/test_threads.py` if selector/cookie assertions need updating.
4. Run lint and tests, then follow the release checklist.

## Troubleshooting

| Problem | Solution |
|---|---|
| Text not pre-filled | The composer selector may be outdated. Follow the verification steps above to find the current selector. |
| "Session expired" on launch | Log in again via Settings > Accounts > Threads. |
| `WV-SESSION-EXPIRED` in results | Session cookies expired or the auth cookie name is wrong. Log in again and verify cookie names if the problem persists. |
