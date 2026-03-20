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
  - Text only → `fetlife.com/posts/new`
  - Image → `fetlife.com/pictures/new`
  - Video → `fetlife.com/videos/new`
- **Text pre-fill**: Uses a ProseMirror / Tiptap editor (`div.tiptap.ProseMirror[contenteditable="true"]`). Pre-fill delay is 200 ms (fast — traditional MPA pages load quickly).
- **Success detection**: FetLife supports URL capture. Post URLs match the pattern `fetlife.com/users/<id>/(statuses|posts|pictures|videos)/<id>`.

### Post Cleanup Note

FetLife redirects to `/posts` (the feed) after a text post is submitted, rather than to the individual post page. This means manual cleanup of test posts may be needed — search your FetLife feed for any test content.

## Troubleshooting

| Problem | Solution |
|---|---|
| "Session expired" on launch | Log in again via Settings > Accounts > FetLife. |
| Text not pre-filled | Ensure the composer has fully loaded before GaleFling injects text. FetLife loads fast, but network latency can occasionally delay page render. |
| `WV-SESSION-EXPIRED` in results | Session cookies expired. Log in again via Settings. |
| Post goes to wrong composer | GaleFling routes based on attached media type. Detach media to get the text composer, or attach the correct media type. |
| Post submitted but no URL captured | Text posts redirect to the feed (`/posts`) rather than the new post. This is a FetLife behavior, not a GaleFling bug. The post was still submitted. |
