# OnlyFans Setup Guide

GaleFling posts to OnlyFans via an embedded WebView at `onlyfans.com`. OnlyFans is protected by Cloudflare, which adds latency to page loads and session detection.

## Account Type

Any OnlyFans creator account works. GaleFling supports **1 OnlyFans account**.

## Credential Setup

OnlyFans uses session cookies stored in a persistent WebView profile. There are no API keys to enter.

### Import a session from your browser

**GaleFling cannot log you in to OnlyFans directly.** OnlyFans gates its login form with
reCAPTCHA Enterprise, which rejects embedded browsers regardless of whether the credentials
are correct — so GaleFling does not offer a login window for OnlyFans at all.

Instead, log in with your normal browser, export the session to an `auth.json` file, and
import it from **Settings > OnlyFans > Import Session from auth.json**.

See **[ONLYFANS_SESSION_IMPORT.md](ONLYFANS_SESSION_IMPORT.md)** for the full procedure.

Once imported, posting works exactly as before — OnlyFans' own site composes and publishes
the post inside GaleFling. Your session is stored in an isolated profile directory under
`%APPDATA%\GaleFling\webprofiles\onlyfans_1\`.

### Checkbox Fix

OnlyFans renders checkboxes using Vue.js custom components whose decorator elements can
absorb clicks before they reach the underlying input. GaleFling injects a script that
restores pointer events and forwards clicks on these components, so checkboxes in the
composer behave normally.

### Session Expiry

OnlyFans sessions expire periodically. Unlike most platforms, OnlyFans does **not redirect to a login URL** when the session expires — it renders an inline login form at the same URL. GaleFling detects this by checking the DOM for login form selectors (`.b-loginreg__form`, `input[type="password"]`).

When your session expires, GaleFling will show a "session expired" warning. Export a fresh
`auth.json` from your browser and re-import it to re-establish the session.

GaleFling verifies an import against Chromium's live cookie store, while its "session valid"
check reads Chromium's on-disk cookie database, which is only written every 30 seconds or so.
A freshly imported session is treated as valid during that gap, so a successful import does
not report itself as expired.

## Media Restrictions

The maximum file sizes below are GaleFling-imposed limits, not values published by OnlyFans.

### Images

| Constraint | Limit |
|---|---|
| Formats | JPEG, PNG, GIF |
| Max dimensions | 10000 × 10000 px |
| Max file size | 50 MB |
| Max attachments | 40 images per post |

### Videos

| Constraint | Limit |
|---|---|
| Formats | MP4, MOV, M4V, MPEG, WMV, AVI, WEBM, MKV |
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
| "Session expired" right after a successful import | Should not happen — a fresh import is trusted while Chromium writes its cookie database. If it does, the import did not complete; check for an error message and import again. |
| Import reports the cookies were rejected | The `auth.json` is malformed or was edited by hand. Export a fresh one. |
| Import succeeds but OnlyFans still shows a login form | The exported session is no longer valid. Log out and back in with your browser — re-exporting without a fresh login reuses the same dead session — then export and import again. |
| No login button on the OnlyFans tab | Intentional. OnlyFans rejects embedded-browser logins, so sessions must be imported. |
| Checkbox not clickable | GaleFling injects a fix for this automatically. If it still fails, try clicking the checkbox directly in the WebView panel. |
| Composer not found | The SPA may need more time to hydrate. Run on Windows for the best chance of full rendering. |
| `WV-SESSION-EXPIRED` in results | Session cookies expired. Export a fresh `auth.json` and re-import it via Settings. |
| Cloudflare challenge loop | Clear the OnlyFans WebView profile (Settings > Accounts > OnlyFans > Clear Session) and import a fresh session. |
