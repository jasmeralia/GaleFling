"""Tests for concrete WebView platform implementations."""

import sqlite3
from pathlib import Path

from src.platforms.fansly import FanslyPlatform
from src.platforms.fetlife import FetLifePlatform
from src.platforms.onlyfans import OnlyFansPlatform
from src.platforms.snapchat import SnapchatPlatform

# ── Snapchat ────────────────────────────────────────────────────────


def test_snapchat_platform_name():
    p = SnapchatPlatform(account_id='snapchat_1', profile_name='rin')
    assert p.get_platform_name() == 'Snapchat (rin)'


def test_snapchat_platform_name_no_profile():
    p = SnapchatPlatform(account_id='snapchat_1')
    assert p.get_platform_name() == 'Snapchat'


def test_snapchat_specs():
    p = SnapchatPlatform(account_id='snapchat_1')
    specs = p.get_specs()
    assert specs.platform_name == 'Snapchat'
    assert specs.api_type == 'webview'
    assert specs.max_accounts == 2
    assert specs.requires_user_confirm is True


def test_snapchat_composer_url():
    assert SnapchatPlatform.COMPOSER_URL == 'https://web.snapchat.com/'


def test_snapchat_is_webview():
    p = SnapchatPlatform(account_id='snapchat_1')
    result = p.post('Hello')
    assert result.success is False
    assert result.error_code == 'WV-PREFILL-FAILED'


def test_snapchat_configures_safe_webview_settings(monkeypatch):
    class DummySettings:
        def __init__(self):
            self.calls = []

        def setAttribute(self, attr, value):  # noqa: N802
            self.calls.append((attr, value))

    class DummyPage:
        def __init__(self, settings):
            self._settings = settings

        def settings(self):
            return self._settings

    class DummyWebAttribute:
        WebGLEnabled = 'webgl'
        Accelerated2dCanvasEnabled = 'canvas2d'

    class DummyQWebEngineSettings:
        WebAttribute = DummyWebAttribute

    monkeypatch.setattr('src.platforms.snapchat.QWebEngineSettings', DummyQWebEngineSettings)
    settings = DummySettings()
    page = DummyPage(settings)

    p = SnapchatPlatform(account_id='snapchat_1')
    p._configure_webview_page(page)

    assert ('webgl', False) in settings.calls
    assert ('canvas2d', False) in settings.calls


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


def test_snapchat_session_requires_auth_cookie(monkeypatch, tmp_path):
    import src.platforms.base_webview as base_webview

    monkeypatch.setattr(base_webview, 'get_app_data_dir', lambda: tmp_path)
    platform = SnapchatPlatform(account_id='snapchat_1')
    cookie_path = tmp_path / 'webprofiles' / 'snapchat_1' / 'Cookies'

    future_expiry = 20_000_000_000_000_000
    _write_cookie(cookie_path, '.snapchat.com', '_ga', future_expiry)
    assert platform.has_valid_session() is False

    _write_cookie(
        cookie_path,
        'accounts.snapchat.com',
        '__Host-sc-a-auth-session',
        future_expiry,
    )
    assert platform.has_valid_session() is True


# ── OnlyFans ────────────────────────────────────────────────────────


def test_onlyfans_platform_name():
    p = OnlyFansPlatform(account_id='onlyfans_1', profile_name='rinmodel')
    assert p.get_platform_name() == 'OnlyFans (rinmodel)'


def test_onlyfans_specs():
    p = OnlyFansPlatform(account_id='onlyfans_1')
    specs = p.get_specs()
    assert specs.platform_name == 'OnlyFans'
    assert specs.has_cloudflare is True
    assert specs.requires_user_confirm is True
    assert specs.max_accounts == 1


def test_onlyfans_prefill_delay():
    assert OnlyFansPlatform.PREFILL_DELAY_MS == 1500


def test_onlyfans_authenticate():
    p = OnlyFansPlatform(account_id='onlyfans_1')
    success, error = p.authenticate()
    assert success is True
    assert error is None


def test_onlyfans_session_requires_auth_cookie(monkeypatch, tmp_path):
    import src.platforms.base_webview as base_webview

    monkeypatch.setattr(base_webview, 'get_app_data_dir', lambda: tmp_path)
    platform = OnlyFansPlatform(account_id='onlyfans_1')
    cookie_path = tmp_path / 'webprofiles' / 'onlyfans_1' / 'Cookies'

    future_expiry = 20_000_000_000_000_000
    _write_cookie(cookie_path, '.onlyfans.com', '__cf_bm', future_expiry)
    assert platform.has_valid_session() is False

    _write_cookie(cookie_path, 'onlyfans.com', 'auth_id', future_expiry)
    assert platform.has_valid_session() is True


# ── Fansly ──────────────────────────────────────────────────────────


def test_fansly_platform_name():
    p = FanslyPlatform(account_id='fansly_1', profile_name='rinmodel')
    assert p.get_platform_name() == 'Fansly (rinmodel)'


def test_fansly_specs():
    p = FanslyPlatform(account_id='fansly_1')
    specs = p.get_specs()
    assert specs.platform_name == 'Fansly'
    assert specs.has_cloudflare is True
    assert specs.max_text_length == 3000


def test_fansly_prefill_delay():
    assert FanslyPlatform.PREFILL_DELAY_MS == 1500


def test_fansly_build_result_not_confirmed():
    p = FanslyPlatform(account_id='fansly_1', profile_name='model')
    result = p.build_result()
    assert result.success is False
    assert result.error_code == 'WV-SUBMIT-TIMEOUT'


def test_fansly_session_requires_auth_cookie(monkeypatch, tmp_path):
    import src.platforms.base_webview as base_webview

    monkeypatch.setattr(base_webview, 'get_app_data_dir', lambda: tmp_path)
    platform = FanslyPlatform(account_id='fansly_1')
    cookie_path = tmp_path / 'webprofiles' / 'fansly_1' / 'Cookies'

    future_expiry = 20_000_000_000_000_000
    _write_cookie(cookie_path, '.fansly.com', '_ga', future_expiry)
    assert platform.has_valid_session() is False

    _write_cookie(cookie_path, '.fansly.com', 'fansly-d', future_expiry)
    assert platform.has_valid_session() is True


# ── FetLife ─────────────────────────────────────────────────────────


def test_fetlife_platform_name():
    p = FetLifePlatform(account_id='fetlife_1', profile_name='rinmodel')
    assert p.get_platform_name() == 'FetLife (rinmodel)'


def test_fetlife_specs():
    p = FetLifePlatform(account_id='fetlife_1')
    specs = p.get_specs()
    assert specs.platform_name == 'FetLife'
    assert specs.has_cloudflare is False
    assert specs.max_text_length is None


def test_fetlife_composer_url():
    assert FetLifePlatform.COMPOSER_URL == 'https://fetlife.com/posts/new?source=Feed'


def test_fetlife_login_url():
    assert FetLifePlatform.LOGIN_URL == 'https://fetlife.com/login'


def test_fetlife_selects_video_composer_url():
    p = FetLifePlatform(account_id='fetlife_1')
    p.prepare_post('hello', [Path('/tmp/sample.mp4')])
    assert p.get_composer_url() == 'https://fetlife.com/videos/new?source=Main+Navigation'


def test_fetlife_selects_image_composer_url():
    p = FetLifePlatform(account_id='fetlife_1')
    p.prepare_post('hello', [Path('/tmp/sample.png')])
    assert p.get_composer_url() == 'https://fetlife.com/pictures/new?source=Main+Navigation'


def test_fetlife_selects_text_composer_url_for_text_only():
    p = FetLifePlatform(account_id='fetlife_1')
    p.prepare_post('hello', [])
    assert p.get_composer_url() == 'https://fetlife.com/posts/new?source=Feed'


def test_fetlife_success_url_pattern():
    import re

    pattern = FetLifePlatform.SUCCESS_URL_PATTERN
    assert re.search(pattern, 'https://fetlife.com/users/12345/statuses/67890')
    assert re.search(pattern, 'https://fetlife.com/users/12345/posts/67890')
    assert re.search(pattern, 'https://fetlife.com/posts/67890')
    assert re.search(pattern, 'https://fetlife.com/pictures/67890')
    assert re.search(pattern, 'https://fetlife.com/videos/67890')
    assert not re.search(pattern, 'https://fetlife.com/')


def test_fetlife_session_requires_auth_cookie(monkeypatch, tmp_path):
    import src.platforms.base_webview as base_webview

    monkeypatch.setattr(base_webview, 'get_app_data_dir', lambda: tmp_path)
    platform = FetLifePlatform(account_id='fetlife_1')
    cookie_path = tmp_path / 'webprofiles' / 'fetlife_1' / 'Cookies'

    future_expiry = 20_000_000_000_000_000
    _write_cookie(cookie_path, '.fetlife.com', 'cf_clearance', future_expiry)
    assert platform.has_valid_session() is False

    _write_cookie(cookie_path, '.fetlife.com', '_fl_sessionid', future_expiry)
    assert platform.has_valid_session() is True


def test_fetlife_build_result_confirmed_with_url():
    p = FetLifePlatform(account_id='fetlife_1', profile_name='model')
    p._post_confirmed = True
    p._captured_post_url = 'https://fetlife.com/users/123/statuses/456'
    result = p.build_result()
    assert result.success is True
    assert result.post_url == 'https://fetlife.com/users/123/statuses/456'
    assert result.url_captured is True
