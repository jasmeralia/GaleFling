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

### Mixing images and video

Fansly's own composer accepts images and video in the same post. **GaleFling does not
offer this** — its composer treats a video as a sole attachment for every platform. That
is a product-level restriction rather than a Fansly limitation; see "Mixing images and
video in one post" in [PLATFORM_SPECS.md](PLATFORM_SPECS.md). The upload flow below is
driven once per post, so nothing here is currently exercised with more than one item.

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

GaleFling drives this flow from `BaseWebViewPlatform._do_prefill()` when a media path is
present. The callback sequence is bounded and aborts on the first failed or refused
step, with the reason recorded in the application log. It leaves the composer ready for
the user and never clicks **Post**.

Attaching media is a multi-step flow driven by Fansly's own UI, not a single file input:

1. Click the image icon in the composer's button row.
2. Choose **Upload New** from the dropdown that appears (its items exist in the DOM but are hidden until then).
3. The native file picker opens; `BaseWebViewPlatform`'s `chooseFiles()` override supplies the staged path.
4. An **Upload media** modal appears with the permission controls above.
5. Click **Upload** to confirm — only now does the media reach the composer.
6. Add the caption and post.

The shipped sequence dismisses the greeting overlay, fills the caption, stages the
file, opens the media dropdown, selects the exact **Upload New** leaf, waits for the
modal, applies the no-paywall permissions, clicks the enabled **Upload** control, waits
for the composer attachment, and finally waits for **Post** to lose its whole-token
`disabled` class. The last observation is readiness only; user confirmation remains
required.

Writing a file onto the input directly does not work, with either a synthetic `DataTransfer` or the picker: Fansly's uploader is never in the call stack, so the modal never opens and the composer stays empty. Posting anyway publishes the caption with **no media attached**.

### Driving the flow — verified selectors and quirks (2026-08-12)

Steps 1–4 above are confirmed working end to end against the live composer. The details are fiddly enough to be worth recording:

| Step | Target | Note |
|---|---|---|
| Open the menu | `div.dropdown-title` — the **parent** of `i.fa-image.hover-effect` | Clicking the `<i>` itself does nothing, despite it having `cursor: pointer` |
| Choose upload | the visible leaf whose text is exactly `Upload New` | Present in the DOM from page load but `visible: false` until the menu opens |
| Picker | fires `chooseFiles()`, `picker_invocations` goes to 1 | Only when Fansly opens it — not when we click the input |
| Modal | `Upload media`; buttons `Cancel` (`btn large margin-right-2`) and `Upload` (`btn solid-blue large`) | |

Two traps:

- **Fansly greets a session with a push-notification prompt.** `<app-web-push-enable-modal class="active-modal">` ("Enable Push Notifications"), with `div.xdModal.back-drop` behind it at 1270 × 900 — covering the entire composer, media icon and Post control alike. `document.elementFromPoint()` at the media icon's centre returns the backdrop, not the icon, and the **first click anywhere is absorbed dismissing it**. This costs the *user* a click too, not just automation.

  The dialog is a **sibling** of the backdrop, not a child: the backdrop element itself is empty, so anything that inspects the backdrop for the dialog's text or buttons finds nothing. Measured layout, both 282 px wide and stacked 41 px apart:

  | Control | Position |
  |---|---|
  | `Yes, Enable` (`btn outline-blue margin-top-3`) | x 494, y 513 |
  | `Maybe Later` (`btn margin-top-2`) | x 494, y 554 |

  Do not rely on an off-target click to clear it. `BaseWebViewPlatform.dismiss_blocking_overlay()` clears it explicitly, and the shipped load path calls it before prefill. Fansly declares both `BLOCKING_OVERLAY_SELECTOR` and `BLOCKING_OVERLAY_DISMISS_LABELS = ['Maybe Later']`; the dismissal prefers that named decline control and falls back to clicking the backdrop element itself when no declared label is on screen.

  **Match the decline label exactly** — the same rule as the media permission rows, and for the same reason. `Yes, Enable` sits directly above `Maybe Later`, so a keyword or substring match here enables push notifications on the account holder's behalf.

  Declining by name also appears to stick. The prompt returned on every subsequent session after a backdrop-only dismissal, but has not returned since one run clicked `Maybe Later` — so `TestFanslyGreetingPrompt` skips when no prompt is present rather than asserting one appears.
- **`fa-image` vs `fa-images`.** The composer's control is the singular `fa-image`; the surrounding feed is full of plural `fa-images` in the right-hand column. A substring match on `fa-image` hits both and lands you on a feed icon ~1000px away. Match the class as a whole token.

### The permission toggles are Angular components, not checkboxes

There is no `input[type="checkbox"]` anywhere in the modal. Each row is:

```html
<app-xd-checkbox class="margin-right-1">
  <div class="checkbox">                                    <!-- unchecked -->
  <div class="checkbox selected"><i class="fa-check">       <!-- checked -->
```

The checked state is the **`selected`** class on the inner `div.checkbox`. Confirmed live: of the four rows, only **Require Subscription** carries it by default.

`FanslyPlatform.apply_media_permissions()` implements the no-paywall policy against this structure. It matches each row by **exact label text**, clicks the `<app-xd-checkbox>` host only when the current state differs from the policy, touches only the rows named in `MEDIA_PERMISSION_POLICY` (so Advanced Permissions and Require Purchase are left as found), and reads the state back afterwards rather than assuming the clicks landed.

### The Post control is a `<div>`, and it is disabled while the upload finishes

The composer's submit is `<div class="btn new-post-btn solid-blue disabled">`. Nothing about a `<div>` stops a synthetic `.click()` being delivered, and `disabled` here is a **class**, not the DOM property — so clicking it while disabled succeeds, reports success, and publishes nothing. That is why media posts appeared to reach the Post click and then silently do nothing, while caption-only posts worked.

Measured live (2026-08-12), with the composer already holding the attachment:

| Moment | `disabled` | opacity |
|---|---|---|
| 2 s after the caption is injected — where the click used to happen | present | 0.6 |
| ~5 s later | gone | 1 |

`media-upload-container` gaining a child is therefore **not** the same as being ready to post: the attachment is visible while Fansly is still processing it. Wait for the `disabled` class to clear (`classList.contains`, a whole-token test — never a substring match) before clicking, and treat "control still disabled" as a refusal to click rather than a click that happened to do nothing.

**Video behaves the same.** A 2 s 320 × 240 MP4 cleared `disabled` after ~5 s — the same figure as a JPEG — so the wait is not proportional to clip length at this size. A large upload is unmeasured, and the functional test keeps generous ceilings for that reason.

### Video posts render as poster images in the feed

A published video post contains **no `<video>` element** until playback. Fansly renders it as a pair of `img.image` elements (one `cover`, one `contain`, both 754 × 566 for a 4:3 source). Anything asserting that a video post contains media must therefore accept `img`, or it will report "no media" on a perfectly good post. The corollary is that the feed offers no video-specific marker to distinguish a video post from an image post without playing it.
