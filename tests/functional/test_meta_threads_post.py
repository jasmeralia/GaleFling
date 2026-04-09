"""Functional tests for Threads API posting — live calls using real credentials.

Credentials are read from tests/functional/.env:
    META_THREADS_ACCESS_TOKEN — long-lived Threads user token
    META_THREADS_USER_ID      — numeric Threads user ID
"""

from __future__ import annotations

import uuid

import pytest

THREADS_API_BASE = 'https://graph.threads.net/v1.0'


def _make_auth(creds: dict):
    """Build a minimal AuthManager stand-in from raw credential dict."""

    class _Auth:
        def get_account_credentials(self, account_id):
            return {
                'access_token': creds['access_token'],
                'user_id': creds['user_id'],
                'provider': 'meta_threads',
            }

        def get_aws_media_staging_credentials(self):
            return None

    return _Auth()


@pytest.mark.functional
class TestMetaThreadsConnection:
    def test_authenticate(self, meta_threads_credentials):
        from src.platforms.meta_threads import MetaThreadsPlatform

        platform = MetaThreadsPlatform(_make_auth(meta_threads_credentials))
        ok, err = platform.authenticate()
        assert ok, f'authenticate() failed with error: {err}'
        assert err is None

    def test_connection(self, meta_threads_credentials):
        from src.platforms.meta_threads import MetaThreadsPlatform

        platform = MetaThreadsPlatform(_make_auth(meta_threads_credentials))
        ok, err = platform.test_connection()
        assert ok, f'test_connection() failed with error: {err}'
        assert err is None

    def test_connection_bad_token(self):
        from src.platforms.meta_threads import MetaThreadsPlatform

        class _BadAuth:
            def get_account_credentials(self, _account_id):
                return {'access_token': 'INVALID_TOKEN', 'user_id': '12345'}

            def get_aws_media_staging_credentials(self):
                return None

        platform = MetaThreadsPlatform(_BadAuth())
        ok, err = platform.test_connection()
        assert not ok
        assert err in ('TH-AUTH-EXPIRED', 'TH-AUTH-INVALID')


@pytest.mark.functional
class TestMetaThreadsTextPost:
    def test_text_post(self, meta_threads_credentials):
        """Post a text-only thread and verify success."""
        from src.platforms.meta_threads import MetaThreadsPlatform

        tag = uuid.uuid4().hex[:8]
        text = f'GaleFling functional test {tag} — safe to ignore'

        platform = MetaThreadsPlatform(_make_auth(meta_threads_credentials))
        result = platform.post(text)

        assert result.success, f'Text post failed: {result.error_code} — {result.error_message}'
        assert result.platform == 'Threads'
        assert result.raw_response.get('id')

    def test_text_too_long_rejected(self, meta_threads_credentials):
        """A post exceeding 500 characters should be rejected before API call."""
        from src.platforms.meta_threads import MetaThreadsPlatform

        text = 'A' * 501
        platform = MetaThreadsPlatform(_make_auth(meta_threads_credentials))
        result = platform.post(text)

        assert not result.success
        assert result.error_code == 'POST-TEXT-TOO-LONG'
