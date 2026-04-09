import os
import sys


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
