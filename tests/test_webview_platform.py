"""Tests for WebView platform infrastructure."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace

from PyQt6.QtCore import QUrl

from src.platforms.base_webview import BaseWebViewPlatform
from src.utils.constants import PlatformSpecs


class DummySignal:
    def __init__(self):
        self._callbacks = []

    def connect(self, callback):
        self._callbacks.append(callback)

    def disconnect(self, callback):
        try:
            self._callbacks.remove(callback)
        except ValueError as exc:
            raise TypeError('callback not connected') from exc

    def emit(self, *args, **kwargs):
        for callback in list(self._callbacks):
            callback(*args, **kwargs)


class DummyLogger:
    def __init__(self, *, debug_enabled=True):
        self.debug_messages = []
        self.info_messages = []
        self.warning_messages = []
        self.error_messages = []
        self.debug_enabled = debug_enabled

    def isEnabledFor(self, _level):  # noqa: N802
        return self.debug_enabled

    def debug(self, message, *_args, **_kwargs):
        self.debug_messages.append(message)

    def info(self, message, *_args, **_kwargs):
        self.info_messages.append(message)

    def warning(self, message, *_args, **_kwargs):
        self.warning_messages.append(message)

    def error(self, message, *_args, **_kwargs):
        self.error_messages.append(message)


class DummyPage:
    scenario = 'success'
    redirect_url = 'https://example.com/login'

    def __init__(self, _profile=None, _platform=None, _parent=None):
        self.urlChanged = DummySignal()
        self.loadStarted = DummySignal()
        self.loadProgress = DummySignal()
        self.loadFinished = DummySignal()
        self.renderProcessTerminated = DummySignal()
        self.windowCloseRequested = DummySignal()
        self.renderProcessPidChanged = DummySignal()
        self.timeout = DummySignal()
        self._url = QUrl()
        self.js_calls = []
        self.deleted = False
        self.load_finished_callbacks = []

    def load(self, url: QUrl):
        self._url = url
        if self.scenario == 'success':
            self.urlChanged.emit(url)
            self.loadFinished.emit(True)
            return
        if self.scenario == 'login_redirect':
            self._url = QUrl(self.redirect_url)
            self.urlChanged.emit(self._url)
            self.loadFinished.emit(True)
            return
        if self.scenario == 'load_fail':
            self.urlChanged.emit(url)
            self.loadFinished.emit(False)

    def url(self):
        return self._url

    def runJavaScript(self, script, callback=None):  # noqa: N802
        self.js_calls.append(script)
        if callback is not None:
            callback({'success': True, 'url': 'https://example.com/post/123'})

    def deleteLater(self):  # noqa: N802
        self.deleted = True


class DummyView:
    def __init__(self, _parent=None):
        self._page = None
        self.renderProcessTerminated = DummySignal()
        self.loaded_urls = []

    def setPage(self, page):  # noqa: N802
        self._page = page

    def page(self):
        return self._page

    def load(self, url: QUrl):
        self.loaded_urls.append(url.toString())
        if self._page is not None:
            self._page.load(url)

    def url(self):
        if self._page is None:
            return QUrl()
        return self._page.url()


class DummyProfile:
    class PersistentCookiesPolicy:
        AllowPersistentCookies = object()

    def __init__(self, _name, _parent=None):
        self.storage_path = ''
        self.policy = None
        self.deleted = False
        # Mirrors Qt's default, which carries the QtWebEngine product token.
        self.user_agent = (
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
            'QtWebEngine/6.11.1 Chrome/140.0.0.0 Safari/537.36'
        )

    def httpUserAgent(self):  # noqa: N802
        return self.user_agent

    def setHttpUserAgent(self, value):  # noqa: N802
        self.user_agent = value

    def setPersistentStoragePath(self, value):  # noqa: N802
        self.storage_path = value

    def setPersistentCookiesPolicy(self, value):  # noqa: N802
        self.policy = value

    def deleteLater(self):  # noqa: N802
        self.deleted = True


class DummyEventLoop:
    def __init__(self):
        self._running = True

    def isRunning(self):  # noqa: N802
        return self._running

    def quit(self):
        self._running = False

    def exec(self):  # noqa: A003
        return 0


class DummyTimer:
    trigger_timeout = False

    def __init__(self):
        self.timeout = DummySignal()
        self.started = False
        self.interval_ms = None
        self.single_shot = False

    @staticmethod
    def singleShot(_delay, callback):  # noqa: N802
        """Fire the callback immediately (no real delay in tests)."""
        callback()

    def setSingleShot(self, value):  # noqa: N802
        self.single_shot = bool(value)

    def setInterval(self, value):  # noqa: N802
        self.interval_ms = value

    def start(self, _value=None):
        self.started = True
        if self.trigger_timeout:
            self.timeout.emit()

    def stop(self):
        self.started = False


class ConcreteWebViewPlatform(BaseWebViewPlatform):
    """Minimal concrete implementation for testing."""

    COMPOSER_URL = 'https://example.com/compose'
    TEXT_SELECTOR = 'textarea.composer'
    SUCCESS_URL_PATTERN = r'example\.com/post/\d+'
    COOKIE_DOMAINS = ['example.com']

    def get_platform_name(self) -> str:
        return 'TestPlatform'

    def get_specs(self) -> PlatformSpecs:
        return PlatformSpecs(
            platform_name='TestPlatform',
            max_image_dimensions=(1024, 1024),
            max_file_size_mb=5.0,
            supported_formats=['JPEG', 'PNG'],
            max_text_length=500,
            api_type='webview',
            auth_method='session_cookie',
            requires_user_confirm=True,
        )


def test_base_webview_platform_properties():
    platform = ConcreteWebViewPlatform(
        account_id='test_1',
        profile_name='testuser',
    )
    assert platform.account_id == 'test_1'
    assert platform.profile_name == 'testuser'
    assert platform.get_platform_name() == 'TestPlatform'
    assert platform.get_specs().api_type == 'webview'
    assert platform.get_specs().requires_user_confirm is True


def test_base_webview_authenticate_returns_ok():
    platform = ConcreteWebViewPlatform(account_id='test_1')
    success, error = platform.authenticate()
    assert success is True
    assert error is None


def test_base_webview_build_result_not_confirmed():
    platform = ConcreteWebViewPlatform(account_id='test_1', profile_name='user')
    result = platform.build_result()
    assert result.success is False
    assert result.error_code == 'WV-SUBMIT-TIMEOUT'
    assert result.user_confirmed is False
    assert result.account_id == 'test_1'
    assert result.profile_name == 'user'


def test_base_webview_build_result_confirmed_no_url():
    platform = ConcreteWebViewPlatform(account_id='test_1', profile_name='user')
    platform.mark_confirmed()
    result = platform.build_result()
    assert result.success is True
    assert result.post_url is None
    assert result.url_captured is False
    assert result.user_confirmed is True


def test_base_webview_build_result_confirmed_with_url():
    platform = ConcreteWebViewPlatform(account_id='test_1', profile_name='user')
    platform._post_confirmed = True
    platform._captured_post_url = 'https://example.com/post/12345'
    result = platform.build_result()
    assert result.success is True
    assert result.post_url == 'https://example.com/post/12345'
    assert result.url_captured is True
    assert result.user_confirmed is True


def test_base_webview_post_returns_error():
    """post() on a WebView platform should return an error since it needs the panel."""
    platform = ConcreteWebViewPlatform(account_id='test_1')
    result = platform.post('Hello')
    assert result.success is False
    assert result.error_code == 'WV-PREFILL-FAILED'


def test_webview_panel_importable():
    """Verify the WebView panel module can be imported."""
    from src.gui.webview_panel import WebViewPanel  # noqa: F401


def _write_cookie_db(path: Path, host: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS cookies (host_key TEXT)')
        cursor.execute('INSERT INTO cookies (host_key) VALUES (?)', (host,))
        conn.commit()


def test_base_webview_has_valid_session_false_without_cookie(monkeypatch, tmp_path):
    import src.platforms.base_webview as base_webview

    monkeypatch.setattr(base_webview, 'get_app_data_dir', lambda: tmp_path)
    platform = ConcreteWebViewPlatform(account_id='test_1')
    assert platform.has_valid_session() is False


def test_base_webview_has_valid_session_true_with_cookie(monkeypatch, tmp_path):
    import src.platforms.base_webview as base_webview

    monkeypatch.setattr(base_webview, 'get_app_data_dir', lambda: tmp_path)
    platform = ConcreteWebViewPlatform(account_id='test_1')
    cookie_path = tmp_path / 'webprofiles' / 'test_1' / 'Cookies'
    _write_cookie_db(cookie_path, '.example.com')
    assert platform.has_valid_session() is True


def test_base_webview_test_connection_uses_cookie_check(monkeypatch, tmp_path):
    import src.platforms.base_webview as base_webview

    monkeypatch.setattr(base_webview, 'get_app_data_dir', lambda: tmp_path)
    platform = ConcreteWebViewPlatform(account_id='test_1')
    success, error = platform.test_connection()
    assert success is False
    assert error == 'WV-SESSION-EXPIRED'


def test_base_webview_test_connection_valid_session(monkeypatch, tmp_path):
    import src.platforms.base_webview as base_webview

    monkeypatch.setattr(base_webview, 'get_app_data_dir', lambda: tmp_path)
    platform = ConcreteWebViewPlatform(account_id='test_1')
    monkeypatch.setattr(platform, '_can_run_live_connection_test', lambda: False)
    cookie_path = tmp_path / 'webprofiles' / 'test_1' / 'Cookies'
    _write_cookie_db(cookie_path, '.example.com')
    success, error = platform.test_connection()
    assert success is True
    assert error is None


def test_base_webview_test_connection_live_probe_used_with_qapp(monkeypatch, tmp_path):
    import src.platforms.base_webview as base_webview

    monkeypatch.setattr(base_webview, 'get_app_data_dir', lambda: tmp_path)

    platform = ConcreteWebViewPlatform(account_id='test_1')
    monkeypatch.setattr(platform, '_can_run_live_connection_test', lambda: True)
    cookie_path = tmp_path / 'webprofiles' / 'test_1' / 'Cookies'
    _write_cookie_db(cookie_path, '.example.com')

    calls = {}
    monkeypatch.setattr(
        platform,
        '_run_live_connection_test',
        lambda: (calls.setdefault('called', True), None),
    )

    success, error = platform.test_connection()
    assert calls.get('called') is True
    assert success is True
    assert error is None


def test_base_webview_has_valid_session_no_cookie_domains(monkeypatch, tmp_path):
    import src.platforms.base_webview as base_webview

    monkeypatch.setattr(base_webview, 'get_app_data_dir', lambda: tmp_path)

    class NoCookiePlatform(ConcreteWebViewPlatform):
        COOKIE_DOMAINS = []

    platform = NoCookiePlatform(account_id='test_1')
    assert platform.has_valid_session() is False


def test_base_webview_has_valid_session_wrong_domain(monkeypatch, tmp_path):
    import src.platforms.base_webview as base_webview

    monkeypatch.setattr(base_webview, 'get_app_data_dir', lambda: tmp_path)
    platform = ConcreteWebViewPlatform(account_id='test_1')
    cookie_path = tmp_path / 'webprofiles' / 'test_1' / 'Cookies'
    _write_cookie_db(cookie_path, '.other-domain.com')
    assert platform.has_valid_session() is False


def test_base_webview_has_valid_session_corrupt_db(monkeypatch, tmp_path):
    import src.platforms.base_webview as base_webview

    monkeypatch.setattr(base_webview, 'get_app_data_dir', lambda: tmp_path)
    platform = ConcreteWebViewPlatform(account_id='test_1')
    cookie_path = tmp_path / 'webprofiles' / 'test_1' / 'Cookies'
    cookie_path.parent.mkdir(parents=True, exist_ok=True)
    cookie_path.write_bytes(b'not a database')
    assert platform.has_valid_session() is False


def test_base_webview_has_valid_session_locked_db_returns_quickly(monkeypatch, tmp_path):
    import src.platforms.base_webview as base_webview

    monkeypatch.setattr(base_webview, 'get_app_data_dir', lambda: tmp_path)
    platform = ConcreteWebViewPlatform(account_id='test_1')
    cookie_path = tmp_path / 'webprofiles' / 'test_1' / 'Cookies'
    _write_cookie_db(cookie_path, '.example.com')

    lock_conn = sqlite3.connect(cookie_path)
    lock_conn.execute('BEGIN EXCLUSIVE')
    start = time.perf_counter()
    try:
        assert platform.has_valid_session() is False
    finally:
        lock_conn.rollback()
        lock_conn.close()
    elapsed = time.perf_counter() - start
    assert elapsed < 0.5


def test_base_webview_is_session_cookie_matches_domain_and_auth_name():
    class AuthPlatform(ConcreteWebViewPlatform):
        AUTH_COOKIE_NAMES = ['session_id']

    platform = AuthPlatform(account_id='test_1')
    assert platform.is_session_cookie('.example.com', 'session_id') is True
    assert platform.is_session_cookie('sub.example.com', 'session_id') is True
    assert platform.is_session_cookie('.example.com', 'other') is False
    assert platform.is_session_cookie('.other.com', 'session_id') is False


def test_base_webview_prepare_post():
    platform = ConcreteWebViewPlatform(account_id='test_1')
    platform._post_confirmed = True
    platform._captured_post_url = 'https://old.url'

    platform.prepare_post('New post', [Path('/tmp/img.jpg')])

    assert platform._text == 'New post'
    assert platform._image_path == Path('/tmp/img.jpg')
    assert platform._captured_post_url is None
    assert platform._post_confirmed is False
    assert platform._poll_elapsed_ms == 0


def test_base_webview_is_post_confirmed_property():
    platform = ConcreteWebViewPlatform(account_id='test_1')
    assert platform.is_post_confirmed is False
    platform.mark_confirmed()
    assert platform.is_post_confirmed is True


def test_base_webview_captured_post_url_property():
    platform = ConcreteWebViewPlatform(account_id='test_1')
    assert platform.captured_post_url is None
    platform._captured_post_url = 'https://example.com/post/1'
    assert platform.captured_post_url == 'https://example.com/post/1'


def test_base_webview_get_webview_none():
    platform = ConcreteWebViewPlatform(account_id='test_1')
    assert platform.get_webview() is None


def test_base_webview_profile_storage_path(monkeypatch, tmp_path):
    import src.platforms.base_webview as base_webview

    monkeypatch.setattr(base_webview, 'get_app_data_dir', lambda: tmp_path)
    platform = ConcreteWebViewPlatform(account_id='myaccount')
    path = platform._get_profile_storage_path()
    assert path == tmp_path / 'webprofiles' / 'myaccount'


def test_base_webview_profile_storage_default_account(monkeypatch, tmp_path):
    import src.platforms.base_webview as base_webview

    monkeypatch.setattr(base_webview, 'get_app_data_dir', lambda: tmp_path)
    platform = ConcreteWebViewPlatform(account_id='')
    path = platform._get_profile_storage_path()
    assert path == tmp_path / 'webprofiles' / 'default'


def test_base_webview_navigation_logging_tracks_source_and_redirect(monkeypatch):
    import src.platforms.base_webview as base_webview

    class DummyLogger:
        def __init__(self):
            self.debug_messages = []
            self.isEnabledFor = self.is_enabled_for  # noqa: N815

        def is_enabled_for(self, _level):
            return True

        def debug(self, message):
            self.debug_messages.append(message)

        def info(self, _message):
            return

        def warning(self, _message):
            return

        def error(self, _message):
            return

    logger = DummyLogger()
    monkeypatch.setattr(base_webview, 'get_logger', lambda: logger)

    platform = ConcreteWebViewPlatform(account_id='test_1')
    platform._last_url = 'https://example.com/login'
    platform._on_navigation_request(
        QUrl('https://example.com/authorize'),
        type('NavType', (), {'name': 'NavigationTypeLinkClicked'})(),
        True,
        True,
    )

    platform._on_url_changed(QUrl('https://example.com/oauth/callback'))

    assert any("source='user-click'" in msg for msg in logger.debug_messages)
    assert any('redirect-or-script-after-user-click' in msg for msg in logger.debug_messages)


def test_base_webview_render_process_termination_logs_error(monkeypatch):
    import src.platforms.base_webview as base_webview

    class DummyLogger:
        def __init__(self):
            self.errors = []
            self.isEnabledFor = self.is_enabled_for  # noqa: N815

        def is_enabled_for(self, _level):
            return False

        def debug(self, _message):
            return

        def info(self, _message):
            return

        def warning(self, _message):
            return

        def error(self, message):
            self.errors.append(message)

    logger = DummyLogger()
    monkeypatch.setattr(base_webview, 'get_logger', lambda: logger)

    platform = ConcreteWebViewPlatform(account_id='test_1')
    platform._on_render_process_terminated(
        type('Status', (), {'name': 'CrashedTerminationStatus'})(),
        139,
    )

    assert any('Render process terminated' in msg for msg in logger.errors)
    assert any('exit_code=139' in msg for msg in logger.errors)


def test_base_webview_create_webview_and_navigation_signals(monkeypatch, tmp_path):
    import src.platforms.base_webview as base_webview

    logger = DummyLogger(debug_enabled=True)
    monkeypatch.setattr(base_webview, 'get_logger', lambda: logger)
    monkeypatch.setattr(base_webview, 'get_app_data_dir', lambda: tmp_path)
    monkeypatch.setattr(base_webview, 'QWebEngineProfile', DummyProfile)
    monkeypatch.setattr(base_webview, 'QWebEngineView', DummyView)
    monkeypatch.setattr(base_webview, '_LoggingWebEnginePage', DummyPage)

    platform = ConcreteWebViewPlatform(account_id='acct1')
    view = platform.create_webview()
    page = view.page()

    assert isinstance(view, DummyView)
    assert isinstance(page, DummyPage)
    assert platform.get_webview() is view
    assert platform._profile is not None
    assert Path(platform._profile.storage_path).parts[-2:] == ('webprofiles', 'acct1')
    # The platform must retain the page. setPage() does not hand ownership to
    # Python, so dropping the reference lets it be garbage-collected and the
    # view silently falls back to Qt's default off-the-record profile, which
    # never persists cookies to disk.
    assert platform._page is page
    # With no imported session, the profile falls back to the normalized user
    # agent: the QtWebEngine product token is stripped, Chrome's is preserved.
    assert 'QtWebEngine/' not in platform._profile.user_agent
    assert 'Chrome/140.0.0.0' in platform._profile.user_agent

    page.loadStarted.emit()
    page.loadProgress.emit(50)
    page.loadFinished.emit(True)
    page.windowCloseRequested.emit()
    page.renderProcessPidChanged.emit(444)
    page.renderProcessTerminated.emit(SimpleNamespace(name='Crash'), 77)
    view.renderProcessTerminated.emit(SimpleNamespace(name='Crash'), 88)
    page.urlChanged.emit(QUrl('https://example.com/post/999'))

    assert platform._post_confirmed is True
    assert platform._captured_post_url == 'https://example.com/post/999'
    assert any('WebView created' in msg for msg in logger.debug_messages)
    assert any('URL changed' in msg for msg in logger.debug_messages)
    assert any('Render process terminated' in msg for msg in logger.error_messages)
    assert any('View render process terminated' in msg for msg in logger.error_messages)


def test_base_webview_domain_and_cookie_name_helpers():
    class AuthPlatform(ConcreteWebViewPlatform):
        COOKIE_DOMAINS = [' .example.com ', '']
        AUTH_COOKIE_NAMES = ['Session_ID']
        AUTH_COOKIE_NAME_PATTERNS = [r'auth_.*']

    platform = AuthPlatform(account_id='test_1')
    where, params = platform._domain_where_clause()

    assert 'lower(host_key) LIKE ?' in where
    assert params == ('%example.com',)
    assert platform._matches_cookie_domain('sub.example.com') is True
    assert platform._matches_cookie_domain('.example.com') is True
    assert platform._matches_cookie_domain('other.com') is False
    assert platform._is_auth_cookie_name('session_id') is True
    assert platform._is_auth_cookie_name('auth_token') is True
    assert platform._is_auth_cookie_name('') is False
    assert platform.is_session_cookie('sub.example.com', 'auth_token') is True
    assert platform.is_session_cookie('sub.example.com', 'other') is False


def test_base_webview_sanitize_and_login_redirect_helpers():
    class LoginPlatform(ConcreteWebViewPlatform):
        LOGIN_URL = 'https://example.com/login'

    platform = LoginPlatform(account_id='test_1')
    assert (
        platform._sanitize_url_for_log('https://example.com/path?q=1#frag')
        == 'https://example.com/path?...'
    )
    assert platform._sanitize_url_for_log('not a url') == 'not a url'
    assert platform._is_login_redirect_url('https://other.com/login') is False
    assert platform._is_login_redirect_url('https://example.com/login?next=%2Fcompose') is True
    assert platform._is_login_redirect_url('https://example.com/auth/challenge') is True


def test_base_webview_has_valid_session_in_db_branches():
    class PatternPlatform(ConcreteWebViewPlatform):
        AUTH_COOKIE_NAMES = []
        AUTH_COOKIE_NAME_PATTERNS = [r'auth_.*']

    platform = PatternPlatform(account_id='test_1')
    now_chrome_us = int((time.time() + 11644473600) * 1_000_000)

    with sqlite3.connect(':memory:') as conn:
        conn.execute('CREATE TABLE cookies (name TEXT)')
        assert platform._has_valid_session_in_db(conn) is False

    with sqlite3.connect(':memory:') as conn:
        conn.execute('CREATE TABLE cookies (host_key TEXT, expires_utc INTEGER)')
        conn.execute(
            'INSERT INTO cookies (host_key, expires_utc) VALUES (?, ?)', ('.example.com', 0)
        )
        assert platform._has_valid_session_in_db(conn) is False

    class HostOnlyPlatform(ConcreteWebViewPlatform):
        AUTH_COOKIE_NAMES = []
        AUTH_COOKIE_NAME_PATTERNS = []

    host_only_platform = HostOnlyPlatform(account_id='test_1')
    with sqlite3.connect(':memory:') as conn:
        conn.execute('CREATE TABLE cookies (host_key TEXT, expires_utc INTEGER)')
        conn.execute(
            'INSERT INTO cookies (host_key, expires_utc) VALUES (?, ?)', ('.example.com', 0)
        )
        assert host_only_platform._has_valid_session_in_db(conn) is True

    with sqlite3.connect(':memory:') as conn:
        conn.execute('CREATE TABLE cookies (host_key TEXT, name TEXT)')
        conn.execute(
            'INSERT INTO cookies (host_key, name) VALUES (?, ?)', ('.example.com', 'auth_token')
        )
        assert platform._has_valid_session_in_db(conn) is True

    with sqlite3.connect(':memory:') as conn:
        conn.execute('CREATE TABLE cookies (host_key TEXT, expires_utc INTEGER)')
        conn.execute(
            'INSERT INTO cookies (host_key, expires_utc) VALUES (?, ?)',
            ('.example.com', now_chrome_us + 1_000_000),
        )

        class NameRequiredPlatform(ConcreteWebViewPlatform):
            AUTH_COOKIE_NAMES = ['session_id']

        name_platform = NameRequiredPlatform(account_id='test_1')
        assert name_platform._has_valid_session_in_db(conn) is False


def test_base_webview_navigation_and_prefill_paths(monkeypatch):
    import src.platforms.base_webview as base_webview

    logger = DummyLogger(debug_enabled=True)
    monkeypatch.setattr(base_webview, 'get_logger', lambda: logger)

    platform = ConcreteWebViewPlatform(account_id='test_1')
    page = DummyPage()
    view = DummyView()
    view.setPage(page)
    platform._view = view

    platform._on_navigation_request(
        QUrl('https://example.com/compose'),
        SimpleNamespace(name='NavigationTypeFormSubmitted'),
        True,
        True,
    )
    platform._on_url_changed(QUrl('https://example.com/compose#done'))
    assert any('form-submit' in msg for msg in logger.debug_messages)

    timers = []
    monkeypatch.setattr(
        base_webview.QTimer,
        'singleShot',
        lambda delay, callback: (timers.append(delay), callback()),
    )
    called = {}
    monkeypatch.setattr(platform, '_do_prefill', lambda: called.setdefault('prefill', True))
    platform._on_load_finished(True)
    assert called.get('prefill') is True
    assert timers == [platform.PREFILL_DELAY_MS]

    platform._on_load_finished(False)
    assert any('Page load failed' in msg for msg in logger.warning_messages)


def test_base_webview_navigate_to_composer_branches(monkeypatch):
    import src.platforms.base_webview as base_webview

    logger = DummyLogger(debug_enabled=False)
    monkeypatch.setattr(base_webview, 'get_logger', lambda: logger)

    platform = ConcreteWebViewPlatform(account_id='test_1')
    platform.navigate_to_composer()
    assert any('WebView not created' in msg for msg in logger.error_messages)

    class NoComposerPlatform(ConcreteWebViewPlatform):
        COMPOSER_URL = ''

    no_url_platform = NoComposerPlatform(account_id='test_1')
    no_url_platform._view = DummyView()
    no_url_platform.navigate_to_composer()
    assert any('No COMPOSER_URL defined' in msg for msg in logger.error_messages)

    platform._view = DummyView()
    platform._view._page = None
    platform.navigate_to_composer()
    assert any('WebView page not available' in msg for msg in logger.error_messages)

    page = DummyPage()
    platform._view = DummyView()
    platform._view.setPage(page)
    platform.navigate_to_composer()
    assert platform._view.loaded_urls == [platform.COMPOSER_URL]


def test_base_webview_injection_and_polling(monkeypatch):
    import src.platforms.base_webview as base_webview

    logger = DummyLogger(debug_enabled=True)
    monkeypatch.setattr(base_webview, 'get_logger', lambda: logger)
    monkeypatch.setattr(base_webview, 'QTimer', DummyTimer)

    platform = ConcreteWebViewPlatform(account_id='test_1')
    page = DummyPage()
    view = DummyView()
    view.setPage(page)
    platform._view = view
    platform.SUCCESS_SELECTOR = 'div.success'
    platform.PERMALINK_SELECTOR = 'a.link'

    platform._inject_text('Hello world')
    assert any('Hello world' in call for call in page.js_calls)

    page.js_calls.clear()
    platform._inject_success_observer()
    assert any('_galefling_post_success' in call for call in page.js_calls)

    platform.start_success_polling()
    assert isinstance(platform._poll_timer, DummyTimer)
    assert platform._poll_timer.started is True

    platform._poll_elapsed_ms = platform.POLL_TIMEOUT_MS
    platform._poll_for_success()
    assert platform._poll_timer is None

    platform.start_success_polling()
    platform._view = None
    platform._poll_for_success()
    assert platform._poll_timer is None

    platform._post_confirmed = False
    platform._captured_post_url = None
    platform._handle_poll_result({'success': True, 'url': 'https://example.com/post/333'})
    assert platform._post_confirmed is True
    assert platform._captured_post_url == 'https://example.com/post/333'

    platform._handle_poll_result({'success': True, 'url': None})
    platform._handle_poll_result('not-a-dict')


def test_base_webview_run_live_connection_test_paths(monkeypatch, tmp_path):
    import src.platforms.base_webview as base_webview

    logger = DummyLogger(debug_enabled=True)
    monkeypatch.setattr(base_webview, 'get_logger', lambda: logger)
    monkeypatch.setattr(base_webview, 'get_app_data_dir', lambda: tmp_path)
    monkeypatch.setattr(base_webview, 'QWebEngineProfile', DummyProfile)
    monkeypatch.setattr(base_webview, '_LoggingWebEnginePage', DummyPage)
    monkeypatch.setattr(base_webview, 'QEventLoop', DummyEventLoop)
    monkeypatch.setattr(base_webview, 'QTimer', DummyTimer)

    platform = ConcreteWebViewPlatform(account_id='test_1')
    DummyPage.scenario = 'success'
    DummyTimer.trigger_timeout = False
    ok, error = platform._run_live_connection_test()
    assert ok is True
    assert error is None

    DummyPage.scenario = 'login_redirect'
    ok, error = platform._run_live_connection_test()
    assert ok is False
    assert error == 'WV-SESSION-EXPIRED'

    DummyPage.scenario = 'load_fail'
    ok, error = platform._run_live_connection_test()
    assert ok is False
    assert error == 'WV-LOAD-FAILED'

    DummyPage.scenario = 'no_events'
    DummyTimer.trigger_timeout = True
    ok, error = platform._run_live_connection_test()
    assert ok is False
    assert error == 'WV-LOAD-FAILED'


def test_base_webview_connection_test_helpers(monkeypatch):
    import src.platforms.base_webview as base_webview

    platform = ConcreteWebViewPlatform(account_id='test_1')
    assert platform._get_connection_test_url() == platform.COMPOSER_URL

    monkeypatch.setattr(base_webview.QApplication, 'instance', lambda: None)
    assert platform._can_run_live_connection_test() is False
    monkeypatch.setattr(
        base_webview.QApplication,
        'instance',
        lambda: SimpleNamespace(processEvents=lambda: None),
    )
    assert platform._can_run_live_connection_test() is True


# ── Session import ──────────────────────────────────────────────────


class DummyScriptCollection:
    def __init__(self):
        self.scripts = []

    def find(self, name):
        return [s for s in self.scripts if s.name() == name]

    def insert(self, script):
        self.scripts.append(script)

    def remove(self, script):
        self.scripts.remove(script)


class DummyCookieStore:
    def __init__(self, *, accept=True):
        self.cookieAdded = DummySignal()
        self.loaded = False
        self.set_cookies = []
        self._accept = accept

    def loadAllCookies(self):  # noqa: N802
        self.loaded = True

    def setCookie(self, cookie, origin):  # noqa: N802
        self.set_cookies.append((cookie, origin))
        if self._accept:
            self.cookieAdded.emit(cookie)


def _make_session(**overrides):
    from src.core.webview_session_import import ImportedSession

    values = {
        'user_id': '123456789',
        'user_agent': 'FixtureBrowser/1.0',
        'x_bc': 'a' * 40,
        'cookies': {'auth_id': '123456789', 'sess': 'fixture-token'},
    }
    values.update(overrides)
    return ImportedSession(**values)


def _prepare_import(monkeypatch, tmp_path, *, accept=True):
    """Wire a platform whose profile records cookie writes instead of using Qt."""
    import src.platforms.base_webview as base_webview

    monkeypatch.setattr(base_webview, 'get_app_data_dir', lambda: tmp_path)
    monkeypatch.setattr(base_webview, 'get_logger', lambda: DummyLogger())
    monkeypatch.setattr(
        base_webview.BaseWebViewPlatform, '_wait_ms', staticmethod(lambda _ms: None)
    )

    store = DummyCookieStore(accept=accept)
    collection = DummyScriptCollection()

    class RecordingProfile(DummyProfile):
        def cookieStore(self):  # noqa: N802
            return store

        def scripts(self):
            return collection

    monkeypatch.setattr(base_webview, 'QWebEngineProfile', RecordingProfile)
    monkeypatch.setattr(base_webview, 'QWebEngineView', DummyView)
    monkeypatch.setattr(base_webview, '_LoggingWebEnginePage', DummyPage)
    BaseWebViewPlatform._profile_registry.clear()
    return store, collection


def test_import_session_injects_cookies_with_expiry(monkeypatch, tmp_path):
    store, _ = _prepare_import(monkeypatch, tmp_path)
    platform = ConcreteWebViewPlatform(account_id='acct_import')

    ok, error = platform.import_session(_make_session())

    assert ok is True
    assert error is None
    assert store.loaded is True, 'store must be bound to disk before writing'

    written = {bytes(c.name()).decode(): c for c, _ in store.set_cookies}
    assert set(written) == {'auth_id', 'sess'}
    for cookie in written.values():
        # Without an expiry Chromium treats these as session cookies and never
        # persists them, so has_valid_session() could never see them again.
        assert cookie.isSessionCookie() is False
        assert cookie.expirationDate().isValid()
        assert cookie.domain() == '.example.com'
        assert cookie.isSecure() is True
        assert cookie.isHttpOnly() is True

    origin = store.set_cookies[0][1]
    assert origin.toString() == 'https://example.com/', 'origin derives from the platform'


def test_import_session_reports_rejected_cookies(monkeypatch, tmp_path):
    _prepare_import(monkeypatch, tmp_path, accept=False)
    platform = ConcreteWebViewPlatform(account_id='acct_reject')

    ok, error = platform.import_session(_make_session())

    assert ok is False
    assert 'auth_id' in error and 'sess' in error
    assert 'stale' not in error.lower(), 'must not blame the export when the store refused'


def test_import_session_persists_user_agent(monkeypatch, tmp_path):
    _prepare_import(monkeypatch, tmp_path)
    from src.core.webview_session_import import load_session_metadata

    platform = ConcreteWebViewPlatform(account_id='acct_ua')
    session = _make_session(user_agent='Mozilla/5.0 (Exported) Firefox/128.0')
    ok, _ = platform.import_session(session)

    assert ok is True
    assert platform._profile.user_agent == session.user_agent
    metadata = load_session_metadata(tmp_path / 'webprofiles' / 'acct_ua')
    assert metadata['user_agent'] == session.user_agent
    assert metadata['x_bc'] == session.x_bc


def test_import_session_requires_cookie_domains(monkeypatch, tmp_path):
    _prepare_import(monkeypatch, tmp_path)

    class NoDomainPlatform(ConcreteWebViewPlatform):
        COOKIE_DOMAINS: list[str] = []

    ok, error = NoDomainPlatform(account_id='acct_nodomain').import_session(_make_session())
    assert ok is False
    assert 'does not support session import' in error


def test_profile_seeds_device_token_after_import(monkeypatch, tmp_path):
    _, collection = _prepare_import(monkeypatch, tmp_path)
    platform = ConcreteWebViewPlatform(account_id='acct_token')
    session = _make_session(x_bc='f' * 40)
    assert platform.import_session(session)[0] is True

    # A new profile for the same account must re-seed the token, so the
    # token survives application restarts rather than only the import run.
    BaseWebViewPlatform._profile_registry.clear()
    collection.scripts.clear()
    ConcreteWebViewPlatform(account_id='acct_token').create_webview()

    seeded = collection.find('galefling_session_token')
    assert len(seeded) == 1
    source = seeded[0].sourceCode()
    assert 'bcTokenSha' in source
    assert session.x_bc in source
    assert 'example.com' in source


def test_profile_without_import_has_no_token_script(monkeypatch, tmp_path):
    _, collection = _prepare_import(monkeypatch, tmp_path)
    ConcreteWebViewPlatform(account_id='acct_plain').create_webview()
    assert collection.find('galefling_session_token') == []
