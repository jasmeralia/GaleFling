"""Functional test configuration — credential loading and skip-if-missing fixtures."""

import os

import pytest
from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(__file__), '.env')

# Module-level reference to QApplication to prevent garbage collection.
_qapp = None


def _has_display() -> bool:
    """Return True if a real display is available (Windows native, X11, or Wayland)."""
    import sys

    if sys.platform == 'win32':
        return True
    return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


def _running_from_network_path() -> bool:
    """Return True if the Python executable lives on a UNC/network path.

    Chromium refuses to launch QtWebEngineProcess with sandboxing enabled when
    the executable is on a network path (e.g. \\\\wsl.localhost\\... when running
    via PowerShell from WSL). --no-sandbox is required in that case.
    """
    import sys

    return sys.platform == 'win32' and sys.executable.startswith('\\\\')


def _is_collecting_functional_tests(config) -> bool:
    """Return True if functional test paths are in collection scope.

    Unit test runs (e.g. ``pytest tests/test_foo.py``) must not trigger
    WebEngine/Chromium initialisation — that requires GPU support that is
    not available in a plain devcontainer.  Functional tests require it and
    are always run explicitly against a display or in a GPU-capable environment.
    """
    args = list(getattr(config, 'args', None) or [])
    if not args:
        # No explicit paths → collect everything, which includes functional.
        return True
    return any('functional' in str(a) for a in args)


def pytest_configure(config):
    global _qapp
    load_dotenv(ENV_PATH)

    # Only initialise WebEngine / Chromium when functional tests are actually
    # being collected.  Unit tests must not depend on GPU availability.
    if not _is_collecting_functional_tests(config):
        return

    # Only fall back to offscreen when no display is available (CI, headless).
    # A real display (WSLg, Xvfb, native X) gives WebGL and full rendering.
    if not _has_display():
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        # Disable Chromium sandbox/GPU to prevent fatal abort in offscreen mode.
        os.environ.setdefault(
            'QTWEBENGINE_CHROMIUM_FLAGS',
            '--no-sandbox --disable-gpu --disable-software-rasterizer',
        )
    elif _running_from_network_path():
        # Chromium sandbox is incompatible with UNC network paths (e.g. WSL
        # filesystem accessed via \\wsl.localhost\...). Disable sandbox only;
        # GPU is still available since this is a native Windows process.
        os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--no-sandbox')

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


@pytest.fixture
def onlyfans_credentials():
    email = os.environ.get('ONLYFANS_EMAIL')
    password = os.environ.get('ONLYFANS_PASSWORD')
    if not email or not password:
        pytest.skip('OnlyFans credentials not configured')
    return {
        'email': email,
        'password': password,
        'totp_secret': os.environ.get('ONLYFANS_TOTP_SECRET'),
    }


@pytest.fixture
def fansly_credentials():
    email = os.environ.get('FANSLY_EMAIL')
    password = os.environ.get('FANSLY_PASSWORD')
    if not email or not password:
        pytest.skip('Fansly credentials not configured')
    return {'email': email, 'password': password}


@pytest.fixture
def fetlife_credentials():
    email = os.environ.get('FETLIFE_EMAIL')
    password = os.environ.get('FETLIFE_PASSWORD')
    if not email or not password:
        pytest.skip('FetLife credentials not configured')
    return {'email': email, 'password': password}


@pytest.fixture
def threads_credentials():
    username = os.environ.get('THREADS_USERNAME')
    password = os.environ.get('THREADS_PASSWORD')
    if not username or not password:
        pytest.skip('Threads credentials not configured')
    return {'username': username, 'password': password}


@pytest.fixture
def snapchat_credentials():
    username = os.environ.get('SNAPCHAT_USERNAME')
    password = os.environ.get('SNAPCHAT_PASSWORD')
    if not username or not password:
        pytest.skip('Snapchat credentials not configured')
    return {'username': username, 'password': password}
