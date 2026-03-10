# Media Processing

## Components
- `src/core/image_processor.py`
- `src/core/video_processor.py`
- `src/gui/image_preview_tabs.py` (preview rendering and processing orchestration)

## Image Pipeline
1. Validate image readability/format.
2. Convert static images to supported output formats when needed.
3. Resize to fit platform max dimensions while preserving aspect ratio.
4. Compress iteratively to meet file-size targets.
5. For animated GIFs, process frame-by-frame while preserving animation.
6. Cache processed outputs per platform/group to avoid redundant work.

## Video Pipeline
1. Probe metadata (ffprobe/ffmpeg fallback).
2. Determine whether re-encode is needed (size, duration, dimensions, format).
3. If needed, transcode to H.264/AAC MP4 with scaling/trimming.
4. Iterate compression settings when output remains too large.
5. Skip re-encode when source already satisfies platform requirements.

## Snapchat-Specific Conversions
- Single static image can be converted to MP4.
- Multi-image flow can use:
  - first image only
  - slideshow conversion
- Landscape handling supports crop/rotate behavior where applicable.

## Preview Behavior
- Preview tabs show platform-specific processed outputs.
- Video preview includes playback controls and change summary messaging.
- Processing can be queued with configurable parallel worker count.

## Restriction and Notice System
Composer + platform selector show dynamic notices for:
- unsupported format
- attachment-count limits
- video-only platform constraints
