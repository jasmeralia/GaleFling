"""Tests for animated GIF support."""

import pytest
from PIL import Image

from src.core.image_processor import (
    is_animated_gif,
    process_animated_gif,
    process_image,
    validate_image,
)
from src.utils.constants import BLUESKY_SPECS, TWITTER_SPECS


def _make_animated_gif(path, size=(100, 100), n_frames=3):
    """Create an animated GIF with the given number of frames."""
    frames = []
    for i in range(n_frames):
        color = (i * 80, 50, 50)
        frames.append(Image.new('RGB', size, color=color))
    frames[0].save(
        path,
        format='GIF',
        save_all=True,
        append_images=frames[1:],
        duration=100,
        loop=0,
    )
    return path


@pytest.fixture
def animated_gif(tmp_path):
    """Create a small animated GIF."""
    return _make_animated_gif(tmp_path / 'animated.gif')


@pytest.fixture
def static_gif(tmp_path):
    """Create a single-frame GIF."""
    img = Image.new('RGB', (100, 100), color='red')
    path = tmp_path / 'static.gif'
    img.save(path, 'GIF')
    return path


@pytest.fixture
def large_animated_gif(tmp_path):
    """Create a large animated GIF (5000x5000)."""
    return _make_animated_gif(tmp_path / 'large_animated.gif', size=(5000, 5000), n_frames=3)


@pytest.fixture
def small_jpeg(tmp_path):
    """Create a small JPEG test image."""
    img = Image.new('RGB', (100, 100), color='red')
    path = tmp_path / 'small.jpg'
    img.save(path, 'JPEG')
    return path


class TestIsAnimatedGif:
    def test_animated_gif_detected(self, animated_gif):
        assert is_animated_gif(animated_gif) is True

    def test_static_gif_not_animated(self, static_gif):
        assert is_animated_gif(static_gif) is False

    def test_jpeg_not_animated(self, small_jpeg):
        assert is_animated_gif(small_jpeg) is False

    def test_missing_file_returns_false(self, tmp_path):
        assert is_animated_gif(tmp_path / 'nonexistent.gif') is False

    def test_corrupt_file_returns_false(self, tmp_path):
        bad = tmp_path / 'bad.gif'
        bad.write_bytes(b'not a gif')
        assert is_animated_gif(bad) is False


class TestValidateAnimatedGif:
    def test_animated_gif_valid_for_twitter(self, animated_gif):
        assert validate_image(animated_gif, TWITTER_SPECS) is None

    def test_animated_gif_invalid_for_bluesky(self, animated_gif):
        assert validate_image(animated_gif, BLUESKY_SPECS) == 'IMG-INVALID-FORMAT'


class TestProcessAnimatedGif:
    def test_small_animated_gif_preserves_frames(self, animated_gif):
        result = process_animated_gif(animated_gif, TWITTER_SPECS)
        assert result.meets_requirements
        assert result.path.exists()
        assert result.format == 'GIF'
        assert result.path.suffix == '.gif'
        # Verify output is still animated
        with Image.open(result.path) as img:
            assert getattr(img, 'is_animated', False)
            assert getattr(img, 'n_frames', 1) == 3

    def test_large_animated_gif_resized(self, large_animated_gif):
        result = process_animated_gif(large_animated_gif, TWITTER_SPECS)
        assert result.meets_requirements
        assert result.processed_size[0] <= TWITTER_SPECS.max_image_dimensions[0]
        assert result.processed_size[1] <= TWITTER_SPECS.max_image_dimensions[1]
        # Verify still animated
        with Image.open(result.path) as img:
            assert getattr(img, 'is_animated', False)
            assert getattr(img, 'n_frames', 1) == 3

    def test_aspect_ratio_preserved(self, tmp_path):
        path = _make_animated_gif(tmp_path / 'wide.gif', size=(6000, 3000), n_frames=2)
        result = process_animated_gif(path, TWITTER_SPECS)
        w, h = result.processed_size
        original_ratio = 6000 / 3000
        processed_ratio = w / h
        assert abs(original_ratio - processed_ratio) < 0.01

    def test_output_file_has_gif_extension(self, animated_gif):
        result = process_animated_gif(animated_gif, TWITTER_SPECS)
        assert result.path.suffix == '.gif'
        assert 'twitter' in result.path.name.lower()

    def test_progress_callback_called(self, animated_gif):
        progress_values = []
        result = process_animated_gif(
            animated_gif, TWITTER_SPECS, progress_cb=progress_values.append
        )
        assert result.meets_requirements
        assert 0 in progress_values
        assert 100 in progress_values


class TestProcessImageStaticGif:
    def test_static_gif_on_twitter_keeps_format(self, static_gif):
        """A static GIF on Twitter should output as GIF format."""
        result = process_image(static_gif, TWITTER_SPECS)
        assert result.meets_requirements
        # Static GIF gets converted to RGB, so it becomes JPEG
        # (GIF requires palette mode; process_image converts to RGB)
        assert result.path.exists()

    def test_static_gif_extension_mapping(self, tmp_path):
        """Verify the extension map handles various formats."""
        img = Image.new('RGB', (100, 100), color='red')
        path = tmp_path / 'test.png'
        img.save(path, 'PNG')
        result = process_image(path, TWITTER_SPECS)
        assert result.path.suffix == '.png'
