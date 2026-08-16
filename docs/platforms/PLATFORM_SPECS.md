# Platform Specs

Quick reference for all platform limits and capabilities. For credential setup and detailed behavior, see the individual platform docs.

## Platform Docs

| Platform | Doc | Type |
|---|---|---|
| Bluesky | [BLUESKY.md](BLUESKY.md) | API |
| Twitter | [TWITTER.md](TWITTER.md) | API |
| Instagram | [INSTAGRAM.md](INSTAGRAM.md) | API |
| Threads | [THREADS.md](THREADS.md) | API |
| Facebook | [FACEBOOK.md](FACEBOOK.md) | API |
| Snapchat | [SNAPCHAT.md](SNAPCHAT.md) | WebView — **disabled**, see below |
| OnlyFans | [ONLYFANS.md](ONLYFANS.md) | WebView — **disabled**, see below |
| Fansly | [FANSLY.md](FANSLY.md) | WebView — **disabled**, see below |
| FetLife | [FETLIFE.md](FETLIFE.md) | WebView |

## Source of Truth

Platform limits and capabilities are defined in `src/utils/constants.py` (`PlatformSpecs` + `PLATFORM_SPECS_MAP`). The tables below are derived from that file.

> **Snapchat is disabled** (`available=False`) and does not appear in the setup wizard, Settings, or the post composer. Its web app offers no upload control — posting there requires an interactive in-page camera GaleFling cannot drive. Its limits remain listed below for reference and are unchanged. See [SNAPCHAT.md](SNAPCHAT.md).
>
> **OnlyFans and Fansly are disabled** (`available=False`) and do not appear in the setup wizard, Settings, or the post composer. Unlike Snapchat, this isn't a capability gap — both work technically. They're paused at Rin's request (2026-08-16) because both platforms are aggressive about detecting and banning automation, and both support post scheduling, a stronger automation signal than a one-off manual post. Their limits remain listed below for reference and are unchanged. See [ONLYFANS.md](ONLYFANS.md) and [FANSLY.md](FANSLY.md).

## Account Limits

| Platform | Max Accounts | Auth Type |
|---|---|---|
| Twitter | 2 | OAuth 1.0a (PIN flow) |
| Bluesky | 2 | App password |
| Instagram | 2 | Graph API OAuth2 |
| Threads | 2 | Threads OAuth2 (API) |
| Facebook | 1 | Facebook Login for Business OAuth2 (API) |
| Snapchat | 2 | Session cookie (WebView) |
| OnlyFans | 1 | Session cookie (WebView) |
| Fansly | 1 | Session cookie (WebView) |
| FetLife | 1 | Session cookie (WebView) |

## Image Limits

| Platform | Max Dimensions | Max Size | Formats | Max Attachments |
|---|---|---|---|---|
| Twitter | 4096 × 4096 | 5 MB | JPEG, PNG, GIF, WEBP | 4 |
| Bluesky | 2000 × 2000 | 1 MB | JPEG, PNG | 4 |
| Instagram | 1440 × 1440 | 8 MB | JPEG, PNG | 1 |
| Threads | 1440 × 1440 | 8 MB | JPEG, PNG | 10 |
| Facebook | 4096 × 4096 | 10 MB | JPEG, PNG | 1 |
| Snapchat | — | — | — | — (video only) |
| OnlyFans | 10000 × 10000 | 50 MB | JPEG, PNG, GIF | 40 |
| Fansly | 4096 × 4096 | 50 MB | JPEG, PNG, WEBP | 4 |
| FetLife | 4096 × 4096 | 20 MB | JPEG, PNG | 1 |

## Video Limits

| Platform | Format | Max Dimensions | Max Size | Max Duration |
|---|---|---|---|---|
| Twitter | MP4 | 1920 × 1200 | 512 MB | 140 s |
| Bluesky | MP4 | 1920 × 1080 | 50 MB | 60 s |
| Instagram | MP4 | 1920 × 1080 | 100 MB | 60 s |
| Threads | MP4, MOV | 1920 × 1080 | 1 GB | 300 s |
| Facebook | MP4, MOV | 1920 × 1080 | 10 GB | — |
| Snapchat | MP4 | 1080 × 1920 | 50 MB | 60 s |
| OnlyFans | MP4, MOV, M4V, MPEG, WMV, AVI, WEBM, MKV | 3840 × 2160 | 5120 MB | — |
| Fansly | MP4, MOV | 3840 × 2160 | 5120 MB | — |
| FetLife | MP4 | 1920 × 1080 | 500 MB | — |

## Text Limits

| Platform | Max Length | Text with Media | Notes |
|---|---|---|---|
| Twitter | 280 chars | Yes | — |
| Bluesky | 300 chars | Yes | URLs auto-linked via facets |
| Instagram | 2200 chars | Yes | — |
| Threads | 500 chars | Yes | — |
| Facebook | 63,206 chars | Yes | — |
| Snapchat | — | No | Text not supported on web composer |
| OnlyFans | 1000 chars | Yes | — |
| Fansly | 3000 chars | Yes | — |
| FetLife | Unlimited | No | Separate composers for text vs media |

## Behavioral Flags

| Platform | User Confirm | URL Capture | Cloudflare | Requires GPU |
|---|---|---|---|---|
| Twitter | No | Yes | No | No |
| Bluesky | No | Yes | No | No |
| Instagram | No | Yes | No | No |
| Threads | No | Yes | No | No |
| Facebook | No | Yes | No | No |
| Snapchat | Yes | No (SPA) | No | **Yes (WebGL)** |
| OnlyFans | Yes | No (SPA) | Yes | No |
| Fansly | Yes | No (SPA) | Yes | No |
| FetLife | Yes | Yes | Yes (cookie-only check) | No |

## Mixing images and video in one post

Several platforms accept a single post containing **both** images and video — Instagram
and Threads carousels do, and so does Fansly's composer. The `Max Attachments` column
above counts images only and says nothing about mixing; do not read it as evidence that
a platform cannot mix media.

**GaleFling does not offer mixed posts.** A video is always a sole attachment:

| Layer | Behavior |
|---|---|
| Composer UI (`post_composer.py::_choose_media`) | Once a video is attached, **Add Media** is disabled. With images already attached, the file dialog offers image formats only, and a video selected alongside them is skipped. |
| Platform gating (`main_window.py::_apply_count_restriction`) | With any video present, the per-post cap drops to 1 for every platform regardless of its own `max_media_attachments`. |
| Platform adapters | Unrestricted — `MetaInstagramPlatform.post()` and `MetaThreadsPlatform.post()` accept `media_paths=[image, video]` and publish a mixed carousel. |

This is a deliberate product restriction, not a platform limitation, and the two halves
disagree on purpose: the adapters can do more than the UI exposes. The functional suite
covers the mixed carousel by calling `post()` directly (`test_carousel_image_and_video`
for Instagram and Threads), which is the only way to reach that path — the GUI will not
produce such a selection. If mixed posts are ever offered to users, the restriction to
lift is in the composer, and the adapters for other platforms would need their own
mixed-media handling before that would be safe.

## Key Capability Flags in Code

`PlatformSpecs` fields used by UI and processing logic:
- `supported_formats`, `max_image_dimensions`, `max_file_size_mb` — image constraints
- `supported_video_formats`, `max_video_dimensions`, `max_video_file_size_mb`, `max_video_duration_seconds` — video constraints
- `max_text_length`, `supports_text`, `supports_text_with_media` — text behavior
- `api_type`, `requires_user_confirm` — posting model
- `max_media_attachments` — attachment cap, counting images (see "Mixing images and video" above — a video being a sole attachment is GaleFling's rule, not the platform's)

The specs objects for Threads and Facebook are `META_THREADS_API_SPECS` and
`META_FACEBOOK_PAGE_SPECS` in `src/utils/constants.py`, registered under the
`meta_threads` and `meta_facebook_page` keys in `PLATFORM_SPECS_MAP`.

## Behavior Notes

- Platform restrictions are enforced dynamically in the composer and selector.
- Unsupported static image formats may be auto-converted (e.g. WEBP → JPEG for Bluesky).
- Single static images attached for Snapchat are auto-converted to MP4 (video-only web path).
- Threads and Instagram (API path) require media to be staged to S3 before the publish
  API call. This is handled transparently by GaleFling's `MediaStager` component.
- Facebook Page posting uses the Facebook Pages API and does not require S3 staging,
  though GaleFling may route media through S3 for implementation consistency.
