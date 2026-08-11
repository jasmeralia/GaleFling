"""Functional test configuration — credentials and strict failure reporting."""

import os
from functools import wraps

import pytest
from dotenv import load_dotenv


def _resolve_env_path() -> str:
    """Return the credential file path, honouring an explicit override.

    The Windows VM runs the suite from a copy of the repository because pytest
    cannot scan the VirtIO-FS share, but credentials deliberately stay on the
    host share rather than being written to the guest disk (where a snapshot
    would preserve them).  The override lets the two live in different places.
    """
    override = os.environ.get('GALEFLING_FUNCTIONAL_ENV')
    if override:
        return override
    return os.path.join(os.path.dirname(__file__), '.env')


ENV_PATH = _resolve_env_path()

# Module-level reference to QApplication to prevent garbage collection.
_qapp = None
_STRICT_FUNCTIONAL = False


def _strict_functional_enabled() -> bool:
    """Return whether functional defects should fail instead of skip."""
    return bool(os.environ.get('GALEFLING_STRICT_FUNCTIONAL'))


@pytest.fixture(scope='session', autouse=True)
def strict_functional() -> bool:
    """Report whether this functional test session uses strict outcomes."""
    global _STRICT_FUNCTIONAL
    _STRICT_FUNCTIONAL = _strict_functional_enabled()
    return _STRICT_FUNCTIONAL


def fail_or_skip(reason: str) -> None:
    """Fail in strict mode, retaining the legacy skip behavior otherwise."""
    if _STRICT_FUNCTIONAL:
        pytest.fail(reason, pytrace=False)
    pytest.skip(reason)


class _RendererCrashMonitor:
    """Record renderer terminations from every WebEngine page seen by a test."""

    def __init__(self) -> None:
        self._page_ids: set[int] = set()
        self.crashes: list[str] = []

    def watch(self, page) -> None:
        """Attach to a page once, if it exposes the renderer termination signal."""
        page_id = id(page)
        if page_id in self._page_ids:
            return

        signal = getattr(page, 'renderProcessTerminated', None)
        if signal is None:
            return

        self._page_ids.add(page_id)

        def on_terminated(status, exit_code, watched_page=page) -> None:
            status_name = getattr(status, 'name', str(status))
            try:
                url = watched_page.url().toString()
            except RuntimeError:
                url = '<page deleted>'
            self.crashes.append(
                f'status={status_name}, exit_code={exit_code}, url={url or "<empty>"}'
            )

        signal.connect(on_terminated)

    def fail_if_crashed(self) -> None:
        """Fail the current test when a watched renderer terminated."""
        if self.crashes:
            pytest.fail(
                'WebEngine renderer process terminated: ' + '; '.join(self.crashes),
                pytrace=False,
            )


@pytest.fixture(autouse=True)
def fail_on_renderer_crash(request, monkeypatch):
    """Fail a functional test if any WebEngine renderer terminates during it."""
    monitor = _RendererCrashMonitor()

    # Existing WebView tests import create_webview directly, so wrap the alias in
    # the test module and attach before the helper returns control to the test.
    create_webview = getattr(request.module, 'create_webview', None)
    if callable(create_webview):

        @wraps(create_webview)
        def monitored_create_webview(*args, **kwargs):
            result = create_webview(*args, **kwargs)
            if isinstance(result, tuple) and len(result) > 1:
                monitor.watch(result[1])
            return result

        monkeypatch.setattr(request.module, 'create_webview', monitored_create_webview)

    # Also discover pages created outside the shared helper. The timer runs as
    # soon as a WebEngine test enters a Qt event loop.
    timer = None
    try:
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtWidgets import QApplication

        def watch_open_views() -> None:
            app = QApplication.instance()
            if app is None:
                return
            for widget in app.allWidgets():
                if isinstance(widget, QWebEngineView):
                    monitor.watch(widget.page())

        watch_open_views()
        timer = QTimer()
        timer.setInterval(50)
        timer.timeout.connect(watch_open_views)
        timer.start()
    except ImportError:
        pass

    yield

    if timer is not None:
        timer.stop()
    monitor.fail_if_crashed()


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

    from src.core.webview_environment import disable_conditional_passkey_ui

    disable_conditional_passkey_ui()

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


def pytest_collection_modifyitems(items) -> None:
    """Require every functional test to declare exactly one side-effect group."""
    errors = []
    for item in items:
        if item.get_closest_marker('functional') is None:
            continue
        groups = [
            name
            for name in ('non_mutating', 'mutating')
            if item.get_closest_marker(name) is not None
        ]
        if len(groups) != 1:
            rendered = ', '.join(groups) if groups else 'none'
            errors.append(f'{item.nodeid} ({rendered})')
    if errors:
        pytest.exit(
            'Functional tests must have exactly one side-effect marker:\n' + '\n'.join(errors),
            returncode=4,
        )


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
    }
    if not all(creds.values()):
        pytest.skip('Instagram credentials not configured')
    return creds


@pytest.fixture
def meta_aws_credentials():
    """AWS S3 staging credentials shared by Instagram and Threads for media posts."""
    bucket = os.environ.get('META_AWS_BUCKET')
    creds = {
        'access_key_id': os.environ.get('META_AWS_ACCESS_KEY_ID'),
        'secret_access_key': os.environ.get('META_AWS_SECRET_ACCESS_KEY'),
        'region': os.environ.get('META_AWS_REGION', 'us-west-2'),
        'bucket': bucket,
        'media_staging_bucket': bucket,
    }
    if not all([creds['access_key_id'], creds['secret_access_key'], creds['bucket']]):
        pytest.skip('Meta AWS media staging credentials not configured')
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
def meta_threads_credentials():
    creds = {
        'access_token': os.environ.get('META_THREADS_ACCESS_TOKEN'),
        'user_id': os.environ.get('META_THREADS_USER_ID'),
    }
    if not all(creds.values()):
        pytest.skip('Meta Threads credentials not configured')
    return creds


@pytest.fixture
def meta_facebook_credentials():
    creds = {
        'page_access_token': os.environ.get('META_FACEBOOK_PAGE_ACCESS_TOKEN'),
        'page_id': os.environ.get('META_FACEBOOK_PAGE_ID'),
    }
    if not all(creds.values()):
        pytest.skip('Meta Facebook Page credentials not configured')
    return creds


@pytest.fixture
def snapchat_credentials():
    username = os.environ.get('SNAPCHAT_USERNAME')
    password = os.environ.get('SNAPCHAT_PASSWORD')
    if not username or not password:
        pytest.skip('Snapchat credentials not configured')
    return {'username': username, 'password': password}
