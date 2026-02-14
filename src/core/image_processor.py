"""Image resize and optimization per platform specifications."""

import io
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

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
    except Exception:
        return 'IMG-CORRUPT'

    try:
        with Image.open(image_path) as img:
            fmt = img.format
            if fmt and fmt.upper() not in specs.supported_formats:
                return 'IMG-INVALID-FORMAT'
    except Exception:
        return 'IMG-CORRUPT'

    return None


def process_image(image_path: Path, specs: PlatformSpecs) -> ProcessedImage:
    """Resize and compress an image to meet platform specs.

    Pipeline:
    1. Load and convert RGBA -> RGB (white background)
    2. Scale to fit max dimensions (preserve aspect ratio)
    3. Iteratively compress to meet file size limit
    """
    logger = get_logger()
    original_file_size = image_path.stat().st_size

    img = Image.open(image_path)
    original_size = img.size

    # Convert RGBA to RGB with white background
    if img.mode == 'RGBA':
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background
    elif img.mode != 'RGB':
        img = img.convert('RGB')

    # Determine output format
    out_format = img.format if img.format and img.format.upper() in specs.supported_formats else 'JPEG'
    if out_format.upper() not in specs.supported_formats:
        out_format = 'JPEG'

    # Scale to fit max dimensions
    max_w, max_h = specs.max_image_dimensions
    w, h = img.size
    if w > max_w or h > max_h:
        ratio = min(max_w / w, max_h / h)
        new_w = int(w * ratio)
        new_h = int(h * ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        logger.info(f"Resized {w}x{h} -> {new_w}x{new_h} for {specs.platform_name}")

    # Iterative compression
    max_bytes = int(specs.max_file_size_mb * 1024 * 1024)
    quality = 95
    buf = io.BytesIO()

    while quality >= 20:
        buf.seek(0)
        buf.truncate()
        save_kwargs = {'format': out_format}
        if out_format.upper() in ('JPEG', 'JPG'):
            save_kwargs['quality'] = quality
            save_kwargs['optimize'] = True
        elif out_format.upper() == 'PNG':
            save_kwargs['optimize'] = True
        img.save(buf, **save_kwargs)

        if buf.tell() <= max_bytes:
            break
        quality -= 5

    # If still too large, reduce dimensions
    warning = None
    scale_factor = 0.9
    while buf.tell() > max_bytes and scale_factor > 0.3:
        new_w = int(img.size[0] * scale_factor)
        new_h = int(img.size[1] * scale_factor)
        img = img.resize((new_w, new_h), Image.LANCZOS)

        buf.seek(0)
        buf.truncate()
        save_kwargs = {'format': out_format}
        if out_format.upper() in ('JPEG', 'JPG'):
            save_kwargs['quality'] = max(quality, 20)
            save_kwargs['optimize'] = True
        img.save(buf, **save_kwargs)
        scale_factor -= 0.1

    meets = buf.tell() <= max_bytes
    if not meets:
        warning = f"Could not compress below {specs.max_file_size_mb}MB"

    # Save to temp file
    ext = '.png' if out_format.upper() == 'PNG' else '.jpg'
    tmp = tempfile.NamedTemporaryFile(
        suffix=f'_{specs.platform_name.lower()}{ext}',
        delete=False,
    )
    tmp.write(buf.getvalue())
    tmp.close()

    return ProcessedImage(
        path=Path(tmp.name),
        original_size=original_size,
        processed_size=img.size,
        original_file_size=original_file_size,
        processed_file_size=buf.tell(),
        format=out_format,
        quality=quality,
        meets_requirements=meets,
        warning=warning,
    )


def generate_thumbnail(image_path: Path, max_size: int = 400) -> Path | None:
    """Generate a thumbnail for preview display."""
    try:
        img = Image.open(image_path)
        img.thumbnail((max_size, max_size), Image.LANCZOS)
        tmp = tempfile.NamedTemporaryFile(suffix='_thumb.png', delete=False)
        img.save(tmp.name, 'PNG')
        return Path(tmp.name)
    except Exception as e:
        get_logger().warning(f"Thumbnail generation failed: {e}")
        return None
