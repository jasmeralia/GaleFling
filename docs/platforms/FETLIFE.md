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
| Text with media | Supported — GaleFling fills `picture[caption]` or `video[description]` on the media composer. |

GaleFling still applies its single 690-character FetLife text limit to captions because
the status composer is the binding constraint; per-composer limits are not yet modeled.

## Platform Behavior

- **API type**: `webview` — you confirm the post in the embedded browser panel.
- **Auth method**: Session cookies in isolated WebView profile (cookie check only — no live probe).
- **Composer routing**: GaleFling navigates to a different URL depending on what is attached:
  - Text only → `fetlife.com/home` (the status composer on the feed)
  - Image → `fetlife.com/pictures/new`
  - Video → `fetlife.com/videos/new`
- **Text pre-fill**: Text posts are FetLife **statuses**, composed in the inline box on the feed (`textarea[name="body"]`, placeholder "What's on your kinky mind?", submit button **"Say It!"**). Pre-fill delay is 200 ms (fast — traditional MPA pages load quickly).

  > **Not `/posts/new`.** That is the *writing* composer, and its form requires a `post[title]` field GaleFling has no input for. Submitting from there fails validation silently and bounces back to the feed, creating nothing — which is exactly what a passing-but-useless functional test looked like before 2026-08-11. The Lexxy editor belongs to that writing composer, not to statuses.

- **Status length limit**: 690 characters — the limit FetLife displays in its own composer. It sets no `maxlength` on the textarea; the "Say It!" button simply disables past the cap (verified 2026-08-11: enabled at 690, disabled at 691). Because there is no `maxlength` to read, `FETLIFE_SPECS.max_text_length` cannot be checked against an attribute the way Fansly's is; `test_composer_cap_agrees_with_specs` probes the boundary instead, asserting the button is live at the cap and dead one character past it. GaleFling truncates to that number before posting, so a silent move in FetLife's cap would otherwise go unnoticed.
- **Recurring prompt**: If FetLife displays its post-login prompt again, GaleFling
  selects **Maybe Later** so the composer remains usable. The prompt is detected on
  every page load rather than assumed to be a one-time event.
- **Upload composers**: `pictures/new` has *two* file inputs — a hidden picker carrying the
  `accept` list (`#picture_attachments`) and the real `picture[attachments][]` field. FetLife
  moves the file between them asynchronously and clears the picker, so an attach cannot be
  verified by re-reading the input it was written to. `videos/new` has a single input
  (`#video_video`) and keeps the file. GaleFling stages the local path, uses a trusted click
  on the visible **Choose File** control, and polls the form until it retains the file.
  The `/pictures/new` and `/videos/new` picker paths were verified live through the
  shipped `_do_prefill()` entry point on 2026-08-12. Each produced one `chooseFiles()`
  call and retained the file in the correct form field without submitting.
- **Upload consent**: both upload forms require `picture[is_certified]` / `video[is_certified]`
  before they will submit. `FetLifePlatform._certify_upload_consent()` matches these by exact
  name — the picture form also carries `picture[is_avatar]`, which replaces the account avatar,
  so keyword matching over checkbox labels must never be used here.
- **Success detection**: FetLife permalinks are **username-scoped**: `fetlife.com/<username>/s/<id>` for a status, `/<username>/pictures/<id>` and `/<username>/videos/<id>` for media. The `users/<id>/...` form this originally expected does not occur in practice, so URL capture never matched any post until fixed. All forms are covered by `SUCCESS_URL_PATTERN`.
- **Media captions**: both media composers accept text — `picture[caption]` and
  `video[description]` — and the video form additionally requires a `video[title]`.
  `FETLIFE_SPECS.supports_text_with_media` is `True`. The media pre-fill sequence calls
  `_inject_media_caption()` after the picker selection is retained; `_inject_text()`
  remains explicitly status-only and is not used on `/pictures/new` or `/videos/new`.
- **User confirmation**: the sequence certifies the exact `picture[is_certified]` or
  `video[is_certified]` field, rechecks that `picture[is_avatar]` is off, and stops. It
  never clicks **Upload Your Picture** or **Upload Your Video**.

- **Caption length is *not* the 690-character status limit.** The 690 figure is the status composer's, which FetLife displays and enforces by disabling "Say It!". The media composers show no counter and enforce nothing visible. Measured 2026-08-12 by uploading a real picture with a **2536-character** caption: accepted, no truncation. So captions hold at least 3.7× the status cap.

  `FETLIFE_SPECS.max_text_length` stays at 690 regardless, because it is a single value applied to every FetLife post and the status composer is the binding constraint. The consequence is only that media captions are capped lower than FetLife would allow — a missed opportunity, not a defect, and the safe direction to err in. `test_picture_caption_capacity` / `test_video_caption_capacity` assert only that captions hold *at least* `max_text_length`, so they stay green on this finding and go red if FetLife ever tightens captions below the spec value. Raising `max_text_length` would need per-composer limits in `PlatformSpecs`, which nothing currently supports.
- **Video uploads are asynchronous and stay put**: clicking **Upload Your Video** does not navigate. FetLife transfers and transcodes in place on `/videos/new`, so the composer URL never changes — success can only be confirmed from `/<username>/videos`. Picture uploads do redirect to the new picture's permalink.

### What proves a media upload worked

A permalink is not proof, and neither is the caption. FetLife renders the caption from
the form field it was submitted with, so an upload that lost its attachment still
produces a page carrying the caption — and the picture composer redirects to *a*
permalink regardless. The functional tests therefore require all three: the permalink
pattern matched, the caption present on that page, and the page actually rendering
media that is not page furniture.

Filtering out the furniture is the fiddly part. FetLife puts the author's avatar inside
the same container as the upload, and it is the *first* image found by anything walking
the DOM looking for one — so an unfiltered check reports success on a post whose picture
silently dropped. Avatars are excluded by class, by container, and by size (≤ 120 px
square); the matched media's real dimensions are printed on every run so a suspicious
pass can be spotted rather than trusted. This mirrors the rule Fansly arrived at the
hard way — see [FANSLY.md](FANSLY.md) → "Video posts render as poster images in the feed".

Note the corollary for video: a gallery entry renders as a poster thumbnail, so what is
actually verified is that *media* landed, not that it is a video. There is no
video-specific marker without playing it.

### Post Cleanup Note

Statuses are posted in place on the feed rather than navigating to the new status, so functional tests confirm success by finding the status's tag on the feed.

Automated status deletion needs **real mouse events**, not a scripted `.click()`. The
Delete entry is an `<a href="#0">` whose only payload is a `data` attribute that
stringifies to `[object Object]` — no `data-method`, no `data-turbo-confirm`, no delete
endpoint. Its handler is bound in JavaScript, so a synthetic click never reaches it and
no confirmation is raised. The status test *attempts* to open the overflow menu and
click Delete with a trusted mouse event at the measured coordinates, then confirm by
reloading the feed — a clicked control is never treated as a successful deletion.

**Verified working end to end against a live status, 2026-08-12** — deletion confirmed
by the status leaving the feed *and* by its permalink no longer resolving. Getting there
took two fixes, both worth knowing because they are the shape of trap this page keeps
producing:

- **The overflow control is icon-only.** It is `<a href="#0" title="More options">`
  wrapping an `<svg>`, with **empty `textContent`** — the label lives in the `title`
  attribute. Matching on text found nothing, so the delete never started. The article
  also contains **no `<button>` at all**; every control is an `<a>`, which is why a
  "last visible button" fallback found nothing either. That fallback was removed rather
  than repaired: had it matched, the article's other controls are Bookmark and Share.
- **The confirmation dialog was being looked for in the wrong element.** The old shared
  snippet scoped with `[role="dialog"], .modal, dialog[open], …` and applied no
  visibility test, so it selected the account sidebar — an invisible
  `<aside role="dialog">` earlier in document order — and reported
  `{confirmed: false, scoped: true}`. That reads as "the dialog had no confirm button"
  rather than "we searched the wrong element". Scope to a **visible** modal footer.

The real dialog is `footer.qa-modal-footer` containing `Cancel` and
`Delete Status Update`, **both `<button type="submit">`** — the type carries no signal,
so the label is the only discriminator, and Cancel is excluded by name as well as by
requiring the affirmative prefix.

**Cleanup is still mostly manual, so check your accounts after a mutating run.** Only
the FetLife status test deletes. The FetLife picture and video tests and all three
Fansly tests delete nothing and print `CLEANUP PENDING` with the tag. Whether Fansly's
delete control can be automated is entirely unexplored.

Generalising this — an opt-in cleanup pass, plus printing the artifact URL alongside the
tag — is Odoo task 420. It is deliberately opt-in rather than automatic: rule 9 in
`AGENTS.md` requires a live artifact to outlive inspection, and a test that deletes on
success destroys the evidence needed to confirm a rewritten assertion.

## Troubleshooting

| Problem | Solution |
|---|---|
| "Session expired" on launch | Log in again via Settings > Accounts > FetLife. |
| Text not pre-filled | Ensure the composer has fully loaded before GaleFling injects text. FetLife loads fast, but network latency can occasionally delay page render. |
| `WV-SESSION-EXPIRED` in results | Session cookies expired. Log in again via Settings. |
| Post goes to wrong composer | GaleFling routes based on attached media type. Detach media to get the text composer, or attach the correct media type. |
| Post submitted but no URL captured | Statuses post in place on the feed rather than navigating to a permalink. Confirm the status actually appears on the feed — a bounce back to the feed is also what a *rejected* submit looks like, so a URL alone never proves a post was created. |
