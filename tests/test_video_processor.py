"""Tests for video processing."""

import subprocess
from pathlib import Path

import pytest

from src.core.video_processor import (
    extract_thumbnail,
    get_ffmpeg_path,
    get_video_info,
    process_video,
    validate_video,
)
from src.utils.constants import BLUESKY_SPECS, TWITTER_SPECS


def _make_test_video(path: Path, width=320, height=240, duration=2, fps=10):
    """Create a minimal test video using ffmpeg."""
    ffmpeg = get_ffmpeg_path()
    subprocess.run(
        [
            ffmpeg,
            '-y',
            '-f',
            'lavfi',
            '-i',
            f'color=c=red:size={width}x{height}:rate={fps}:d={duration}',
            '-f',
            'lavfi',
            '-i',
            'anullsrc=r=44100:cl=mono',
            '-t',
            str(duration),
            '-c:v',
            'libx264',
            '-crf',
            '28',
            '-preset',
            'ultrafast',
            '-c:a',
            'aac',
            '-b:a',
            '32k',
            '-shortest',
            str(path),
        ],
        capture_output=True,
        timeout=30,
    )
    return path


@pytest.fixture
def small_mp4(tmp_path):
    """Create a small MP4 test video."""
    return _make_test_video(tmp_path / 'small.mp4')


@pytest.fixture
def large_mp4(tmp_path):
    """Create a larger resolution MP4 test video."""
    return _make_test_video(tmp_path / 'large.mp4', width=2560, height=1440, duration=2)


class TestGetFfmpegPath:
    def test_returns_valid_path(self):
        path = get_ffmpeg_path()
        assert Path(path).exists()


class TestGetVideoInfo:
    def test_reads_dimensions(self, small_mp4):
        info = get_video_info(small_mp4)
        assert info.width == 320
        assert info.height == 240

    def test_reads_duration(self, small_mp4):
        info = get_video_info(small_mp4)
        assert info.duration_seconds >= 1.5

    def test_reads_codec(self, small_mp4):
        info = get_video_info(small_mp4)
        assert info.codec == 'h264'

    def test_reads_file_size(self, small_mp4):
        info = get_video_info(small_mp4)
        assert info.file_size == small_mp4.stat().st_size


class TestValidateVideo:
    def test_valid_mp4(self, small_mp4):
        assert validate_video(small_mp4, TWITTER_SPECS) is None

    def test_missing_file(self, tmp_path):
        missing = tmp_path / 'nonexistent.mp4'
        assert validate_video(missing, TWITTER_SPECS) == 'VID-NOT-FOUND'

    def test_unsupported_format(self, tmp_path):
        # Create a file with wrong extension
        bad = tmp_path / 'bad.avi'
        bad.write_bytes(b'fake')
        assert validate_video(bad, TWITTER_SPECS) == 'VID-INVALID-FORMAT'

    def test_corrupt_file(self, tmp_path):
        corrupt = tmp_path / 'corrupt.mp4'
        corrupt.write_bytes(b'not a video')
        assert validate_video(corrupt, TWITTER_SPECS) == 'VID-CORRUPT'


class TestProcessVideo:
    def test_small_video_passes_through(self, small_mp4):
        result = process_video(small_mp4, TWITTER_SPECS)
        assert result.meets_requirements
        assert result.path.exists()

    def test_large_video_resized(self, large_mp4):
        result = process_video(large_mp4, TWITTER_SPECS)
        assert result.meets_requirements
        assert result.processed_info.width <= TWITTER_SPECS.max_video_dimensions[0]
        assert result.processed_info.height <= TWITTER_SPECS.max_video_dimensions[1]

    def test_output_is_mp4(self, small_mp4):
        result = process_video(small_mp4, BLUESKY_SPECS)
        assert result.path.suffix == '.mp4' or result.path == small_mp4

    def test_progress_callback_called(self, small_mp4):
        progress_values = []
        result = process_video(small_mp4, TWITTER_SPECS, progress_cb=progress_values.append)
        assert result.meets_requirements
        assert 0 in progress_values
        assert 100 in progress_values


class TestExtractThumbnail:
    def test_extracts_first_frame(self, small_mp4):
        thumb = extract_thumbnail(small_mp4)
        assert thumb is not None
        assert thumb.exists()
        assert thumb.suffix == '.png'

    def test_returns_none_on_failure(self, tmp_path):
        bad = tmp_path / 'bad.mp4'
        bad.write_bytes(b'not a video')
        assert extract_thumbnail(bad) is None
