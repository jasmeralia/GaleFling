# Platform Specs

## Source of Truth
Platform limits and capabilities are defined in `src/utils/constants.py` (`PlatformSpecs` + `PLATFORM_SPECS_MAP`).

## Account Limits and Types
- Twitter: up to 2, API
- Bluesky: up to 2, API
- Instagram: up to 2, API
- Snapchat: up to 2, WebView
- OnlyFans: 1, WebView
- Fansly: 1, WebView
- FetLife: 1, WebView
- Threads: up to 2, WebView

## Key Capability Flags
`PlatformSpecs` includes key behavioral fields used by UI and processing:
- image constraints (`supported_formats`, `max_image_dimensions`, `max_file_size_mb`)
- video constraints (`supported_video_formats`, `max_video_dimensions`, `max_video_file_size_mb`, `max_video_duration_seconds`)
- text behavior (`max_text_length`, `supports_text`, `supports_text_with_media`)
- posting model (`api_type`, `requires_user_confirm`)
- media attachment cap (`max_media_attachments`)

## Current Limits Snapshot
### Images
- Twitter: 4096x4096, 5 MB, JPEG/PNG/GIF/WEBP
- Bluesky: 2000x2000, 1 MB, JPEG/PNG
- Instagram: 1440x1440, 8 MB, JPEG/PNG
- Snapchat: image upload not native on web path (video-oriented flow)
- OnlyFans: 4096x4096, 50 MB, JPEG/PNG/WEBP
- Fansly: 4096x4096, 50 MB, JPEG/PNG/WEBP
- FetLife: 4096x4096, 20 MB, JPEG/PNG
- Threads: 1440x1440, 10 MB, JPEG/PNG/GIF

### Videos
- Twitter: MP4, 1920x1200, 512 MB, 140s
- Bluesky: MP4, 1920x1080, 50 MB, 60s
- Instagram: MP4, 1920x1080, 100 MB, 60s
- Snapchat: MP4, 1080x1920, 50 MB, 60s
- OnlyFans: MP4/MOV, 3840x2160, 5120 MB
- Fansly: MP4/MOV, 3840x2160, 5120 MB
- FetLife: MP4, 1920x1080, 500 MB
- Threads: MP4, 1920x1080, 1024 MB, 300s

## Behavior Notes
- Platform restrictions are enforced dynamically in composer/selector.
- Unsupported static image formats may be auto-converted.
- Video-only targets can use image-to-video conversion where supported by app logic.
