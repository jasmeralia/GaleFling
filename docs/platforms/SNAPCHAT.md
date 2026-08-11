# Snapchat Setup Guide

> ## ⚠ Snapchat support is disabled
>
> **Snapchat is not currently available in GaleFling.** It does not appear in the setup
> wizard, in Settings, or as a post target. Nothing else is affected.
>
> **Why.** Snapchat's web app has no upload control. Verified 2026-08-11 against a live
> authenticated session: zero `input[type=file]` elements, zero `<canvas>`, and no
> link, button or label offering camera, story, create, post, upload, capture or
> record. What the web app serves is a chat client.
>
> Posting is possible there, but only interactively: the interface invites you to
> "click on the camera to send snaps", which activates an in-page camera you use to
> take a photo or record a video, optionally apply filters, and send. There is no file
> picker anywhere in that flow.
>
> **Why that is hard to automate.** GaleFling would have to attach a virtual camera
> device to the browser and play media into it as a live stream, then drive the capture
> UI. That means a platform-specific virtual camera (a kernel module on Linux, a signed
> driver on Windows) as a user-facing dependency; capture that runs in real time, so a
> 60-second video takes 60 seconds to "record"; and synthetic interaction with a camera
> UI, which is close to the shape of automation that platforms actively detect. It is
> likely technically possible and definitely not cheap.
>
> **Status.** Paused rather than removed. The platform code, specs and tests remain in
> place, and an existing Snapchat session is untouched. A future spike may revisit the
> virtual-camera approach; see `docs/testing/WEBVIEW_TEST_PLAN.md` for the evidence.

GaleFling posts to Snapchat via an embedded WebView at `web.snapchat.com`. This is the Snapchat **web app** — a different interface from the mobile app, with different capabilities.

## Account Type

Any Snapchat account that can access the web app works. GaleFling supports **up to 2 Snapchat accounts**.

## Credential Setup

Snapchat uses session cookies stored in a persistent WebView profile. There are no API keys to enter.

### Step 1: Log In via GaleFling

1. Open GaleFling and go to **Settings > Accounts > Snapchat**.
2. Click **Log In**. An embedded browser opens `web.snapchat.com`.
3. Complete the Snapchat login flow in the embedded browser (email/password + any 2FA).
4. Once the Snapchat web app loads, GaleFling detects the session and closes the login window.

Your session cookies are stored in an isolated profile directory under `%APPDATA%\GaleFling\webprofiles\snapchat_1\`.

### Session Expiry

Snapchat web sessions expire periodically. When your session expires, GaleFling will show a "session expired" warning. Repeat Step 1 to re-establish the session.

### Adding a Second Account

GaleFling supports up to 2 Snapchat accounts. To add a second account:

1. Go to **Settings > Accounts > Snapchat > Add Account**.
2. Log in with the second Snapchat account in the embedded browser.

Each account uses a separate profile directory (`snapchat_1`, `snapchat_2`) so sessions never interfere.

## Media Restrictions

### Images

Snapchat's web app is **video-oriented**. Native image posting is not supported on the web path. When you attach a single static image, GaleFling automatically converts it to a short MP4 video before sending it to Snapchat.

### Videos

| Constraint | Limit |
|---|---|
| Format | MP4 |
| Max dimensions | 1080 × 1920 px (portrait) |
| Max file size | 50 MB |
| Max duration | 60 seconds |

### Text

Snapchat's web story composer **does not support text captions**. Any text entered in the GaleFling composer is ignored for Snapchat. GaleFling shows a warning in the composer when Snapchat is selected with text content.

### Multiple Images

Multiple image attachments are not supported for Snapchat on the web path. Snapchat will be disabled in the platform selector if more than one image is attached.

## Platform Behavior

- **API type**: `webview` — you confirm the post in the embedded browser panel.
- **Auth method**: Session cookies in isolated WebView profile.
- **Success detection**: Snapchat is a SPA (single-page app); post URLs are not captured. "Posted (link unavailable)" is a normal, non-error result.
- **WebGL requirement**: Snapchat's web app requires WebGL with a real GPU. **Windows native is required.** WSL, offscreen mode, and most virtual display setups will fail with JS errors.

### Renderer Crash Workaround

Navigating to `www.snapchat.com/web` (the marketing landing page) with Snapchat cookies present causes a GPU renderer crash in Qt's Chromium. GaleFling intercepts this redirect:

- On initial session expiry: navigates directly to the Snapchat SSO login page, bypassing the crash-prone marketing page.
- After a successful login on `accounts.snapchat.com`: navigates directly to `web.snapchat.com` (the app), skipping the marketing page on the return redirect.

## Troubleshooting

| Problem | Solution |
|---|---|
| "Session expired" on launch | Log in again via Settings > Accounts > Snapchat. |
| Composer loads but JS errors appear | Snapchat requires WebGL. Run on native Windows. |
| Black screen in WebView | GPU rendering issue; ensure you are on native Windows, not WSL or offscreen mode. |
| Image post not working | Single images are auto-converted to MP4. Multiple images are not supported. |
| `WV-SESSION-EXPIRED` in results | Session cookies expired. Log in again via Settings. |
