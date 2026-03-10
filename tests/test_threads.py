"""Tests for the Threads WebView platform."""

import re
import sqlite3
from pathlib import Path

from src.platforms.threads import ThreadsPlatform
from src.utils.constants import (
    ERROR_CODES,
    PLATFORM_SPECS_MAP,
    THREADS_SPECS,
    USER_FRIENDLY_MESSAGES,
)

# ── Specs ────────────────────────────────────────────────────────────


def test_threads_in_platform_specs_map():
    assert 'threads' in PLATFORM_SPECS_MAP
    assert PLATFORM_SPECS_MAP['threads'] is THREADS_SPECS


def test_threads_specs_basic():
    assert THREADS_SPECS.platform_name == 'Threads'
    assert THREADS_SPECS.max_text_length == 500
    assert THREADS_SPECS.api_type == 'webview'
    assert THREADS_SPECS.auth_method == 'session_cookie'
    assert THREADS_SPECS.requires_user_confirm is True
    assert THREADS_SPECS.max_accounts == 2


def test_threads_specs_image():
    assert THREADS_SPECS.max_image_dimensions == (1440, 1440)
    assert THREADS_SPECS.max_file_size_mb == 10.0
    assert 'JPEG' in THREADS_SPECS.supported_formats
    assert 'PNG' in THREADS_SPECS.supported_formats
    assert THREADS_SPECS.supports_images is True
    assert THREADS_SPECS.supports_text is True


def test_threads_specs_video():
    assert 'MP4' in THREADS_SPECS.supported_video_formats
    assert THREADS_SPECS.max_video_dimensions == (1920, 1080)
    assert THREADS_SPECS.max_video_file_size_mb == 1024.0
    assert THREADS_SPECS.max_video_duration_seconds == 300


def test_threads_specs_color():
    assert THREADS_SPECS.platform_color == '#000000'


def test_threads_error_codes_defined():
    assert 'TH-AUTH-INVALID' in ERROR_CODES
    assert 'TH-AUTH-EXPIRED' in ERROR_CODES
    assert 'TH-RATE-LIMIT' in ERROR_CODES


def test_threads_user_friendly_messages_defined():
    assert 'TH-AUTH-INVALID' in USER_FRIENDLY_MESSAGES
    assert 'TH-AUTH-EXPIRED' in USER_FRIENDLY_MESSAGES
    assert 'TH-RATE-LIMIT' in USER_FRIENDLY_MESSAGES


# ── Platform class ───────────────────────────────────────────────────


def test_threads_platform_name_with_profile():
    p = ThreadsPlatform(account_id='threads_1', profile_name='rinthemodel')
    assert p.get_platform_name() == 'Threads (rinthemodel)'


def test_threads_platform_name_no_profile():
    p = ThreadsPlatform(account_id='threads_1')
    assert p.get_platform_name() == 'Threads'


def test_threads_get_specs():
    p = ThreadsPlatform(account_id='threads_1')
    assert p.get_specs() is THREADS_SPECS


def test_threads_composer_url():
    assert ThreadsPlatform.COMPOSER_URL == 'https://www.threads.net/'


def test_threads_login_url():
    assert ThreadsPlatform.LOGIN_URL == 'https://www.threads.net/login'


def test_threads_cookie_domains():
    assert 'threads.net' in ThreadsPlatform.COOKIE_DOMAINS


def test_threads_text_selector_nonempty():
    assert ThreadsPlatform.TEXT_SELECTOR != ''


def test_threads_auth_cookie_names_nonempty():
    assert len(ThreadsPlatform.AUTH_COOKIE_NAMES) > 0


def test_threads_success_url_pattern_matches_post():
    pattern = ThreadsPlatform.SUCCESS_URL_PATTERN
    assert re.search(pattern, 'https://www.threads.net/@rinthemodel/post/ABC123xyz')
    assert re.search(pattern, 'https://www.threads.net/@user.name/post/CDefGHijkL')


def test_threads_success_url_pattern_no_match_home():
    pattern = ThreadsPlatform.SUCCESS_URL_PATTERN
    assert not re.search(pattern, 'https://www.threads.net/')
    assert not re.search(pattern, 'https://www.threads.net/login')


def test_threads_is_webview_platform():
    p = ThreadsPlatform(account_id='threads_1')
    result = p.post('Hello Threads')
    assert result.success is False
    assert result.error_code == 'WV-PREFILL-FAILED'


def test_threads_authenticate():
    p = ThreadsPlatform(account_id='threads_1')
    success, error = p.authenticate()
    assert success is True
    assert error is None


def test_threads_build_result_not_confirmed():
    p = ThreadsPlatform(account_id='threads_1', profile_name='rinthemodel')
    result = p.build_result()
    assert result.success is False
    assert result.error_code == 'WV-SUBMIT-TIMEOUT'
    assert result.user_confirmed is False


def test_threads_build_result_confirmed_with_url():
    p = ThreadsPlatform(account_id='threads_1', profile_name='rinthemodel')
    p._post_confirmed = True
    p._captured_post_url = 'https://www.threads.net/@rinthemodel/post/ABC123'
    result = p.build_result()
    assert result.success is True
    assert result.post_url == 'https://www.threads.net/@rinthemodel/post/ABC123'
    assert result.url_captured is True
    assert result.user_confirmed is True


def test_threads_build_result_confirmed_no_url():
    p = ThreadsPlatform(account_id='threads_1', profile_name='rinthemodel')
    p._post_confirmed = True
    p._captured_post_url = None
    result = p.build_result()
    assert result.success is True
    assert result.post_url is None
    assert result.url_captured is False


# ── Session cookie detection ─────────────────────────────────────────


def _write_cookie(path: Path, host: str, name: str, expires_utc: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            'CREATE TABLE IF NOT EXISTS cookies (host_key TEXT, name TEXT, expires_utc INTEGER)'
        )
        cursor.execute(
            'INSERT INTO cookies (host_key, name, expires_utc) VALUES (?, ?, ?)',
            (host, name, expires_utc),
        )
        conn.commit()


def test_threads_no_session_without_auth_cookie(monkeypatch, tmp_path):
    import src.platforms.base_webview as base_webview

    monkeypatch.setattr(base_webview, 'get_app_data_dir', lambda: tmp_path)
    platform = ThreadsPlatform(account_id='threads_1')
    cookie_path = tmp_path / 'webprofiles' / 'threads_1' / 'Cookies'

    future_expiry = 20_000_000_000_000_000
    # Non-auth cookie should not count
    _write_cookie(cookie_path, '.threads.net', '_ga', future_expiry)
    assert platform.has_valid_session() is False


def test_threads_session_with_auth_cookie(monkeypatch, tmp_path):
    import src.platforms.base_webview as base_webview

    monkeypatch.setattr(base_webview, 'get_app_data_dir', lambda: tmp_path)
    platform = ThreadsPlatform(account_id='threads_1')
    cookie_path = tmp_path / 'webprofiles' / 'threads_1' / 'Cookies'

    future_expiry = 20_000_000_000_000_000
    # AUTH_COOKIE_NAMES[0] ('sessionid') should be accepted
    _write_cookie(cookie_path, '.threads.net', ThreadsPlatform.AUTH_COOKIE_NAMES[0], future_expiry)
    assert platform.has_valid_session() is True
