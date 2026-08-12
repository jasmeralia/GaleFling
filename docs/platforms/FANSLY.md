# Fansly Setup Guide

GaleFling posts to Fansly via an embedded WebView at `fansly.com`. Fansly is protected by Cloudflare, which uses CloudFront-signed cookies alongside the primary session cookie.

## Account Type

Any Fansly creator account works. GaleFling supports **1 Fansly account**.

## Credential Setup

Fansly uses session cookies stored in a persistent WebView profile. There are no API keys to enter.

### Step 1: Log In via GaleFling

1. Open GaleFling and go to **Settings > Accounts > Fansly**.
2. Click **Log In**. An embedded browser opens `fansly.com`.
3. Complete the Fansly login flow (email/password + any 2FA).
4. Once the Fansly home page loads, GaleFling detects the session and closes the login window.

Your session cookies are stored in an isolated profile directory under `%APPDATA%\GaleFling\webprofiles\fansly_1\`.

### Session Cookies

GaleFling validates session by checking for all of the following cookies:

| Cookie | Purpose |
|---|---|
| `fansly-d` | Primary Fansly session |
| `CloudFront-Key-Pair-Id` | CloudFront CDN auth |
| `CloudFront-Policy` | CloudFront CDN auth |
| `CloudFront-Signature` | CloudFront CDN auth |

All four must be present for the session to be considered valid. If any are missing, GaleFling will report the session as expired.

### Session Expiry

Fansly sessions expire periodically. When your session expires, GaleFling will show a "session expired" warning. Repeat Step 1 to re-establish the session.

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
| Max length | 3000 characters |
| Text with media | Supported |

## Platform Behavior

- **API type**: `webview` — you confirm the post in the embedded browser panel.
- **Auth method**: `fansly-d` + CloudFront session cookies in isolated WebView profile.
- **Composer route**: Authenticated composer sessions open at `fansly.com/home`. The
  public landing page remains at `/`, so GaleFling also checks the logged-out
  navigation shell instead of treating a non-redirecting `/` response as authenticated.
- **Cloudflare**: Pages load with a Cloudflare challenge. GaleFling waits 1500 ms before attempting to pre-fill the text composer (`textarea`) to allow Cloudflare and the SPA to complete page hydration.
- **Success detection**: Fansly is a SPA; post URLs are not captured. "Posted (link unavailable)" is a normal, non-error result.

## Troubleshooting

| Problem | Solution |
|---|---|
| "Session expired" on launch | One or more required cookies (including CloudFront cookies) are missing. Log in again via Settings. |
| Text not pre-filled | Cloudflare challenge may still be running. Wait for the page to fully load, then retry or type manually in the WebView panel. |
| `WV-SESSION-EXPIRED` in results | Session cookies expired. Log in again via Settings. |
| Cloudflare challenge loop | Clear the Fansly WebView profile (Settings > Accounts > Fansly > Clear Session) and log in again. |

## Media permissions — no paywall

Fansly's **Upload media** modal opens with **Require Subscription checked** ("Any Tier"). GaleFling must clear it and check **Require Follow** instead; Advanced Permissions and Require Purchase stay unchecked. See the "Posts are never paywalled" convention in `AGENTS.md`.

Target these by exact field name. The modal is a permissions block, so a keyword match over labels risks toggling a monetization control — the same hazard as FetLife's `picture[is_avatar]`.

## Media upload flow

Attaching media is a multi-step flow driven by Fansly's own UI, not a single file input:

1. Click the image icon in the composer's button row.
2. Choose **Upload New** from the dropdown that appears (its items exist in the DOM but are hidden until then).
3. The native file picker opens; `BaseWebViewPlatform`'s `chooseFiles()` override supplies the staged path.
4. An **Upload media** modal appears with the permission controls above.
5. Click **Upload** to confirm — only now does the media reach the composer.
6. Add the caption and post.

Writing a file onto the input directly does not work, with either a synthetic `DataTransfer` or the picker: Fansly's uploader is never in the call stack, so the modal never opens and the composer stays empty. Posting anyway publishes the caption with **no media attached**.
