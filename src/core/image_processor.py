"""Image resize and optimization per platform specifications."""

import io
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from PIL.Image import Resampling

from src.core.logger import get_logger
from src.utils.constants import PlatformSpecs


@dataclass
class ProcessedImage:
    """Result of processing an image for a platform."""

    path: Path
    original_size: tuple[int, int]
    processed_size: tuple[int, int]
    original_file_size: int
    processed_file_size: int
    format: str
    quality: int
    meets_requirements: bool
    warning: str | None = None


def validate_image(image_path: Path, specs: PlatformSpecs) -> str | None:
    """Check if an image is valid for a platform. Returns error code or None."""
    if not image_path.exists():
        return 'IMG-NOT-FOUND'

    try:
        with Image.open(image_path) as img:
            img.verify()
    except Exception as exc:
        get_logger().exception(
            'Image validation failed during verify',
            extra={
                'platform': specs.platform_name,
                'image_path': str(image_path),
                'error': str(exc),
            },
        )
        return 'IMG-CORRUPT'

    try:
        with Image.open(image_path) as img:
            fmt = img.format
            # Animated GIFs cannot be silently converted without losing animation.
            # Static images are auto-converted by PIL to a supported format.
            if fmt and fmt.upper() not in specs.supported_formats and is_animated_gif(image_path):
                return 'IMG-INVALID-FORMAT'
    except Exception as exc:
        get_logger().exception(
            'Image validation failed during format check',
            extra={
                'platform': specs.platform_name,
                'image_path': str(image_path),
                'error': str(exc),
            },
        )
        return 'IMG-CORRUPT'

    return None


def is_animated_gif(image_path: Path) -> bool:
    """Check if an image file is an animated GIF (more than one frame)."""
    try:
        with Image.open(image_path) as img:
            if img.format != 'GIF':
                return False
            return getattr(img, 'is_animated', False)
    except Exception:
        return False


def _resize_gif_frame(frame: Image.Image, new_size: tuple[int, int]) -> Image.Image:
    """Resize a single GIF frame, preserving palette mode."""
    return frame.resize(new_size, Resampling.LANCZOS)


def process_animated_gif(
    image_path: Path,
    specs: PlatformSpecs,
    progress_cb: Callable[[int], None] | None = None,
) -> ProcessedImage:
    """Resize and compress an animated GIF while preserving all frames.

    Pipeline:
    1. Load all frames from the GIF
    2. Scale each frame to fit max dimensions (preserve aspect ratio)
    3. Check total file size, reduce dimensions if needed
    4. Save with all frames preserved
    """
    logger = get_logger()
    try:
        logger.info(
            'Animated GIF processing start',
            extra={
                'platform': specs.platform_name,
                'image_path': str(image_path),
            },
        )
        _emit_progress(progress_cb, 0)
        original_file_size = image_path.stat().st_size

        img: Image.Image = Image.open(image_path)
        original_size = img.size
        n_frames = getattr(img, 'n_frames', 1)
        logger.info(
            'Loaded animated GIF',
            extra={
                'platform': specs.platform_name,
                'size': original_size,
                'frames': n_frames,
                'file_size': original_file_size,
            },
        )
        _emit_progress(progress_cb, 10)

        # Extract all frames and their durations
        frames: list[Image.Image] = []
        durations: list[int] = []
        for i in range(n_frames):
            img.seek(i)
            frame = img.copy()
            # Convert to RGBA for consistent processing (handles disposal methods)
            if frame.mode != 'RGBA':
                frame = frame.convert('RGBA')
            frames.append(frame)
            durations.append(img.info.get('duration', 100))
        _emit_progress(progress_cb, 30)

        # Calculate target dimensions
        max_w, max_h = specs.max_image_dimensions
        w, h = original_size
        if w > max_w or h > max_h:
            ratio = min(max_w / w, max_h / h)
            target_size = (int(w * ratio), int(h * ratio))
        else:
            target_size = (w, h)

        # Resize all frames
        resized_frames = [_resize_gif_frame(f, target_size) for f in frames]
        _emit_progress(progress_cb, 50)

        # Convert frames back to palette mode for GIF saving
        def _to_palette(frame_list: list[Image.Image]) -> list[Image.Image]:
            return [f.convert('P', palette=Image.Palette.ADAPTIVE, colors=256) for f in frame_list]

        palette_frames = _to_palette(resized_frames)

        # Save and check file size
        max_bytes = int(specs.max_file_size_mb * 1024 * 1024)
        buf = io.BytesIO()
        palette_frames[0].save(
            buf,
            format='GIF',
            save_all=True,
            append_images=palette_frames[1:],
            duration=durations,
            loop=img.info.get('loop', 0),
            optimize=True,
        )
        _emit_progress(progress_cb, 70)

        # If too large, progressively reduce dimensions
        warning = None
        scale_factor = 0.9
        current_frames = resized_frames
        while buf.tell() > max_bytes and scale_factor > 0.3:
            new_w = int(target_size[0] * scale_factor)
            new_h = int(target_size[1] * scale_factor)
            current_frames = [_resize_gif_frame(f, (new_w, new_h)) for f in frames]
            palette_frames = _to_palette(current_frames)
            target_size = (new_w, new_h)

            buf.seek(0)
            buf.truncate()
            palette_frames[0].save(
                buf,
                format='GIF',
                save_all=True,
                append_images=palette_frames[1:],
                duration=durations,
                loop=img.info.get('loop', 0),
                optimize=True,
            )
            scale_factor -= 0.1
            logger.debug(
                'Animated GIF dimension reduction',
                extra={
                    'platform': specs.platform_name,
                    'size': target_size,
                    'bytes': buf.tell(),
                    'max_bytes': max_bytes,
                },
            )
        _emit_progress(progress_cb, 80)

        meets = buf.tell() <= max_bytes
        if not meets:
            warning = f'Could not compress below {specs.max_file_size_mb}MB'

        # Save to temp file
        with tempfile.NamedTemporaryFile(
            suffix=f'_{specs.platform_name.lower()}.gif',
            delete=False,
        ) as tmp:
            tmp.write(buf.getvalue())
            tmp_name = tmp.name
        logger.info(
            'Saved processed animated GIF',
            extra={
                'platform': specs.platform_name,
                'output_path': tmp_name,
                'processed_size': target_size,
                'processed_bytes': buf.tell(),
                'frames': n_frames,
            },
        )
        _emit_progress(progress_cb, 100)

        return ProcessedImage(
            path=Path(tmp_name),
            original_size=original_size,
            processed_size=target_size,
            original_file_size=original_file_size,
            processed_file_size=buf.tell(),
            format='GIF',
            quality=100,
            meets_requirements=meets,
            warning=warning,
        )
    except Exception as exc:
        logger.exception(
            'Animated GIF processing failed',
            extra={
                'platform': specs.platform_name,
                'image_path': str(image_path),
                'error': str(exc),
            },
        )
        raise


def _emit_progress(progress_cb: Callable[[int], None] | None, value: int):
    if progress_cb is not None:
        progress_cb(value)


def _choose_output_format(img: Image.Image, specs: PlatformSpecs) -> str:
    """Pick a supported output format for the processed image."""
    supported = {fmt.upper() for fmt in specs.supported_formats}
    original = (img.format or '').upper()

    if original and original in supported:
        return original

    # Prefer PNG when transparency is present and PNG is supported.
    if img.mode in ('RGBA', 'LA') and 'PNG' in supported:
        return 'PNG'

    for preferred in ('JPEG', 'PNG', 'WEBP', 'GIF', 'BMP'):
        if preferred in supported:
            return preferred

    # Defensive fallback for malformed specs.
    return specs.supported_formats[0].upper() if specs.supported_formats else 'JPEG'


def process_image(
    image_path: Path,
    specs: PlatformSpecs,
    progress_cb: Callable[[int], None] | None = None,
) -> ProcessedImage:
    """Resize and compress an image to meet platform specs.

    Pipeline:
    1. Load and convert RGBA -> RGB (white background)
    2. Scale to fit max dimensions (preserve aspect ratio)
    3. Iteratively compress to meet file size limit
    """
    logger = get_logger()
    try:
        logger.info(
            'Image processing start',
            extra={
                'platform': specs.platform_name,
                'image_path': str(image_path),
                'temp_dir': tempfile.gettempdir(),
            },
        )
        _emit_progress(progress_cb, 0)
        original_file_size = image_path.stat().st_size

        img: Image.Image = Image.open(image_path)
        original_size = img.size
        logger.info(
            'Loaded image',
            extra={
                'platform': specs.platform_name,
                'mode': img.mode,
                'size': original_size,
                'file_size': original_file_size,
                'format': img.format,
                'image_path': str(image_path),
            },
        )
        _emit_progress(progress_cb, 10)

        # Convert RGBA to RGB with white background
        if img.mode == 'RGBA':
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            img = background
            logger.info(
                'Converted RGBA to RGB with white background',
                extra={'platform': specs.platform_name},
            )
        elif img.mode != 'RGB':
            img = img.convert('RGB')
            logger.info('Converted image to RGB', extra={'platform': specs.platform_name})
        _emit_progress(progress_cb, 20)

        # Determine output format
        out_format = _choose_output_format(img, specs)
        logger.debug(
            'Output format selected',
            extra={'platform': specs.platform_name, 'format': out_format},
        )
        _emit_progress(progress_cb, 30)

        # Scale to fit max dimensions
        max_w, max_h = specs.max_image_dimensions
        w, h = img.size
        if w > max_w or h > max_h:
            ratio = min(max_w / w, max_h / h)
            new_w = int(w * ratio)
            new_h = int(h * ratio)
            img = img.resize((new_w, new_h), Resampling.LANCZOS)
            logger.info(f'Resized {w}x{h} -> {new_w}x{new_h} for {specs.platform_name}')
        _emit_progress(progress_cb, 40)

        # Iterative compression
        max_bytes = int(specs.max_file_size_mb * 1024 * 1024)
        quality = 95
        buf = io.BytesIO()

        while quality >= 20:
            buf.seek(0)
            buf.truncate()
            if out_format.upper() in ('JPEG', 'JPG'):
                img.save(buf, format=out_format, quality=quality, optimize=True)
            elif out_format.upper() == 'PNG':
                img.save(buf, format=out_format, optimize=True)
            else:
                img.save(buf, format=out_format)

            logger.debug(
                'Compression attempt',
                extra={
                    'platform': specs.platform_name,
                    'quality': quality,
                    'bytes': buf.tell(),
                    'max_bytes': max_bytes,
                },
            )
            if buf.tell() <= max_bytes:
                break
            quality -= 5
            _emit_progress(progress_cb, 50)
        _emit_progress(progress_cb, 60)

        # If still too large, reduce dimensions
        warning = None
        scale_factor = 0.9
        while buf.tell() > max_bytes and scale_factor > 0.3:
            new_w = int(img.size[0] * scale_factor)
            new_h = int(img.size[1] * scale_factor)
            img = img.resize((new_w, new_h), Resampling.LANCZOS)

            buf.seek(0)
            buf.truncate()
            if out_format.upper() in ('JPEG', 'JPG'):
                img.save(buf, format=out_format, quality=max(quality, 20), optimize=True)
            else:
                img.save(buf, format=out_format)
            scale_factor -= 0.1
            logger.debug(
                'Dimension reduction attempt',
                extra={
                    'platform': specs.platform_name,
                    'size': img.size,
                    'bytes': buf.tell(),
                    'max_bytes': max_bytes,
                },
            )
            _emit_progress(progress_cb, 70)

        meets = buf.tell() <= max_bytes
        if not meets:
            warning = f'Could not compress below {specs.max_file_size_mb}MB'
            logger.debug(
                'Compression failed to meet size',
                extra={'platform': specs.platform_name, 'warning': warning},
            )
        _emit_progress(progress_cb, 80)

        # Save to temp file
        ext_map = {'PNG': '.png', 'GIF': '.gif', 'WEBP': '.webp'}
        ext = ext_map.get(out_format.upper(), '.jpg')
        with tempfile.NamedTemporaryFile(
            suffix=f'_{specs.platform_name.lower()}{ext}',
            delete=False,
        ) as tmp:
            tmp.write(buf.getvalue())
            tmp_name = tmp.name
        logger.info(
            'Saved processed image',
            extra={
                'platform': specs.platform_name,
                'input_path': str(image_path),
                'output_path': tmp_name,
                'processed_size': img.size,
                'processed_bytes': buf.tell(),
                'format': out_format,
            },
        )
        _emit_progress(progress_cb, 100)

        return ProcessedImage(
            path=Path(tmp_name),
            original_size=original_size,
            processed_size=img.size,
            original_file_size=original_file_size,
            processed_file_size=buf.tell(),
            format=out_format,
            quality=quality,
            meets_requirements=meets,
            warning=warning,
        )
    except Exception as exc:
        logger.exception(
            'Image processing failed',
            extra={
                'platform': specs.platform_name,
                'image_path': str(image_path),
                'error': str(exc),
            },
        )
        raise


def generate_thumbnail(image_path: Path, max_size: int = 400) -> Path | None:
    """Generate a thumbnail for preview display."""
    try:
        img: Image.Image = Image.open(image_path)
        img.thumbnail((max_size, max_size), Resampling.LANCZOS)
        with tempfile.NamedTemporaryFile(suffix='_thumb.png', delete=False) as tmp:
            img.save(tmp.name, 'PNG')
            get_logger().info(
                'Thumbnail generated',
                extra={'input_path': str(image_path), 'output_path': tmp.name},
            )
            return Path(tmp.name)
    except Exception as e:
        get_logger().exception(
            'Thumbnail generation failed',
            extra={'image_path': str(image_path), 'error': str(e)},
        )
        return None
