"""Tests for WebView platform infrastructure."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from PyQt6.QtCore import QUrl

from src.platforms.base_webview import BaseWebViewPlatform
from src.utils.constants import PlatformSpecs


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
    assert elapsed < 0.2


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
