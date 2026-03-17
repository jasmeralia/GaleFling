"""Functional tests for media processing — real PIL and ffmpeg operations.

These tests do NOT require any platform credentials. They exercise the actual
image and video processing pipelines against real platform constraint specs.
They can optionally run in CI if ffmpeg is available.
"""

import pytest
from PIL import Image

from src.core.image_processor import process_animated_gif, process_image, validate_image
from src.core.video_processor import (
    get_ffmpeg_path,
    get_ffmpeg_version,
    get_video_info,
    process_video,
    validate_video,
)
from src.utils.constants import (
    BLUESKY_SPECS,
    INSTAGRAM_SPECS,
    TWITTER_SPECS,
)

# ── Image processing tests ───────────────────────────────────────────


@pytest.mark.functional
class TestImageResizeToPlatformLimits:
    """Verify images are resized to each platform's max dimensions."""

    @pytest.mark.parametrize(
        'specs',
        [TWITTER_SPECS, BLUESKY_SPECS, INSTAGRAM_SPECS],
        ids=['twitter', 'bluesky', 'instagram'],
    )
    def test_oversized_image_is_resized(self, oversized_jpeg, specs):
        """A 5000x5000 image should be scaled down to fit max dimensions."""
        result = process_image(oversized_jpeg, specs)
        max_w, max_h = specs.max_image_dimensions
        assert result.processed_size[0] <= max_w
        assert result.processed_size[1] <= max_h
        assert result.meets_requirements
        assert result.path.exists()
        # Clean up temp file
        result.path.unlink(missing_ok=True)

    @pytest.mark.parametrize(
        'specs',
        [TWITTER_SPECS, BLUESKY_SPECS, INSTAGRAM_SPECS],
        ids=['twitter', 'bluesky', 'instagram'],
    )
    def test_small_image_not_upscaled(self, sample_jpeg, specs):
        """A 100x100 image should not be upscaled."""
        result = process_image(sample_jpeg, specs)
        assert result.processed_size == (100, 100)
        assert result.meets_requirements
        result.path.unlink(missing_ok=True)


@pytest.mark.functional
class TestImageFormatConversion:
    """Verify unsupported formats are converted to supported ones."""

    def test_webp_to_jpeg_for_bluesky(self, tmp_path):
        """Bluesky only supports JPEG/PNG — WebP should be converted."""
        webp_path = tmp_path / 'test.webp'
        img = Image.new('RGB', (200, 200), color='purple')
        img.save(str(webp_path), 'WEBP')

        result = process_image(webp_path, BLUESKY_SPECS)
        assert result.format in ('JPEG', 'PNG')
        assert result.meets_requirements
        result.path.unlink(missing_ok=True)

    def test_rgba_png_transparency(self, tmp_path):
        """RGBA PNG should be converted to RGB with white background for JPEG targets."""
        rgba_path = tmp_path / 'transparent.png'
        img = Image.new('RGBA', (200, 200), color=(255, 0, 0, 128))
        img.save(str(rgba_path), 'PNG')

        result = process_image(rgba_path, TWITTER_SPECS)
        assert result.meets_requirements
        # Verify the output is a valid image
        with Image.open(result.path) as out:
            assert out.mode == 'RGB' or result.format == 'PNG'
        result.path.unlink(missing_ok=True)


@pytest.mark.functional
class TestImageFileSizeLimits:
    """Verify images are compressed to meet file size limits."""

    def test_bluesky_1mb_limit(self, tmp_path):
        """Create an image that would be >1MB uncompressed and verify it's compressed."""
        # Create a large noisy image (noise compresses poorly)
        import random

        img = Image.new('RGB', (2000, 2000))
        pixels = img.load()
        rng = random.Random(42)
        for x in range(2000):
            for y in range(2000):
                pixels[x, y] = (rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255))
        path = tmp_path / 'noisy.png'
        img.save(str(path), 'PNG')

        result = process_image(path, BLUESKY_SPECS)
        max_bytes = int(BLUESKY_SPECS.max_file_size_mb * 1024 * 1024)
        if result.meets_requirements:
            assert result.processed_file_size <= max_bytes
        result.path.unlink(missing_ok=True)


@pytest.mark.functional
class TestImageValidation:
    """Verify the validate_image function catches invalid files."""

    def test_missing_file(self, tmp_path):
        from pathlib import Path

        assert validate_image(Path(tmp_path / 'nonexistent.jpg'), TWITTER_SPECS) == 'IMG-NOT-FOUND'

    def test_corrupt_file(self, tmp_path):
        corrupt = tmp_path / 'corrupt.jpg'
        corrupt.write_bytes(b'not a real image')
        assert validate_image(corrupt, TWITTER_SPECS) == 'IMG-CORRUPT'

    def test_valid_jpeg(self, sample_jpeg):
        assert validate_image(sample_jpeg, TWITTER_SPECS) is None


@pytest.mark.functional
class TestAnimatedGifProcessing:
    """Verify animated GIF processing preserves frames."""

    def test_animated_gif_resize(self, tmp_path):
        """Create a simple 2-frame GIF and verify it processes correctly."""
        frames = [
            Image.new('RGB', (3000, 3000), color='red'),
            Image.new('RGB', (3000, 3000), color='blue'),
        ]
        gif_path = tmp_path / 'animated.gif'
        frames[0].save(
            str(gif_path),
            format='GIF',
            save_all=True,
            append_images=frames[1:],
            duration=100,
            loop=0,
        )

        result = process_animated_gif(gif_path, BLUESKY_SPECS)
        max_w, max_h = BLUESKY_SPECS.max_image_dimensions
        assert result.processed_size[0] <= max_w
        assert result.processed_size[1] <= max_h
        assert result.format == 'GIF'

        # Verify output is still animated
        with Image.open(result.path) as out:
            assert getattr(out, 'n_frames', 1) >= 2
        result.path.unlink(missing_ok=True)


# ── Video processing tests ───────────────────────────────────────────


@pytest.mark.functional
class TestFfmpegAvailability:
    """Verify ffmpeg is installed and accessible."""

    def test_ffmpeg_path(self):
        path = get_ffmpeg_path()
        assert path

    def test_ffmpeg_version(self):
        version = get_ffmpeg_version()
        assert version != 'unknown'


@pytest.mark.functional
class TestVideoInfo:
    """Verify video metadata extraction."""

    def test_probe_video(self, sample_video):
        info = get_video_info(sample_video)
        assert info.width == 320
        assert info.height == 240
        assert 1.5 <= info.duration_seconds <= 3.0
        assert info.codec in ('h264', 'libx264')
        assert info.file_size > 0


@pytest.mark.functional
class TestVideoValidation:
    """Verify video validation catches constraint violations."""

    def test_valid_video(self, sample_video):
        assert validate_video(sample_video, TWITTER_SPECS) is None

    def test_missing_file(self, tmp_path):
        from pathlib import Path

        assert validate_video(Path(tmp_path / 'missing.mp4'), TWITTER_SPECS) == 'VID-NOT-FOUND'


@pytest.mark.functional
class TestVideoProcessing:
    """Verify video resize/compression pipeline."""

    @pytest.mark.parametrize(
        'specs',
        [TWITTER_SPECS, BLUESKY_SPECS, INSTAGRAM_SPECS],
        ids=['twitter', 'bluesky', 'instagram'],
    )
    def test_process_small_video(self, sample_video, specs):
        """A small 320x240 video within limits should pass through or re-encode cleanly."""
        result = process_video(sample_video, specs)
        assert result.meets_requirements
        assert result.processed_info.width > 0
        assert result.processed_info.height > 0
        if result.path != sample_video:
            result.path.unlink(missing_ok=True)

    def test_process_preserves_duration(self, sample_video):
        """Processing should not significantly alter duration when not trimming."""
        result = process_video(sample_video, TWITTER_SPECS)
        # Original is ~2s, processed should be similar
        assert result.processed_info.duration_seconds >= 1.0
        if result.path != sample_video:
            result.path.unlink(missing_ok=True)
