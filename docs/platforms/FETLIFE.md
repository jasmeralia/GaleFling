# FetLife Setup Guide

GaleFling posts to FetLife via an embedded WebView. FetLife uses traditional server-rendered pages (not a SPA), which means page loads are fast and text pre-fill is reliable.

## Account Type

Any FetLife account works. GaleFling supports **1 FetLife account**.

## Credential Setup

FetLife uses session cookies stored in a persistent WebView profile. There are no API keys to enter.

### Step 1: Log In via GaleFling

1. Open GaleFling and go to **Settings > Accounts > FetLife**.
2. Click **Log In**. An embedded browser opens `fetlife.com/login`.
3. Complete the FetLife login flow (email/password).
4. Once the FetLife home page loads, GaleFling detects the session and closes the login window.

Your session cookies are stored in an isolated profile directory under `%APPDATA%\GaleFling\webprofiles\fetlife_1\`.

### Session Cookies

GaleFling validates session by checking for any of the following cookies:

| Cookie | Notes |
|---|---|
| `_fl_sessionid` | Primary session cookie |
| `remember_user_token` | Persistent "remember me" token |
| `_fl_session_remember_me` | Persistent session flag |

At least one of these must be present and valid for the session to be considered active.

### Session Expiry and Cloudflare

FetLife is protected by Cloudflare. The **headless** connection test (used to verify the session on a background QWebEnginePage) produces fingerprinting data that Cloudflare rejects — it redirects to `/login` even with valid cookies. GaleFling skips the live connection test for FetLife and relies entirely on the cookie-based check, which is accurate.

### Session Expiry

FetLife sessions expire periodically (especially without "remember me"). When your session expires, GaleFling will show a "session expired" warning. Repeat Step 1 to re-establish the session.

## Media Restrictions

### Images

| Constraint | Limit |
|---|---|
| Formats | JPEG, PNG |
| Max dimensions | 4096 × 4096 px |
| Max file size | 20 MB |
| Max attachments | 1 image per post |

### Videos

| Constraint | Limit |
|---|---|
| Format | MP4 |
| Max dimensions | 1920 × 1080 px |
| Max file size | 500 MB |
| Max duration | Not enforced by GaleFling |

### Text

| Constraint | Limit |
|---|---|
| Max length | Unlimited |
| Text-only posts | Supported |
| Text with media | **Not supported** — FetLife uses separate composers for text, image, and video posts. When media is attached, text is ignored. |

> GaleFling shows a warning in the composer when Fetslife is selected with both media and text, since the platform does not support captions on media posts.

## Platform Behavior

- **API type**: `webview` — you confirm the post in the embedded browser panel.
- **Auth method**: Session cookies in isolated WebView profile (cookie check only — no live probe).
- **Composer routing**: GaleFling navigates to a different URL depending on what is attached:
  - Text only → `fetlife.com/home` (the status composer on the feed)
  - Image → `fetlife.com/pictures/new`
  - Video → `fetlife.com/videos/new`
- **Text pre-fill**: Text posts are FetLife **statuses**, composed in the inline box on the feed (`textarea[name="body"]`, placeholder "What's on your kinky mind?", submit button **"Say It!"**). Pre-fill delay is 200 ms (fast — traditional MPA pages load quickly).

  > **Not `/posts/new`.** That is the *writing* composer, and its form requires a `post[title]` field GaleFling has no input for. Submitting from there fails validation silently and bounces back to the feed, creating nothing — which is exactly what a passing-but-useless functional test looked like before 2026-08-11. The Lexxy editor belongs to that writing composer, not to statuses.

- **Status length limit**: 690 characters — the limit FetLife displays in its own composer. It sets no `maxlength` on the textarea; the "Say It!" button simply disables past the cap (verified 2026-08-11: enabled at 690, disabled at 691).
- **Recurring prompt**: If FetLife displays its post-login prompt again, GaleFling
  selects **Maybe Later** so the composer remains usable. The prompt is detected on
  every page load rather than assumed to be a one-time event.
- **Upload composers**: `pictures/new` has *two* file inputs — a hidden picker carrying the
  `accept` list (`#picture_attachments`) and the real `picture[attachments][]` field. FetLife
  moves the file between them asynchronously and clears the picker, so an attach cannot be
  verified by re-reading the input it was written to. `videos/new` has a single input
  (`#video_video`) and keeps the file.
- **Upload consent**: both upload forms require `picture[is_certified]` / `video[is_certified]`
  before they will submit. `FetLifePlatform._certify_upload_consent()` matches these by exact
  name — the picture form also carries `picture[is_avatar]`, which replaces the account avatar,
  so keyword matching over checkbox labels must never be used here.
- **Success detection**: FetLife supports URL capture. Status permalinks use `fetlife.com/<username>/s/<id>` (e.g. `/Jasmeralia/s/11543410072`) — **not** `users/<id>/statuses/<id>`. Media posts use `fetlife.com/(users/<id>/)?(posts|pictures|videos)/<id>`. All forms are covered by `SUCCESS_URL_PATTERN`.

### Post Cleanup Note

Statuses are posted in place on the feed rather than navigating to the new status, so functional tests confirm success by finding the status's tag on the feed. Automated deletion of a status is best-effort and currently unproven — check your feed for the tag printed by the test run.

## Troubleshooting

| Problem | Solution |
|---|---|
| "Session expired" on launch | Log in again via Settings > Accounts > FetLife. |
| Text not pre-filled | Ensure the composer has fully loaded before GaleFling injects text. FetLife loads fast, but network latency can occasionally delay page render. |
| `WV-SESSION-EXPIRED` in results | Session cookies expired. Log in again via Settings. |
| Post goes to wrong composer | GaleFling routes based on attached media type. Detach media to get the text composer, or attach the correct media type. |
| Post submitted but no URL captured | Statuses post in place on the feed rather than navigating to a permalink. Confirm the status actually appears on the feed — a bounce back to the feed is also what a *rejected* submit looks like, so a URL alone never proves a post was created. |
