"""Tests for video processing."""

import subprocess
from pathlib import Path

import pytest
from PIL import Image

import src.core.video_processor as video_processor
from src.core.video_processor import (
    VideoInfo,
    _run_subprocess,
    convert_image_to_video,
    convert_images_to_video_slideshow,
    extract_thumbnail,
    get_ffmpeg_path,
    get_ffmpeg_version,
    get_video_info,
    process_video,
    validate_video,
)
from src.utils.constants import BLUESKY_SPECS, ONLYFANS_SPECS, SNAPCHAT_SPECS, TWITTER_SPECS


def _make_test_video(path: Path, width=320, height=240, duration=2, fps=10):
    """Create a minimal test video using ffmpeg."""
    ffmpeg = get_ffmpeg_path()
    _run_subprocess(
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


class TestGetFfmpegVersion:
    def test_parses_version(self, monkeypatch):
        monkeypatch.setattr('src.core.video_processor.get_ffmpeg_path', lambda: '/tmp/ffmpeg.exe')
        monkeypatch.setattr(
            subprocess,
            'run',
            lambda *_args, **_kwargs: subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout='ffmpeg version 7.1.1-custom Copyright\n',
                stderr='',
            ),
        )
        assert get_ffmpeg_version() == '7.1.1-custom'

    def test_returns_unknown_on_failure(self, monkeypatch):
        monkeypatch.setattr(
            'src.core.video_processor.get_ffmpeg_path',
            lambda: (_ for _ in ()).throw(RuntimeError('missing')),
        )
        assert get_ffmpeg_version() == 'unknown'


class TestRunSubprocess:
    def test_windows_uses_hidden_process_flags(self, monkeypatch):
        seen = {}

        class DummyStartupInfo:
            def __init__(self):
                self.dwFlags = 0
                self.wShowWindow = 0

        monkeypatch.setattr(video_processor.sys, 'platform', 'win32')
        monkeypatch.setattr(
            video_processor.subprocess, 'CREATE_NO_WINDOW', 0x08000000, raising=False
        )
        monkeypatch.setattr(
            video_processor.subprocess, 'STARTUPINFO', DummyStartupInfo, raising=False
        )
        monkeypatch.setattr(
            video_processor.subprocess, 'STARTF_USESHOWWINDOW', 0x00000001, raising=False
        )
        monkeypatch.setattr(video_processor.subprocess, 'SW_HIDE', 0, raising=False)

        def fake_run(cmd, **kwargs):
            seen['cmd'] = cmd
            seen['kwargs'] = kwargs
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout='', stderr='')

        monkeypatch.setattr(video_processor.subprocess, 'run', fake_run)

        _run_subprocess(['ffmpeg', '-version'], timeout=5)

        assert seen['cmd'] == ['ffmpeg', '-version']
        assert seen['kwargs']['creationflags'] == 0x08000000
        assert seen['kwargs']['capture_output'] is True
        assert seen['kwargs']['text'] is True
        assert seen['kwargs']['timeout'] == 5
        assert isinstance(seen['kwargs']['startupinfo'], DummyStartupInfo)


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

    def test_reads_frame_rate(self, small_mp4):
        info = get_video_info(small_mp4)
        assert info.frame_rate is None or info.frame_rate > 0


class TestValidateVideo:
    def test_valid_mp4(self, small_mp4):
        assert validate_video(small_mp4, TWITTER_SPECS) is None

    def test_missing_file(self, tmp_path):
        missing = tmp_path / 'nonexistent.mp4'
        assert validate_video(missing, TWITTER_SPECS) == 'VID-NOT-FOUND'

    def test_convertible_format_not_rejected(self, tmp_path):
        # AVI passes format check for Twitter (MP4-supporting platform) — ffmpeg converts it.
        # The fake content causes a corruption error, not a format error.
        bad = tmp_path / 'bad.avi'
        bad.write_bytes(b'fake')
        assert validate_video(bad, TWITTER_SPECS) == 'VID-CORRUPT'

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

    def test_supported_video_within_limits_skips_reencode(self, tmp_path, monkeypatch):
        source = tmp_path / 'clip.mov'
        source.write_bytes(b'video-bytes')

        info = VideoInfo(
            width=1280,
            height=720,
            duration_seconds=30.0,
            codec='hevc',
            file_size=3 * 1024 * 1024,
            format_name='mov',
        )
        monkeypatch.setattr('src.core.video_processor.get_video_info', lambda _path: info)
        monkeypatch.setattr(
            'src.core.video_processor._run_subprocess',
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError('ffmpeg should not run for no-op processing')
            ),
        )

        result = process_video(source, ONLYFANS_SPECS)

        assert result.path == source
        assert result.processed_info == info
        assert result.meets_requirements

    def test_snapchat_landscape_crop_mode_uses_crop_filter(self, tmp_path, monkeypatch):
        source = tmp_path / 'landscape.mp4'
        source.write_bytes(b'video-bytes')
        commands: list[list[str]] = []

        source_info = VideoInfo(
            width=640,
            height=360,
            duration_seconds=12.0,
            codec='h264',
            file_size=4 * 1024 * 1024,
            format_name='mp4',
        )
        processed_info = VideoInfo(
            width=202,
            height=360,
            duration_seconds=12.0,
            codec='h264',
            file_size=2 * 1024 * 1024,
            format_name='mp4',
        )

        def fake_info(path: Path):
            return source_info if path == source else processed_info

        def fake_run(cmd: list[str], timeout: int):
            commands.append(cmd)
            Path(cmd[-1]).write_bytes(b'processed-bytes')
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout='', stderr='')

        monkeypatch.setattr('src.core.video_processor.get_video_info', fake_info)
        monkeypatch.setattr('src.core.video_processor._run_subprocess', fake_run)

        result = process_video(source, SNAPCHAT_SPECS, snapchat_landscape_mode='crop')

        assert result.path != source
        assert commands
        vf = commands[0][commands[0].index('-vf') + 1]
        assert 'crop=' in vf
        assert 'transpose' not in vf

    def test_snapchat_landscape_rotate_mode_uses_rotate_filter(self, tmp_path, monkeypatch):
        source = tmp_path / 'landscape.mp4'
        source.write_bytes(b'video-bytes')
        commands: list[list[str]] = []

        source_info = VideoInfo(
            width=640,
            height=360,
            duration_seconds=12.0,
            codec='h264',
            file_size=4 * 1024 * 1024,
            format_name='mp4',
        )
        processed_info = VideoInfo(
            width=360,
            height=640,
            duration_seconds=12.0,
            codec='h264',
            file_size=2 * 1024 * 1024,
            format_name='mp4',
        )

        def fake_info(path: Path):
            return source_info if path == source else processed_info

        def fake_run(cmd: list[str], timeout: int):
            commands.append(cmd)
            Path(cmd[-1]).write_bytes(b'processed-bytes')
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout='', stderr='')

        monkeypatch.setattr('src.core.video_processor.get_video_info', fake_info)
        monkeypatch.setattr('src.core.video_processor._run_subprocess', fake_run)

        result = process_video(source, SNAPCHAT_SPECS, snapchat_landscape_mode='rotate')

        assert result.path != source
        assert commands
        vf = commands[0][commands[0].index('-vf') + 1]
        assert 'transpose=1' in vf

    def test_snapchat_vertical_source_skips_reencode(self, tmp_path, monkeypatch):
        source = tmp_path / 'vertical.mp4'
        source.write_bytes(b'video-bytes')
        info = VideoInfo(
            width=360,
            height=640,
            duration_seconds=15.0,
            codec='h264',
            file_size=3 * 1024 * 1024,
            format_name='mp4',
        )
        monkeypatch.setattr('src.core.video_processor.get_video_info', lambda _path: info)
        monkeypatch.setattr(
            'src.core.video_processor._run_subprocess',
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError('ffmpeg should not run for already-vertical Snapchat video')
            ),
        )

        result = process_video(source, SNAPCHAT_SPECS, snapchat_landscape_mode='rotate')

        assert result.path == source
        assert result.processed_info == info
        assert result.meets_requirements


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


class TestConvertImageToVideo:
    def test_static_image_converts_to_mp4(self, tmp_path):
        image_path = tmp_path / 'still.png'
        img = Image.new('RGB', (800, 1200), color='purple')
        img.save(image_path, 'PNG')

        output = convert_image_to_video(image_path, SNAPCHAT_SPECS, duration_seconds=3)
        info = get_video_info(output)

        assert output.exists()
        assert output.suffix == '.mp4'
        assert info.duration_seconds >= 2.5
        assert info.width <= SNAPCHAT_SPECS.max_video_dimensions[0]
        assert info.height <= SNAPCHAT_SPECS.max_video_dimensions[1]

    def test_snapchat_landscape_crop_mode_uses_crop_filter(self, tmp_path, monkeypatch):
        image_path = tmp_path / 'landscape.png'
        Image.new('RGB', (1600, 900), color='blue').save(image_path, 'PNG')
        commands: list[list[str]] = []

        monkeypatch.setattr('src.core.video_processor.get_ffmpeg_path', lambda: '/tmp/ffmpeg')

        def fake_run(cmd: list[str], timeout: int):
            commands.append(cmd)
            Path(cmd[-1]).write_bytes(b'mp4')
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout='', stderr='')

        monkeypatch.setattr('src.core.video_processor._run_subprocess', fake_run)

        output = convert_image_to_video(
            image_path,
            SNAPCHAT_SPECS,
            duration_seconds=2,
            snapchat_landscape_mode='crop',
        )

        assert output.exists()
        assert commands
        vf = commands[0][commands[0].index('-vf') + 1]
        assert 'crop=' in vf
        assert 'transpose=' not in vf

    def test_snapchat_landscape_rotate_mode_uses_transpose_filter(self, tmp_path, monkeypatch):
        image_path = tmp_path / 'landscape.png'
        Image.new('RGB', (1600, 900), color='green').save(image_path, 'PNG')
        commands: list[list[str]] = []

        monkeypatch.setattr('src.core.video_processor.get_ffmpeg_path', lambda: '/tmp/ffmpeg')

        def fake_run(cmd: list[str], timeout: int):
            commands.append(cmd)
            Path(cmd[-1]).write_bytes(b'mp4')
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout='', stderr='')

        monkeypatch.setattr('src.core.video_processor._run_subprocess', fake_run)

        output = convert_image_to_video(
            image_path,
            SNAPCHAT_SPECS,
            duration_seconds=2,
            snapchat_landscape_mode='rotate',
        )

        assert output.exists()
        assert commands
        vf = commands[0][commands[0].index('-vf') + 1]
        assert 'transpose=1' in vf


class TestConvertImagesToVideoSlideshow:
    def test_slideshow_conversion_uses_xfade_and_runs_post_processing(self, tmp_path, monkeypatch):
        image_1 = tmp_path / 'img1.png'
        image_2 = tmp_path / 'img2.png'
        Image.new('RGB', (900, 1200), color='red').save(image_1, 'PNG')
        Image.new('RGB', (900, 1200), color='yellow').save(image_2, 'PNG')

        seen = {}
        source_info = VideoInfo(
            width=900,
            height=1200,
            duration_seconds=5.0,
            codec='h264',
            file_size=2 * 1024 * 1024,
            format_name='mp4',
        )

        monkeypatch.setattr('src.core.video_processor.get_ffmpeg_path', lambda: '/tmp/ffmpeg')

        def fake_run(cmd: list[str], timeout: int):
            seen['cmd'] = cmd
            Path(cmd[-1]).write_bytes(b'mp4')
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout='', stderr='')

        def fake_process_video(path: Path, specs, progress_cb=None, snapchat_landscape_mode=None):
            seen['processed_path'] = path
            seen['mode'] = snapchat_landscape_mode
            return video_processor.ProcessedVideo(
                path=path,
                original_info=source_info,
                processed_info=source_info,
                meets_requirements=True,
            )

        monkeypatch.setattr('src.core.video_processor._run_subprocess', fake_run)
        monkeypatch.setattr('src.core.video_processor.process_video', fake_process_video)

        output = convert_images_to_video_slideshow(
            [image_1, image_2],
            SNAPCHAT_SPECS,
            snapchat_landscape_mode='rotate',
        )

        assert output.exists()
        assert 'xfade=' in ' '.join(seen['cmd'])
        assert seen['processed_path'] == output
        assert seen['mode'] == 'rotate'


class TestParseFrameRate:
    def test_handles_fraction_and_float(self):
        assert video_processor._parse_frame_rate('30000/1001') == pytest.approx(29.97003, rel=1e-4)
        assert video_processor._parse_frame_rate('24') == 24.0

    def test_handles_empty_and_invalid_values(self):
        assert video_processor._parse_frame_rate(None) is None
        assert video_processor._parse_frame_rate('') is None
        assert video_processor._parse_frame_rate('0') is None
        assert video_processor._parse_frame_rate('0/0') is None
        assert video_processor._parse_frame_rate('30/0') is None
        assert video_processor._parse_frame_rate('not-a-rate') is None


class TestGetFfmpegVersionEdgeCases:
    def test_returns_unknown_when_version_output_empty(self, monkeypatch):
        monkeypatch.setattr('src.core.video_processor.get_ffmpeg_path', lambda: '/tmp/ffmpeg.exe')
        monkeypatch.setattr(
            'src.core.video_processor._run_subprocess',
            lambda *_args, **_kwargs: subprocess.CompletedProcess(
                args=[], returncode=0, stdout='', stderr=''
            ),
        )
        assert get_ffmpeg_version() == 'unknown'


class TestGetVideoInfoEdgeCases:
    def test_uses_ffprobe_json_when_available(self, tmp_path, monkeypatch):
        video = tmp_path / 'clip.mp4'
        video.write_bytes(b'video-bytes')

        monkeypatch.setattr('src.core.video_processor.get_ffmpeg_path', lambda: '/tmp/ffmpeg')
        monkeypatch.setattr('src.core.video_processor.get_ffprobe_path', lambda: '/tmp/ffprobe')

        probe_json = {
            'streams': [
                {
                    'width': 1920,
                    'height': 1080,
                    'codec_name': 'h264',
                    'avg_frame_rate': '30000/1001',
                }
            ],
            'format': {'duration': '12.5', 'format_name': 'mov,mp4,m4a,3gp,3g2,mj2'},
        }

        monkeypatch.setattr(
            'src.core.video_processor._run_subprocess',
            lambda *_args, **_kwargs: subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=__import__('json').dumps(probe_json),
                stderr='',
            ),
        )

        info = get_video_info(video)

        assert info.width == 1920
        assert info.height == 1080
        assert info.duration_seconds == 12.5
        assert info.codec == 'h264'
        assert info.format_name == 'mp4'
        assert info.frame_rate == pytest.approx(29.97003, rel=1e-4)

    def test_timeout_is_raised(self, tmp_path, monkeypatch):
        video = tmp_path / 'clip.mp4'
        video.write_bytes(b'video-bytes')

        monkeypatch.setattr('src.core.video_processor.get_ffmpeg_path', lambda: '/tmp/ffmpeg')
        monkeypatch.setattr('src.core.video_processor.get_ffprobe_path', lambda: '/tmp/ffmpeg')
        monkeypatch.setattr(
            'src.core.video_processor._run_subprocess',
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                subprocess.TimeoutExpired(cmd='ffmpeg', timeout=30)
            ),
        )

        with pytest.raises(subprocess.TimeoutExpired):
            get_video_info(video)


class TestValidateVideoEdgeCases:
    def test_invalid_format_when_mp4_not_supported(self, tmp_path):
        webm_only = video_processor.PlatformSpecs(
            platform_name='WebmOnly',
            max_image_dimensions=(100, 100),
            max_file_size_mb=1.0,
            supported_formats=['PNG'],
            max_text_length=1,
            supported_video_formats=['WEBM'],
            max_video_dimensions=(640, 360),
            max_video_file_size_mb=5.0,
            max_video_duration_seconds=30,
        )
        mp4 = tmp_path / 'clip.mp4'
        mp4.write_bytes(b'not-real-video')

        assert validate_video(mp4, webm_only) == 'VID-INVALID-FORMAT'

    def test_too_long_and_too_large(self, tmp_path, monkeypatch):
        video = tmp_path / 'clip.mp4'
        video.write_bytes(b'video-bytes')

        long_info = VideoInfo(
            width=1280,
            height=720,
            duration_seconds=(TWITTER_SPECS.max_video_duration_seconds or 140) + 1,
            codec='h264',
            file_size=1024,
            format_name='mp4',
        )
        monkeypatch.setattr('src.core.video_processor.get_video_info', lambda _path: long_info)
        assert validate_video(video, TWITTER_SPECS) == 'VID-TOO-LONG'

        large_info = VideoInfo(
            width=1280,
            height=720,
            duration_seconds=10,
            codec='h264',
            file_size=int((TWITTER_SPECS.max_video_file_size_mb + 1) * 1024 * 1024),
            format_name='mp4',
        )
        monkeypatch.setattr('src.core.video_processor.get_video_info', lambda _path: large_info)
        assert validate_video(video, TWITTER_SPECS) == 'VID-TOO-LARGE'


class TestConvertImageToVideoEdgeCases:
    def test_raises_for_non_positive_duration(self, tmp_path):
        image_path = tmp_path / 'still.png'
        Image.new('RGB', (640, 480), color='purple').save(image_path, 'PNG')

        with pytest.raises(ValueError, match='duration_seconds must be greater than zero'):
            convert_image_to_video(image_path, SNAPCHAT_SPECS, duration_seconds=0)


class TestConvertImagesToVideoSlideshowEdgeCases:
    def test_rejects_invalid_arguments(self):
        with pytest.raises(ValueError, match='image_paths cannot be empty'):
            convert_images_to_video_slideshow([], SNAPCHAT_SPECS)

        with pytest.raises(ValueError, match='image_duration_seconds must be greater than zero'):
            convert_images_to_video_slideshow(
                [Path('a.png')], SNAPCHAT_SPECS, image_duration_seconds=0
            )

        with pytest.raises(ValueError, match='transition_seconds cannot be negative'):
            convert_images_to_video_slideshow(
                [Path('a.png')], SNAPCHAT_SPECS, transition_seconds=-1
            )

    def test_raises_when_source_dimensions_cannot_be_read(self, tmp_path):
        bad_image = tmp_path / 'bad.png'
        bad_image.write_bytes(b'not-an-image')

        with pytest.raises(RuntimeError, match='Could not read slideshow source image dimensions'):
            convert_images_to_video_slideshow([bad_image], SNAPCHAT_SPECS)

    def test_raises_when_ffmpeg_fails(self, tmp_path, monkeypatch):
        image_1 = tmp_path / 'img1.png'
        image_2 = tmp_path / 'img2.png'
        Image.new('RGB', (900, 1200), color='red').save(image_1, 'PNG')
        Image.new('RGB', (900, 1200), color='yellow').save(image_2, 'PNG')

        monkeypatch.setattr('src.core.video_processor.get_ffmpeg_path', lambda: '/tmp/ffmpeg')
        monkeypatch.setattr(
            'src.core.video_processor._run_subprocess',
            lambda cmd, timeout: subprocess.CompletedProcess(
                args=cmd, returncode=1, stdout='', stderr='boom'
            ),
        )

        with pytest.raises(RuntimeError, match='ffmpeg exited with code 1'):
            convert_images_to_video_slideshow([image_1, image_2], SNAPCHAT_SPECS)
