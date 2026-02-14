"""Tests for image processing."""


import pytest
from PIL import Image

from src.core.image_processor import (
    generate_thumbnail,
    process_image,
    validate_image,
)
from src.utils.constants import BLUESKY_SPECS, TWITTER_SPECS


@pytest.fixture
def small_jpeg(tmp_path):
    """Create a small JPEG test image."""
    img = Image.new('RGB', (100, 100), color='red')
    path = tmp_path / 'small.jpg'
    img.save(path, 'JPEG')
    return path


@pytest.fixture
def large_jpeg(tmp_path):
    """Create a large JPEG test image (5000x5000)."""
    img = Image.new('RGB', (5000, 5000), color='blue')
    path = tmp_path / 'large.jpg'
    img.save(path, 'JPEG', quality=95)
    return path


@pytest.fixture
def rgba_png(tmp_path):
    """Create an RGBA PNG test image."""
    img = Image.new('RGBA', (200, 200), color=(255, 0, 0, 128))
    path = tmp_path / 'alpha.png'
    img.save(path, 'PNG')
    return path


class TestValidateImage:
    def test_valid_jpeg(self, small_jpeg):
        assert validate_image(small_jpeg, TWITTER_SPECS) is None

    def test_missing_file(self, tmp_path):
        missing = tmp_path / 'nonexistent.jpg'
        assert validate_image(missing, TWITTER_SPECS) == 'IMG-NOT-FOUND'

    def test_corrupt_file(self, tmp_path):
        corrupt = tmp_path / 'corrupt.jpg'
        corrupt.write_bytes(b'not an image')
        assert validate_image(corrupt, TWITTER_SPECS) == 'IMG-CORRUPT'


class TestProcessImage:
    def test_small_image_passes_through(self, small_jpeg):
        result = process_image(small_jpeg, TWITTER_SPECS)
        assert result.meets_requirements
        assert result.path.exists()
        assert result.processed_size[0] <= TWITTER_SPECS.max_image_dimensions[0]

    def test_large_image_resized_for_twitter(self, large_jpeg):
        result = process_image(large_jpeg, TWITTER_SPECS)
        assert result.meets_requirements
        assert result.processed_size[0] <= TWITTER_SPECS.max_image_dimensions[0]
        assert result.processed_size[1] <= TWITTER_SPECS.max_image_dimensions[1]

    def test_large_image_resized_for_bluesky(self, large_jpeg):
        result = process_image(large_jpeg, BLUESKY_SPECS)
        assert result.processed_size[0] <= BLUESKY_SPECS.max_image_dimensions[0]
        assert result.processed_size[1] <= BLUESKY_SPECS.max_image_dimensions[1]

    def test_rgba_converted_to_rgb(self, rgba_png):
        result = process_image(rgba_png, TWITTER_SPECS)
        assert result.meets_requirements
        processed_img = Image.open(result.path)
        assert processed_img.mode == 'RGB'

    def test_aspect_ratio_preserved(self, tmp_path):
        img = Image.new('RGB', (4000, 2000), color='green')
        path = tmp_path / 'wide.jpg'
        img.save(path, 'JPEG')

        result = process_image(path, BLUESKY_SPECS)
        w, h = result.processed_size
        original_ratio = 4000 / 2000
        processed_ratio = w / h
        assert abs(original_ratio - processed_ratio) < 0.01


class TestGenerateThumbnail:
    def test_creates_thumbnail(self, small_jpeg):
        thumb = generate_thumbnail(small_jpeg, max_size=50)
        assert thumb is not None
        assert thumb.exists()
        img = Image.open(thumb)
        assert img.size[0] <= 50
        assert img.size[1] <= 50

    def test_returns_none_for_invalid(self, tmp_path):
        bad = tmp_path / 'bad.jpg'
        bad.write_bytes(b'not an image')
        assert generate_thumbnail(bad) is None
