# OnlyFans Setup Guide

GaleFling posts to OnlyFans via an embedded WebView at `onlyfans.com`. OnlyFans is protected by Cloudflare, which adds latency to page loads and session detection.

## Account Type

Any OnlyFans creator account works. GaleFling supports **1 OnlyFans account**.

## Credential Setup

OnlyFans uses session cookies stored in a persistent WebView profile. There are no API keys to enter.

### Step 1: Log In via GaleFling

1. Open GaleFling and go to **Settings > Accounts > OnlyFans**.
2. Click **Log In**. An embedded browser opens `onlyfans.com`.
3. Complete the OnlyFans login flow (email/password + 2FA if enabled).
4. Once the OnlyFans home page loads, GaleFling detects the session and closes the login window.

Your session cookies are stored in an isolated profile directory under `%APPDATA%\GaleFling\webprofiles\onlyfans_1\`.

### 2FA Checkbox Fix

OnlyFans renders its 2FA "remember me" checkbox using Vue.js custom components that can block click events in an embedded WebView. GaleFling automatically injects a script that fixes pointer events and click forwarding on these checkboxes, so 2FA should work normally.

### Session Expiry

OnlyFans sessions expire periodically. Unlike most platforms, OnlyFans does **not redirect to a login URL** when the session expires — it renders an inline login form at the same URL. GaleFling detects this by checking the DOM for login form selectors (`.b-loginreg__form`, `input[type="password"]`).

When your session expires, GaleFling will show a "session expired" warning. Repeat Step 1 to re-establish the session.

## Media Restrictions

### Images

| Constraint | Limit |
|---|---|
| Formats | JPEG, PNG, WEBP |
| Max dimensions | 4096 × 4096 px |
| Max file size | 50 MB |
| Max attachments | 4 images per post |

### Videos

| Constraint | Limit |
|---|---|
| Formats | MP4, MOV |
| Max dimensions | 3840 × 2160 px (4K) |
| Max file size | 5120 MB (5 GB) |
| Max duration | Not enforced by GaleFling |

### Text

| Constraint | Limit |
|---|---|
| Max length | 1000 characters |
| Text with media | Supported |

## Platform Behavior

- **API type**: `webview` — you confirm the post in the embedded browser panel.
- **Auth method**: `auth_id` session cookie in isolated WebView profile.
- **Session detection**: DOM-based (inline login form check), not URL redirect.
- **Cloudflare**: Pages load with a Cloudflare challenge. GaleFling waits 1500 ms before attempting to pre-fill the composer to allow Cloudflare and Vue.js to complete page hydration.
- **Success detection**: OnlyFans is a SPA; post URLs are not captured. "Posted (link unavailable)" is a normal, non-error result.

## Troubleshooting

| Problem | Solution |
|---|---|
| "Session expired" immediately after logging in | Cloudflare may be blocking the headless session check. Try posting directly and confirming in the WebView panel. |
| 2FA checkbox not clickable | GaleFling injects a fix for this automatically. If it still fails, try clicking the checkbox directly in the WebView panel. |
| Composer not found | The SPA may need more time to hydrate. Run on Windows for the best chance of full rendering. |
| `WV-SESSION-EXPIRED` in results | Session cookies expired. Log in again via Settings. |
| Cloudflare challenge loop | Clear the OnlyFans WebView profile (Settings > Accounts > OnlyFans > Clear Session) and log in again. |
