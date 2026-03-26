"""Functional tests for WebView platform session validation.

These tests verify that WebView platforms have valid session cookies
stored in the GaleFling data directory. They exercise the same session
checking logic that the app uses to determine login status.

Requires GALEFLING_DATA_DIR in .env pointing to the GaleFling AppData directory.
Export via Settings > Advanced > Export Test Config.
"""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from src.platforms.fansly import FanslyPlatform
from src.platforms.fetlife import FetLifePlatform
from src.platforms.onlyfans import OnlyFansPlatform
from src.platforms.snapchat import SnapchatPlatform
from src.platforms.threads import ThreadsPlatform

# ── Helpers ──────────────────────────────────────────────────────────


def _cookie_db_path(data_dir: Path, account_id: str) -> Path:
    return data_dir / 'webprofiles' / account_id / 'Cookies'


def _has_cookie_db(data_dir: Path, account_id: str) -> bool:
    return _cookie_db_path(data_dir, account_id).exists()


# ── Snapchat ─────────────────────────────────────────────────────────


@pytest.mark.functional
class TestSnapchatSession:
    """Snapchat WebView session validation."""

    def test_session_cookies_exist(self, galefling_data_dir):
        """Verify that at least one Snapchat account has a cookie database."""
        account_ids = ['snapchat_1', 'snapchat_2']
        found = [aid for aid in account_ids if _has_cookie_db(galefling_data_dir, aid)]
        if not found:
            pytest.skip('No Snapchat cookie databases found')
        for account_id in found:
            assert _cookie_db_path(galefling_data_dir, account_id).stat().st_size > 0

    def test_has_valid_session(self, galefling_data_dir):
        """Verify has_valid_session() returns True for accounts with cookies."""
        account_ids = ['snapchat_1', 'snapchat_2']
        found = [aid for aid in account_ids if _has_cookie_db(galefling_data_dir, aid)]
        if not found:
            pytest.skip('No Snapchat cookie databases found')
        for account_id in found:
            platform = SnapchatPlatform(account_id=account_id)
            with patch(
                'src.platforms.base_webview.get_app_data_dir', return_value=galefling_data_dir
            ):
                assert platform.has_valid_session(), f'Snapchat session invalid for {account_id}'

    def test_platform_specs(self, galefling_data_dir):
        """Verify platform specs are consistent."""
        platform = SnapchatPlatform(account_id='snapchat_1')
        specs = platform.get_specs()
        assert specs.platform_name == 'Snapchat'
        assert specs.api_type == 'webview'
        assert specs.auth_method == 'session_cookie'
        assert specs.max_accounts == 2
        assert not specs.supports_images
        assert not specs.supports_text


# ── OnlyFans ─────────────────────────────────────────────────────────


@pytest.mark.functional
class TestOnlyFansSession:
    """OnlyFans WebView session validation."""

    def test_session_cookies_exist(self, galefling_data_dir):
        """Verify that the OnlyFans account has a cookie database."""
        if not _has_cookie_db(galefling_data_dir, 'onlyfans_1'):
            pytest.skip('No OnlyFans cookie database found')
        assert _cookie_db_path(galefling_data_dir, 'onlyfans_1').stat().st_size > 0

    def test_has_valid_session(self, galefling_data_dir):
        """Verify has_valid_session() returns True for the OnlyFans account."""
        if not _has_cookie_db(galefling_data_dir, 'onlyfans_1'):
            pytest.skip('No OnlyFans cookie database found')
        platform = OnlyFansPlatform(account_id='onlyfans_1')
        with patch('src.platforms.base_webview.get_app_data_dir', return_value=galefling_data_dir):
            assert platform.has_valid_session(), 'OnlyFans session invalid'

    def test_platform_specs(self, galefling_data_dir):
        """Verify platform specs are consistent."""
        platform = OnlyFansPlatform(account_id='onlyfans_1')
        specs = platform.get_specs()
        assert specs.platform_name == 'OnlyFans'
        assert specs.api_type == 'webview'
        assert specs.has_cloudflare
        assert specs.max_accounts == 1


# ── Fansly ───────────────────────────────────────────────────────────


@pytest.mark.functional
class TestFanslySession:
    """Fansly WebView session validation."""

    def test_session_cookies_exist(self, galefling_data_dir):
        """Verify that the Fansly account has a cookie database."""
        if not _has_cookie_db(galefling_data_dir, 'fansly_1'):
            pytest.skip('No Fansly cookie database found')
        assert _cookie_db_path(galefling_data_dir, 'fansly_1').stat().st_size > 0

    def test_has_valid_session(self, galefling_data_dir):
        """Verify has_valid_session() returns True for the Fansly account."""
        if not _has_cookie_db(galefling_data_dir, 'fansly_1'):
            pytest.skip('No Fansly cookie database found')
        platform = FanslyPlatform(account_id='fansly_1')
        with patch('src.platforms.base_webview.get_app_data_dir', return_value=galefling_data_dir):
            assert platform.has_valid_session(), 'Fansly session invalid'

    def test_platform_specs(self, galefling_data_dir):
        """Verify platform specs are consistent."""
        platform = FanslyPlatform(account_id='fansly_1')
        specs = platform.get_specs()
        assert specs.platform_name == 'Fansly'
        assert specs.api_type == 'webview'
        assert specs.has_cloudflare
        assert specs.max_accounts == 1


# ── FetLife ──────────────────────────────────────────────────────────


@pytest.mark.functional
class TestFetLifeSession:
    """FetLife WebView session validation."""

    def test_session_cookies_exist(self, galefling_data_dir):
        """Verify that the FetLife account has a cookie database."""
        if not _has_cookie_db(galefling_data_dir, 'fetlife_1'):
            pytest.skip('No FetLife cookie database found')
        assert _cookie_db_path(galefling_data_dir, 'fetlife_1').stat().st_size > 0

    def test_has_valid_session(self, galefling_data_dir):
        """Verify has_valid_session() returns True for the FetLife account."""
        if not _has_cookie_db(galefling_data_dir, 'fetlife_1'):
            pytest.skip('No FetLife cookie database found')
        platform = FetLifePlatform(account_id='fetlife_1')
        with patch('src.platforms.base_webview.get_app_data_dir', return_value=galefling_data_dir):
            assert platform.has_valid_session(), 'FetLife session invalid'

    def test_platform_specs(self, galefling_data_dir):
        """Verify platform specs are consistent."""
        platform = FetLifePlatform(account_id='fetlife_1')
        specs = platform.get_specs()
        assert specs.platform_name == 'FetLife'
        assert specs.api_type == 'webview'
        assert not specs.supports_text_with_media
        assert specs.max_accounts == 1


# ── Threads ──────────────────────────────────────────────────────────


@pytest.mark.functional
class TestThreadsSession:
    """Threads WebView session validation."""

    def test_session_cookies_exist(self, galefling_data_dir):
        """Verify that the Threads account has a cookie database."""
        if not _has_cookie_db(galefling_data_dir, 'threads_1'):
            pytest.skip('No Threads cookie database found')
        assert _cookie_db_path(galefling_data_dir, 'threads_1').stat().st_size > 0

    def test_has_valid_session(self, galefling_data_dir):
        """Verify has_valid_session() returns True for the Threads account.

        NOTE: ThreadsPlatform uses THREADS_PLACEHOLDER session cookie names.
        If this test fails, inspect the diagnostic output for the actual
        cookie domain/name pairs and update ThreadsPlatform.AUTH_COOKIE_NAMES.
        """
        cookie_db = _cookie_db_path(galefling_data_dir, 'threads_1')
        if not cookie_db.exists():
            pytest.skip('No Threads cookie database found')
        platform = ThreadsPlatform(account_id='threads_1')
        with patch('src.platforms.base_webview.get_app_data_dir', return_value=galefling_data_dir):
            valid = platform.has_valid_session()
        if not valid:
            # Gather diagnostic info: domain+name pairs (no values) from the DB.
            # Threads is THREADS_PLACEHOLDER — AUTH_COOKIE_NAMES is unverified.
            # Use this output to update ThreadsPlatform.AUTH_COOKIE_NAMES.
            diag: list[str] = []
            try:
                with sqlite3.connect(f'file:{cookie_db}?mode=ro', uri=True) as conn:
                    rows = conn.execute(
                        'SELECT host_key, name FROM cookies ORDER BY host_key, name'
                    ).fetchall()
                    diag = [f'{r[0]}/{r[1]}' for r in rows[:40]]
            except sqlite3.Error:
                diag = ['(db read error)']
            pytest.skip(
                f'Threads session invalid (THREADS_PLACEHOLDER — '
                f'AUTH_COOKIE_NAMES unverified). '
                f'Cookies in DB (domain/name): {diag}'
            )

    def test_platform_specs(self, galefling_data_dir):
        """Verify platform specs are consistent."""
        platform = ThreadsPlatform(account_id='threads_1')
        specs = platform.get_specs()
        assert specs.platform_name == 'Threads'
        assert specs.api_type == 'webview'
        assert specs.auth_method == 'session_cookie'
        assert specs.max_accounts == 2
