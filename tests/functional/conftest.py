"""Functional test configuration — credential loading and skip-if-missing fixtures."""

import os

import pytest
from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(__file__), '.env')

# Module-level reference to QApplication to prevent garbage collection.
_qapp = None


def pytest_configure(config):
    global _qapp
    load_dotenv(ENV_PATH)
    # QWebEngineWidgets must be imported before any QApplication is created.
    # Set offscreen platform and import early so webview posting tests work.
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    # Disable Chromium sandbox/GPU to prevent fatal abort in WSL offscreen mode.
    os.environ.setdefault(
        'QTWEBENGINE_CHROMIUM_FLAGS', '--no-sandbox --disable-gpu --disable-software-rasterizer'
    )
    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QApplication

        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
        import PyQt6.QtWebEngineWidgets  # noqa: F401

        # Create QApplication early so Chromium initializes before tests run.
        if QApplication.instance() is None:
            _qapp = QApplication(['galefling_functional_tests'])
    except ImportError:
        pass


# ── Helper to create a small test image on disk ─────────────────────


@pytest.fixture
def sample_jpeg(tmp_path):
    """Create a small 100x100 red JPEG for upload tests."""
    from PIL import Image

    img = Image.new('RGB', (100, 100), color='red')
    path = tmp_path / 'test_image.jpg'
    img.save(str(path), 'JPEG', quality=85)
    return path


@pytest.fixture
def sample_png(tmp_path):
    """Create a small 100x100 blue PNG for upload tests."""
    from PIL import Image

    img = Image.new('RGB', (100, 100), color='blue')
    path = tmp_path / 'test_image.png'
    img.save(str(path), 'PNG')
    return path


@pytest.fixture
def oversized_jpeg(tmp_path):
    """Create a 5000x5000 JPEG that exceeds most platform dimension limits."""
    from PIL import Image

    img = Image.new('RGB', (5000, 5000), color='green')
    path = tmp_path / 'oversized.jpg'
    img.save(str(path), 'JPEG', quality=95)
    return path


@pytest.fixture
def sample_video(tmp_path):
    """Create a short 2-second test MP4 via ffmpeg."""
    from src.core.video_processor import get_ffmpeg_path

    ffmpeg = get_ffmpeg_path()
    output = tmp_path / 'test_video.mp4'
    import subprocess

    subprocess.run(
        [
            ffmpeg,
            '-y',
            '-f',
            'lavfi',
            '-i',
            'color=c=red:s=320x240:d=2',
            '-c:v',
            'libx264',
            '-pix_fmt',
            'yuv420p',
            '-an',
            str(output),
        ],
        capture_output=True,
        timeout=30,
    )
    return output


@pytest.fixture
def long_video(tmp_path):
    """Create a 10-second test MP4 to test duration trimming."""
    from src.core.video_processor import get_ffmpeg_path

    ffmpeg = get_ffmpeg_path()
    output = tmp_path / 'long_video.mp4'
    import subprocess

    subprocess.run(
        [
            ffmpeg,
            '-y',
            '-f',
            'lavfi',
            '-i',
            'color=c=blue:s=640x480:d=10',
            '-c:v',
            'libx264',
            '-pix_fmt',
            'yuv420p',
            '-an',
            str(output),
        ],
        capture_output=True,
        timeout=30,
    )
    return output


# ── Platform credential fixtures ─────────────────────────────────────


@pytest.fixture
def twitter_credentials():
    keys = [
        'TWITTER_API_KEY',
        'TWITTER_API_SECRET',
        'TWITTER_ACCESS_TOKEN',
        'TWITTER_ACCESS_TOKEN_SECRET',
    ]
    creds = {k: os.environ.get(k) for k in keys}
    if not all(creds.values()):
        pytest.skip('Twitter credentials not configured')
    return creds


@pytest.fixture
def bluesky_credentials():
    creds = {
        'identifier': os.environ.get('BLUESKY_IDENTIFIER'),
        'app_password': os.environ.get('BLUESKY_APP_PASSWORD'),
    }
    if not all(creds.values()):
        pytest.skip('Bluesky credentials not configured')
    return creds


@pytest.fixture
def instagram_credentials():
    creds = {
        'access_token': os.environ.get('INSTAGRAM_ACCESS_TOKEN'),
        'account_id': os.environ.get('INSTAGRAM_BUSINESS_ACCOUNT_ID'),
        'page_id': os.environ.get('INSTAGRAM_PAGE_ID'),
    }
    if not all(creds.values()):
        pytest.skip('Instagram credentials not configured')
    return creds


@pytest.fixture
def galefling_data_dir():
    data_dir = os.environ.get('GALEFLING_DATA_DIR')
    if not data_dir:
        pytest.skip('GALEFLING_DATA_DIR not configured')
    from pathlib import Path

    path = Path(data_dir)
    if not path.is_dir():
        pytest.skip(f'GALEFLING_DATA_DIR does not exist: {data_dir}')
    return path
