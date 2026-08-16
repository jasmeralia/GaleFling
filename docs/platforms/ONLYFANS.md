# OnlyFans Setup Guide

> ## ⚠ OnlyFans support is disabled
>
> **OnlyFans is not currently available in GaleFling.** It does not appear in the setup
> wizard, in Settings, or as a post target. Nothing else is affected.
>
> **Why.** Paused 2026-08-16 at Rin's request. OnlyFans and Fansly are both aggressive
> about detecting and banning automation, and both support scheduled posts — a stronger
> automation signal than a one-off manual post — which would only increase that
> exposure. This is a risk decision, not a technical failure: unlike Snapchat, the
> session-import-and-post mechanism described below does actually work.
>
> **What was investigated.** GaleFling never offered embedded login for OnlyFans —
> its login form is gated by a bot check that rejects embedded browsers (see below) —
> so posting worked only via manual `auth.json` session import. A 2026-08 investigation
> explored whether that manual step could be automated by driving OnlyFans' login form
> with GaleFling's `trusted_click()` primitive (a synthesized `QMouseEvent`, added since
> the original login-removal decision). Findings:
>
> - **Works on Windows.** The exact same Qt WebEngine automation succeeded 3/3, zero
>   Cloudflare Turnstile challenges triggered.
> - **Fails on Linux**, both on bare-metal typhoon and in a throwaway VM with no GPU
>   passthrough (3/3 failures each) — Turnstile never completes, so the password step
>   is never reached. A real, human-driven Chrome browser succeeds on the same Linux
>   machine and network, which isolates the cause to Qt WebEngine's own behavior on
>   Linux specifically, not the OS, network, or automation-vs-human input in general.
> - **A fingerprint sweep found no simple spoofable cause.** Ruled out: Chromium
>   storage/privacy-sandbox flags, full `window.chrome`/plugin/mimetype spoofing,
>   presenting as Chrome-on-Windows via UA, `navigator.webdriver` (false on both
>   platforms), and WebGL/GPU fingerprint (bare metal reports a fully normal GPU
>   string via ANGLE and still fails). Re-enabling several Chromium features Qt
>   WebEngine disables by default that real Chrome leaves on (`WebPayments`, `WebUSB`,
>   `WebOTP`, `BackgroundFetch`, `InstalledApp`) also made no difference; one
>   (`WebAuthenticationConditionalUI`) could not be re-enabled via command-line flags
>   at all, suggesting it's hardcoded rather than a simple default.
> - A **browser-extension architecture** (drive the user's real, already-logged-in
>   Chrome/Edge instead of Qt WebEngine) was scoped as the structural fix, since it
>   sidesteps the fingerprint problem entirely by using a real browser. That work is
>   now moot given OnlyFans support itself is paused; see the closed Odoo tasks
>   referenced in `CHANGELOG.md` if this is ever revisited.
>
> **Status.** Paused rather than removed. The platform code, specs, and existing
> imported sessions are untouched; the functional tests are skipped (not run) rather
> than kept live, since continuing to exercise the platform automation carries exactly
> the automation-detection risk this pause is meant to avoid.

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
| Composer not found | The SPA may need more time to hydrate. Run on Windows for the best chance of full rendering. |
| `WV-SESSION-EXPIRED` in results | Session cookies expired. Export a fresh `auth.json` and re-import it via Settings. |
| Cloudflare challenge loop | Clear the OnlyFans WebView profile (Settings > Accounts > OnlyFans > Clear Session) and import a fresh session. |
