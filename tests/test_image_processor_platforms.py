"""Tests for image processing with Phase 1 platform specs."""

import pytest
from PIL import Image

from src.core.image_processor import process_image, validate_image
from src.utils.constants import (
    FANSLY_SPECS,
    FETLIFE_SPECS,
    INSTAGRAM_SPECS,
    ONLYFANS_SPECS,
    SNAPCHAT_SPECS,
)


@pytest.fixture
def large_image(tmp_path):
    """Create a large test image (3000x3000)."""
    img = Image.new('RGB', (3000, 3000), color='blue')
    path = tmp_path / 'large.jpg'
    img.save(path, 'JPEG', quality=95)
    return path


@pytest.fixture
def vertical_image(tmp_path):
    """Create a vertical test image for Snapchat (1080x1920)."""
    img = Image.new('RGB', (1080, 1920), color='green')
    path = tmp_path / 'vertical.jpg'
    img.save(path, 'JPEG')
    return path


def test_instagram_specs(large_image):
    """Test image processing for Instagram specs."""
    result = process_image(large_image, INSTAGRAM_SPECS)
    assert result.meets_requirements
    assert result.processed_size[0] <= INSTAGRAM_SPECS.max_image_dimensions[0]
    assert result.processed_size[1] <= INSTAGRAM_SPECS.max_image_dimensions[1]


def test_snapchat_specs_vertical(vertical_image):
    """Test Snapchat specs with vertical image."""
    result = process_image(vertical_image, SNAPCHAT_SPECS)
    assert result.meets_requirements
    assert result.processed_size[0] <= SNAPCHAT_SPECS.max_image_dimensions[0]
    assert result.processed_size[1] <= SNAPCHAT_SPECS.max_image_dimensions[1]


def test_onlyfans_specs(large_image):
    """Test OnlyFans specs (larger size limits)."""
    result = process_image(large_image, ONLYFANS_SPECS)
    assert result.meets_requirements
    # OnlyFans allows 4096x4096, so 3000x3000 should pass through
    assert result.processed_size[0] == 3000
    assert result.processed_size[1] == 3000


def test_fansly_specs(large_image):
    """Test Fansly specs (similar to OnlyFans)."""
    result = process_image(large_image, FANSLY_SPECS)
    assert result.meets_requirements
    assert result.processed_size[0] <= FANSLY_SPECS.max_image_dimensions[0]
    assert result.processed_size[1] <= FANSLY_SPECS.max_image_dimensions[1]


def test_fetlife_specs(large_image):
    """Test FetLife specs."""
    result = process_image(large_image, FETLIFE_SPECS)
    assert result.meets_requirements
    assert result.processed_size[0] <= FETLIFE_SPECS.max_image_dimensions[0]
    assert result.processed_size[1] <= FETLIFE_SPECS.max_image_dimensions[1]


def test_instagram_validation_webp_accepted(tmp_path):
    """Test that Instagram accepts WEBP — PIL auto-converts static images to a supported format."""
    img = Image.new('RGB', (100, 100), color='red')
    path = tmp_path / 'test.webp'
    img.save(path, 'WEBP')

    error = validate_image(path, INSTAGRAM_SPECS)
    assert error is None


def test_onlyfans_accepts_webp(tmp_path):
    """Test that OnlyFans accepts WEBP format."""
    img = Image.new('RGB', (100, 100), color='red')
    path = tmp_path / 'test.webp'
    img.save(path, 'WEBP')

    error = validate_image(path, ONLYFANS_SPECS)
    assert error is None


def test_snapchat_no_text_length_limit():
    """Test that Snapchat has no text length limit."""
    assert SNAPCHAT_SPECS.max_text_length is None


def test_fetlife_no_text_length_limit():
    """Test that FetLife has no text length limit."""
    assert FETLIFE_SPECS.max_text_length is None
