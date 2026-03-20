"""Shared helpers for WebView functional tests.

Provides QWebEngineView creation, page loading, JS execution, and event loop
utilities used by the per-platform webview posting test modules.
"""

import contextlib
from pathlib import Path

from PyQt6.QtCore import QEventLoop, QTimer, QUrl
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication


def get_or_create_app():
    """Return existing QApplication or create one."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(['galefling_functional_test'])
    return app


def wait_ms(ms: int):
    """Block the event loop for the given number of milliseconds."""
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(ms)
    loop.exec()


def load_page(page: QWebEnginePage, url: str, timeout_ms: int = 15000) -> tuple[bool, str]:
    """Load a URL and wait for it to finish. Returns (ok, final_url)."""
    state: dict = {'loaded': False, 'ok': False}

    def on_load(ok):
        state['loaded'] = True
        state['ok'] = ok

    page.loadFinished.connect(on_load)

    loop = QEventLoop()
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)

    check = QTimer()
    check.setInterval(300)
    check.timeout.connect(lambda: loop.quit() if state['loaded'] else None)
    check.start()

    page.load(QUrl(url))
    timeout.start(timeout_ms)
    loop.exec()
    check.stop()
    timeout.stop()

    with contextlib.suppress(TypeError, RuntimeError):
        page.loadFinished.disconnect(on_load)

    return state['ok'], page.url().toString()


def run_js(page: QWebEnginePage, js: str, timeout_ms: int = 5000):
    """Execute JavaScript and return the result synchronously."""
    state: dict = {'done': False, 'value': None}

    def callback(value):
        state['done'] = True
        state['value'] = value

    page.runJavaScript(js, callback)

    loop = QEventLoop()
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)

    check = QTimer()
    check.setInterval(200)
    check.timeout.connect(lambda: loop.quit() if state['done'] else None)
    check.start()

    timeout.start(timeout_ms)
    loop.exec()
    check.stop()
    timeout.stop()

    return state['value']


def create_webview(data_dir: Path, account_id: str):
    """Create a QWebEngineView with persistent cookies from the given profile.

    Uses the same profile name and storage path as the app so that Chromium loads
    the full persisted browser context (including Cloudflare fingerprint state) from
    prior app sessions.  The app must NOT be running simultaneously — Chromium holds
    an exclusive SQLite WAL lock on the cookie database.
    """
    storage = data_dir / 'webprofiles' / account_id
    # Use the same profile name as the app (_get_profile_storage_path returns
    # get_app_data_dir() / 'webprofiles' / account_id and passes .name to
    # QWebEngineProfile).  A different name creates a fresh Chromium context with
    # no Cloudflare session state, causing re-challenges on protected sites.
    profile = QWebEngineProfile(account_id, None)
    profile.setPersistentStoragePath(str(storage))
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
    )
    page = QWebEnginePage(profile)
    view = QWebEngineView()
    view.setPage(page)
    view.resize(1280, 900)
    view.show()
    return view, page, profile


def has_cookie_db(data_dir: Path, account_id: str) -> bool:
    """Check whether a cookie database exists for the given account."""
    return (data_dir / 'webprofiles' / account_id / 'Cookies').exists()
