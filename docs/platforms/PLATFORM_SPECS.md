# Platform Specs

Quick reference for all platform limits and capabilities. For credential setup and detailed behavior, see the individual platform docs.

## Platform Docs

| Platform | Doc | Type |
|---|---|---|
| Bluesky | [BLUESKY.md](BLUESKY.md) | API |
| Twitter / X | [TWITTER.md](TWITTER.md) | API |
| Instagram | [INSTAGRAM.md](INSTAGRAM.md) | API |
| Snapchat | [SNAPCHAT.md](SNAPCHAT.md) | WebView |
| OnlyFans | [ONLYFANS.md](ONLYFANS.md) | WebView |
| Fansly | [FANSLY.md](FANSLY.md) | WebView |
| FetLife | [FETLIFE.md](FETLIFE.md) | WebView |
| Threads | [THREADS.md](THREADS.md) | WebView |

## Source of Truth

Platform limits and capabilities are defined in `src/utils/constants.py` (`PlatformSpecs` + `PLATFORM_SPECS_MAP`). The tables below are derived from that file.

## Account Limits

| Platform | Max Accounts | Auth Type |
|---|---|---|
| Twitter | 2 | OAuth 1.0a (PIN flow) |
| Bluesky | 2 | App password |
| Instagram | 2 | Graph API OAuth2 |
| Snapchat | 2 | Session cookie (WebView) |
| OnlyFans | 1 | Session cookie (WebView) |
| Fansly | 1 | Session cookie (WebView) |
| FetLife | 1 | Session cookie (WebView) |
| Threads | 2 | Session cookie (WebView) |

## Image Limits

| Platform | Max Dimensions | Max Size | Formats | Max Attachments |
|---|---|---|---|---|
| Twitter | 4096 × 4096 | 5 MB | JPEG, PNG, GIF, WEBP | 4 |
| Bluesky | 2000 × 2000 | 1 MB | JPEG, PNG | 4 |
| Instagram | 1440 × 1440 | 8 MB | JPEG, PNG | 1 |
| Snapchat | — | — | — | — (video only) |
| OnlyFans | 4096 × 4096 | 50 MB | JPEG, PNG, WEBP | 4 |
| Fansly | 4096 × 4096 | 50 MB | JPEG, PNG, WEBP | 4 |
| FetLife | 4096 × 4096 | 20 MB | JPEG, PNG | 1 |
| Threads | 1440 × 1440 | 10 MB | JPEG, PNG, GIF | 10 |

## Video Limits

| Platform | Format | Max Dimensions | Max Size | Max Duration |
|---|---|---|---|---|
| Twitter | MP4 | 1920 × 1200 | 512 MB | 140 s |
| Bluesky | MP4 | 1920 × 1080 | 50 MB | 60 s |
| Instagram | MP4 | 1920 × 1080 | 100 MB | 60 s |
| Snapchat | MP4 | 1080 × 1920 | 50 MB | 60 s |
| OnlyFans | MP4, MOV | 3840 × 2160 | 5120 MB | — |
| Fansly | MP4, MOV | 3840 × 2160 | 5120 MB | — |
| FetLife | MP4 | 1920 × 1080 | 500 MB | — |
| Threads | MP4 | 1920 × 1080 | 1024 MB | 300 s |

## Text Limits

| Platform | Max Length | Text with Media | Notes |
|---|---|---|---|
| Twitter | 280 chars | Yes | — |
| Bluesky | 300 chars | Yes | URLs auto-linked via facets |
| Instagram | 2200 chars | Yes | — |
| Snapchat | — | No | Text not supported on web composer |
| OnlyFans | 1000 chars | Yes | — |
| Fansly | 3000 chars | Yes | — |
| FetLife | Unlimited | No | Separate composers for text vs media |
| Threads | 500 chars | Yes | Selectors unverified — see THREADS.md |

## Behavioral Flags

| Platform | User Confirm | URL Capture | Cloudflare | Requires GPU |
|---|---|---|---|---|
| Twitter | No | Yes | No | No |
| Bluesky | No | Yes | No | No |
| Instagram | No | Yes | No | No |
| Snapchat | Yes | No (SPA) | No | **Yes (WebGL)** |
| OnlyFans | Yes | No (SPA) | Yes | No |
| Fansly | Yes | No (SPA) | Yes | No |
| FetLife | Yes | Yes | Yes (cookie-only check) | No |
| Threads | Yes | Unverified | No | No |

## Key Capability Flags in Code

`PlatformSpecs` fields used by UI and processing logic:
- `supported_formats`, `max_image_dimensions`, `max_file_size_mb` — image constraints
- `supported_video_formats`, `max_video_dimensions`, `max_video_file_size_mb`, `max_video_duration_seconds` — video constraints
- `max_text_length`, `supports_text`, `supports_text_with_media` — text behavior
- `api_type`, `requires_user_confirm` — posting model
- `max_media_attachments` — attachment cap

## Behavior Notes

- Platform restrictions are enforced dynamically in the composer and selector.
- Unsupported static image formats may be auto-converted (e.g. WEBP → JPEG for Bluesky).
- Single static images attached for Snapchat are auto-converted to MP4 (video-only web path).
