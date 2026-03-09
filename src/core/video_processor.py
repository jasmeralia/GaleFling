"""Video resize, compression, and thumbnail extraction per platform specifications."""

import contextlib
import json
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from src.core.logger import get_logger
from src.utils.constants import PlatformSpecs


def get_ffmpeg_path() -> str:
    """Return path to the bundled ffmpeg binary."""
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise RuntimeError('VID-FFMPEG-MISSING') from exc


def get_ffprobe_path() -> str:
    """Return path to the ffprobe binary alongside the bundled ffmpeg."""
    ffmpeg = Path(get_ffmpeg_path())
    # imageio-ffmpeg bundles ffmpeg; ffprobe sits alongside it or we use ffmpeg -i
    ffprobe = ffmpeg.parent / ffmpeg.name.replace('ffmpeg', 'ffprobe')
    if ffprobe.exists():
        return str(ffprobe)
    # Fallback: use ffmpeg itself for probing (via -i flag)
    return str(ffmpeg)


def get_ffmpeg_version() -> str:
    """Probe the ffmpeg binary and return its version string."""
    logger = get_logger()
    try:
        ffmpeg = get_ffmpeg_path()
        result = subprocess.run(
            [ffmpeg, '-version'],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = (result.stdout or result.stderr or '').strip()
        if not output:
            return 'unknown'

        first_line = output.splitlines()[0].strip()
        prefix = 'ffmpeg version '
        if first_line.lower().startswith(prefix):
            version = first_line[len(prefix) :].split(' ', 1)[0].strip()
            if version:
                return version
        return first_line
    except Exception as exc:
        logger.warning('Could not probe ffmpeg version', extra={'error': str(exc)})
        return 'unknown'


@dataclass
class VideoInfo:
    """Metadata extracted from a video file."""

    width: int
    height: int
    duration_seconds: float
    codec: str
    file_size: int
    format_name: str  # container format, e.g. 'mp4'


@dataclass
class ProcessedVideo:
    """Result of processing a video for a platform."""

    path: Path
    original_info: VideoInfo
    processed_info: VideoInfo
    meets_requirements: bool
    warning: str | None = None


def _emit_progress(progress_cb: Callable[[int], None] | None, value: int):
    if progress_cb is not None:
        progress_cb(value)


def get_video_info(video_path: Path) -> VideoInfo:
    """Extract video metadata using ffprobe/ffmpeg."""
    logger = get_logger()
    ffmpeg = get_ffmpeg_path()
    file_size = video_path.stat().st_size

    try:
        # Try ffprobe first (may be alongside ffmpeg binary)
        ffprobe = get_ffprobe_path()
        if ffprobe != str(Path(ffmpeg)):
            probe_result = subprocess.run(
                [
                    ffprobe,
                    '-v',
                    'quiet',
                    '-print_format',
                    'json',
                    '-show_format',
                    '-show_streams',
                    '-select_streams',
                    'v:0',
                    str(video_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            probe_data = None
            if probe_result.stdout.strip():
                with contextlib.suppress(json.JSONDecodeError):
                    probe_data = json.loads(probe_result.stdout)

            if probe_data:
                streams = probe_data.get('streams', [])
                fmt = probe_data.get('format', {})
                video_stream = streams[0] if streams else {}
                width = int(video_stream.get('width', 0))
                height = int(video_stream.get('height', 0))
                duration = float(fmt.get('duration', video_stream.get('duration', 0)))
                codec = video_stream.get('codec_name', 'unknown')
                format_name = fmt.get('format_name', 'unknown')
                # Normalize format name (e.g., "mov,mp4,m4a,3gp,3g2,mj2" -> "mp4")
                if ',' in format_name:
                    ext = video_path.suffix.lstrip('.').lower()
                    format_name = ext if ext else format_name.split(',')[0]
                return VideoInfo(
                    width=width,
                    height=height,
                    duration_seconds=duration,
                    codec=codec,
                    file_size=file_size,
                    format_name=format_name,
                )

        # Fallback: parse ffmpeg -i stderr output
        result = subprocess.run(
            [ffmpeg, '-i', str(video_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        stderr = result.stderr or ''
        return _parse_ffmpeg_stderr(stderr, file_size, video_path)
    except subprocess.TimeoutExpired:
        logger.warning('ffprobe timed out', extra={'video_path': str(video_path)})
        raise
    except Exception as exc:
        logger.exception(
            'Failed to get video info',
            extra={'video_path': str(video_path), 'error': str(exc)},
        )
        raise


def _parse_ffmpeg_stderr(stderr: str, file_size: int, video_path: Path) -> VideoInfo:
    """Parse ffmpeg -i stderr output as a fallback for metadata extraction."""
    import re

    width = height = 0
    duration = 0.0
    codec = 'unknown'
    format_name = video_path.suffix.lstrip('.').lower()

    # Parse duration: Duration: HH:MM:SS.ss
    dur_match = re.search(r'Duration:\s*(\d+):(\d+):(\d+)\.(\d+)', stderr)
    if dur_match:
        h, m, s, cs = dur_match.groups()
        duration = int(h) * 3600 + int(m) * 60 + int(s) + int(cs) / 100

    # Parse video stream: Video: h264 (...), ..., 320x240
    vid_match = re.search(r'Video:\s+(\w+)\s.*?(\d{2,5})x(\d{2,5})', stderr)
    if vid_match:
        codec = vid_match.group(1)
        width = int(vid_match.group(2))
        height = int(vid_match.group(3))

    return VideoInfo(
        width=width,
        height=height,
        duration_seconds=duration,
        codec=codec,
        file_size=file_size,
        format_name=format_name,
    )


def validate_video(video_path: Path, specs: PlatformSpecs) -> str | None:
    """Check if a video is valid for a platform. Returns error code or None."""
    if not video_path.exists():
        return 'VID-NOT-FOUND'

    ext = video_path.suffix.lstrip('.').upper()
    if ext not in specs.supported_video_formats:
        return 'VID-INVALID-FORMAT'

    try:
        info = get_video_info(video_path)
    except Exception:
        return 'VID-CORRUPT'

    if info.duration_seconds <= 0:
        return 'VID-CORRUPT'

    if (
        specs.max_video_duration_seconds is not None
        and info.duration_seconds > specs.max_video_duration_seconds
    ):
        return 'VID-TOO-LONG'

    if specs.max_video_file_size_mb is not None:
        max_bytes = int(specs.max_video_file_size_mb * 1024 * 1024)
        if info.file_size > max_bytes:
            return 'VID-TOO-LARGE'

    return None


def convert_image_to_video(
    image_path: Path,
    specs: PlatformSpecs,
    duration_seconds: int = 5,
    progress_cb: Callable[[int], None] | None = None,
) -> Path:
    """Convert a static image to an MP4 video for video-only platforms."""
    logger = get_logger()
    ffmpeg = get_ffmpeg_path()

    if duration_seconds <= 0:
        raise ValueError('duration_seconds must be greater than zero')

    max_w, max_h = specs.max_video_dimensions or (1080, 1920)
    target_w = max_w - (max_w % 2)
    target_h = max_h - (max_h % 2)

    with tempfile.NamedTemporaryFile(
        suffix=f'_{specs.platform_name.lower()}_img.mp4',
        delete=False,
    ) as tmp:
        output_path = Path(tmp.name)

    cmd = [
        ffmpeg,
        '-y',
        '-loop',
        '1',
        '-i',
        str(image_path),
        '-t',
        str(duration_seconds),
        '-vf',
        (
            f'scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,'
            f'pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,format=yuv420p'
        ),
        '-r',
        '30',
        '-c:v',
        'libx264',
        '-pix_fmt',
        'yuv420p',
        '-an',
        '-movflags',
        '+faststart',
        str(output_path),
    ]

    logger.info(
        'Converting static image to video',
        extra={
            'platform': specs.platform_name,
            'image_path': str(image_path),
            'output_path': str(output_path),
            'duration_seconds': duration_seconds,
            'target_dimensions': f'{target_w}x{target_h}',
        },
    )
    _emit_progress(progress_cb, 0)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        output_path.unlink(missing_ok=True)
        logger.error(
            'Image-to-video conversion failed',
            extra={
                'platform': specs.platform_name,
                'returncode': result.returncode,
                'stderr': result.stderr[-500:] if result.stderr else '',
            },
        )
        raise RuntimeError(f'ffmpeg exited with code {result.returncode}')

    _emit_progress(progress_cb, 100)
    return output_path


def process_video(
    video_path: Path,
    specs: PlatformSpecs,
    progress_cb: Callable[[int], None] | None = None,
) -> ProcessedVideo:
    """Resize and compress a video to meet platform specs.

    Pipeline:
    1. Probe video metadata
    2. Scale to fit max dimensions (preserve aspect ratio)
    3. Trim to max duration if needed
    4. Re-encode to H.264+AAC MP4 if resize/trim is needed
    5. If file too large, re-encode with lower CRF
    """
    logger = get_logger()
    ffmpeg = get_ffmpeg_path()

    try:
        logger.info(
            'Video processing start',
            extra={'platform': specs.platform_name, 'video_path': str(video_path)},
        )
        _emit_progress(progress_cb, 0)

        original_info = get_video_info(video_path)
        logger.info(
            'Loaded video info',
            extra={
                'platform': specs.platform_name,
                'width': original_info.width,
                'height': original_info.height,
                'duration': original_info.duration_seconds,
                'codec': original_info.codec,
                'file_size': original_info.file_size,
            },
        )
        _emit_progress(progress_cb, 10)

        max_dims = specs.max_video_dimensions
        needs_resize = False
        target_w, target_h = original_info.width, original_info.height

        if max_dims:
            max_w, max_h = max_dims
            if target_w > max_w or target_h > max_h:
                ratio = min(max_w / target_w, max_h / target_h)
                target_w = int(target_w * ratio)
                target_h = int(target_h * ratio)
                needs_resize = True
        # Ensure even dimensions (required by H.264)
        target_w = target_w - (target_w % 2)
        target_h = target_h - (target_h % 2)

        needs_trim = False
        target_duration = original_info.duration_seconds
        if (
            specs.max_video_duration_seconds is not None
            and original_info.duration_seconds > specs.max_video_duration_seconds
        ):
            target_duration = specs.max_video_duration_seconds
            needs_trim = True

        max_bytes = None
        if specs.max_video_file_size_mb is not None:
            max_bytes = int(specs.max_video_file_size_mb * 1024 * 1024)

        needs_reencode = needs_resize or needs_trim or original_info.codec != 'h264'

        # If no processing needed and file size is OK, just copy
        if not needs_reencode and (max_bytes is None or original_info.file_size <= max_bytes):
            _emit_progress(progress_cb, 100)
            return ProcessedVideo(
                path=video_path,
                original_info=original_info,
                processed_info=original_info,
                meets_requirements=True,
            )

        _emit_progress(progress_cb, 20)

        # Build ffmpeg command
        crf = 23  # Default quality
        output_path: Path | None = None
        warning: str | None = None

        for attempt in range(4):  # Try up to 4 CRF levels: 23, 28, 33, 38
            with tempfile.NamedTemporaryFile(
                suffix=f'_{specs.platform_name.lower()}.mp4',
                delete=False,
            ) as tmp:
                output_path = Path(tmp.name)

            cmd = [
                ffmpeg,
                '-y',
                '-i',
                str(video_path),
            ]

            if needs_trim:
                cmd.extend(['-t', str(target_duration)])

            cmd.extend(
                [
                    '-c:v',
                    'libx264',
                    '-crf',
                    str(crf),
                    '-preset',
                    'medium',
                    '-c:a',
                    'aac',
                    '-b:a',
                    '128k',
                ]
            )

            if needs_resize or target_w != original_info.width or target_h != original_info.height:
                cmd.extend(['-vf', f'scale={target_w}:{target_h}'])

            cmd.extend(
                [
                    '-movflags',
                    '+faststart',
                    str(output_path),
                ]
            )

            logger.debug(
                'Running ffmpeg',
                extra={
                    'platform': specs.platform_name,
                    'crf': crf,
                    'attempt': attempt,
                    'cmd': ' '.join(cmd),
                },
            )

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
            )

            if result.returncode != 0:
                logger.error(
                    'ffmpeg failed',
                    extra={
                        'platform': specs.platform_name,
                        'returncode': result.returncode,
                        'stderr': result.stderr[-500:] if result.stderr else '',
                    },
                )
                raise RuntimeError(f'ffmpeg exited with code {result.returncode}')

            _emit_progress(progress_cb, 50 + attempt * 10)

            output_size = output_path.stat().st_size
            if max_bytes is None or output_size <= max_bytes:
                break

            # File too large, increase CRF for more compression
            crf += 5
            if crf > 38:
                warning = f'Could not compress below {specs.max_video_file_size_mb}MB'
                break
            # Clean up and retry
            output_path.unlink(missing_ok=True)

        _emit_progress(progress_cb, 80)

        assert output_path is not None  # guaranteed by the for loop above
        processed_info = get_video_info(output_path)
        meets = max_bytes is None or processed_info.file_size <= max_bytes

        if not meets and not warning:
            warning = f'Could not compress below {specs.max_video_file_size_mb}MB'

        logger.info(
            'Saved processed video',
            extra={
                'platform': specs.platform_name,
                'output_path': str(output_path),
                'processed_size': f'{processed_info.width}x{processed_info.height}',
                'processed_bytes': processed_info.file_size,
                'duration': processed_info.duration_seconds,
            },
        )
        _emit_progress(progress_cb, 100)

        return ProcessedVideo(
            path=output_path,
            original_info=original_info,
            processed_info=processed_info,
            meets_requirements=meets,
            warning=warning,
        )
    except Exception as exc:
        logger.exception(
            'Video processing failed',
            extra={
                'platform': specs.platform_name,
                'video_path': str(video_path),
                'error': str(exc),
            },
        )
        raise


def extract_thumbnail(video_path: Path, max_size: int = 400) -> Path | None:
    """Extract the first frame from a video as a PNG thumbnail."""
    logger = get_logger()
    try:
        ffmpeg = get_ffmpeg_path()
        with tempfile.NamedTemporaryFile(suffix='_vthumb.png', delete=False) as tmp:
            thumb_path = Path(tmp.name)

        result = subprocess.run(
            [
                ffmpeg,
                '-y',
                '-i',
                str(video_path),
                '-vframes',
                '1',
                '-vf',
                f'scale={max_size}:{max_size}:force_original_aspect_ratio=decrease',
                str(thumb_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0 and thumb_path.exists() and thumb_path.stat().st_size > 0:
            logger.info(
                'Video thumbnail generated',
                extra={'video_path': str(video_path), 'thumb_path': str(thumb_path)},
            )
            return thumb_path

        logger.warning(
            'Video thumbnail extraction failed',
            extra={'video_path': str(video_path), 'returncode': result.returncode},
        )
        thumb_path.unlink(missing_ok=True)
        return None
    except Exception as exc:
        logger.exception(
            'Video thumbnail extraction failed',
            extra={'video_path': str(video_path), 'error': str(exc)},
        )
        return None
