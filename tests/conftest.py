import os
import sys
import tempfile

import pytest


@pytest.fixture(autouse=True, scope='session')
def _redirect_ad_hoc_tempfile_dir(tmp_path_factory):
    """Redirect tempfile.NamedTemporaryFile()/mkstemp() (no explicit dir=) into
    pytest's own managed temp area for the whole session.

    Several production code paths (image_processor.py, video_processor.py)
    create real images/videos via `tempfile.NamedTemporaryFile(delete=False)`
    without an explicit `dir=`, so they land in the shared OS temp dir where
    nothing ever cleans them up — unlike pytest's own `tmp_path`, which is
    rotated automatically (last 3 runs kept). Setting `tempfile.tempdir`
    redirects any such call for the rest of the process into a location
    pytest already manages, without touching the calling code.
    """
    shared_dir = tmp_path_factory.mktemp('shared_tempfile_dir', numbered=False)
    original = tempfile.tempdir
    tempfile.tempdir = str(shared_dir)
    yield
    tempfile.tempdir = original


def pytest_configure():
    _no_display = (
        sys.platform == 'linux'
        and not os.environ.get('DISPLAY')
        and not os.environ.get('WAYLAND_DISPLAY')
    )
    _is_ci = os.environ.get('GITHUB_ACTIONS') == 'true' or os.environ.get('CI') == 'true'

    if _is_ci or _no_display:
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

    # When running without a GPU (CI, devcontainer, headless Linux), disable the
    # Chromium sandbox and GPU acceleration so that importing QtWebEngineWidgets
    # does not cause a fatal abort when QApplication is created.  Unit tests do
    # not use WebEngine at all, but some GUI modules import base_webview at
    # module level, which loads the WebEngine Qt module into the process.
    if _is_ci or _no_display or _is_container():
        os.environ.setdefault(
            'QTWEBENGINE_CHROMIUM_FLAGS',
            '--no-sandbox --disable-gpu --disable-software-rasterizer',
        )

    # Qt requires this before the QApplication exists, or any later import of
    # QtWebEngineWidgets raises ImportError.  Several GUI modules import
    # WebEngine lazily inside a handler, so without this a test file passes or
    # fails depending on whether some *other* file happened to import WebEngine
    # earlier in the session — `pytest tests/` passed while
    # `pytest tests/test_settings_dialog.py` did not.
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)


def _is_container() -> bool:
    """Return True when running inside a container (Docker / devcontainer)."""
    # /.dockerenv is created by Docker; cgroup v2 controllers list 'docker' or 'containerd'.
    if os.path.exists('/.dockerenv'):
        return True
    try:
        with open('/proc/1/cgroup') as fh:
            return any(kw in fh.read() for kw in ('docker', 'containerd', 'lxc'))
    except OSError:
        return False
