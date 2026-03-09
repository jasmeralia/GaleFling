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
    assert FetLifePlatform.COMPOSER_URL == 'https://fetlife.com/statuses/new'


def test_fetlife_success_url_pattern():
    import re

    pattern = FetLifePlatform.SUCCESS_URL_PATTERN
    assert re.search(pattern, 'https://fetlife.com/users/12345/statuses/67890')
    assert not re.search(pattern, 'https://fetlife.com/')


def test_fetlife_build_result_confirmed_with_url():
    p = FetLifePlatform(account_id='fetlife_1', profile_name='model')
    p._post_confirmed = True
    p._captured_post_url = 'https://fetlife.com/users/123/statuses/456'
    result = p.build_result()
    assert result.success is True
    assert result.post_url == 'https://fetlife.com/users/123/statuses/456'
    assert result.url_captured is True
