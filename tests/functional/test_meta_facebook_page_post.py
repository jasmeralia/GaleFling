"""Functional tests for Facebook Page API posting — live calls using real credentials.

Credentials are read from tests/functional/.env:
    META_FACEBOOK_PAGE_ACCESS_TOKEN — long-lived Page access token
    META_FACEBOOK_PAGE_ID           — Facebook Page ID (numeric string)
"""

from __future__ import annotations

import uuid

import pytest


def _make_auth(creds: dict):
    """Build a minimal AuthManager stand-in from raw credential dict."""

    class _Auth:
        def get_account_credentials(self, account_id):
            return {
                'page_access_token': creds['page_access_token'],
                'page_id': creds['page_id'],
                'provider': 'meta_facebook_page',
            }

    return _Auth()


@pytest.mark.functional
class TestMetaFacebookPageConnection:
    def test_authenticate(self, meta_facebook_credentials):
        from src.platforms.meta_facebook_page import MetaFacebookPagePlatform

        platform = MetaFacebookPagePlatform(_make_auth(meta_facebook_credentials))
        ok, err = platform.authenticate()
        assert ok, f'authenticate() failed with error: {err}'
        assert err is None

    def test_connection(self, meta_facebook_credentials):
        from src.platforms.meta_facebook_page import MetaFacebookPagePlatform

        platform = MetaFacebookPagePlatform(_make_auth(meta_facebook_credentials))
        ok, err = platform.test_connection()
        assert ok, f'test_connection() failed with error: {err}'
        assert err is None

    def test_connection_bad_token(self):
        from src.platforms.meta_facebook_page import MetaFacebookPagePlatform

        class _BadAuth:
            def get_account_credentials(self, _account_id):
                return {'page_access_token': 'INVALID_TOKEN', 'page_id': '12345'}

        platform = MetaFacebookPagePlatform(_BadAuth())
        ok, err = platform.test_connection()
        assert not ok
        assert err in ('FB-AUTH-EXPIRED', 'FB-AUTH-INVALID')


@pytest.mark.functional
class TestMetaFacebookPageTextPost:
    def test_text_post(self, meta_facebook_credentials):
        """Post a text-only update to the Facebook Page and verify success."""
        from src.platforms.meta_facebook_page import MetaFacebookPagePlatform

        tag = uuid.uuid4().hex[:8]
        text = f'GaleFling functional test {tag} — safe to delete'

        platform = MetaFacebookPagePlatform(_make_auth(meta_facebook_credentials))
        result = platform.post(text)

        assert result.success, f'Text post failed: {result.error_code} — {result.error_message}'
        assert result.platform == 'Facebook Page'
        assert result.raw_response.get('id')

    def test_text_too_long_rejected(self, meta_facebook_credentials):
        """A post exceeding 63206 characters should be rejected before API call."""
        from src.platforms.meta_facebook_page import MetaFacebookPagePlatform

        text = 'A' * 63207
        platform = MetaFacebookPagePlatform(_make_auth(meta_facebook_credentials))
        result = platform.post(text)

        assert not result.success
        assert result.error_code == 'POST-TEXT-TOO-LONG'


@pytest.mark.functional
class TestMetaFacebookPagePhotoPost:
    def test_photo_post(self, meta_facebook_credentials, sample_jpeg):
        """Upload a single photo to the Facebook Page and verify success."""
        from src.platforms.meta_facebook_page import MetaFacebookPagePlatform

        tag = uuid.uuid4().hex[:8]
        caption = f'GaleFling photo test {tag} — safe to delete'

        platform = MetaFacebookPagePlatform(_make_auth(meta_facebook_credentials))
        result = platform.post(caption, media_paths=[sample_jpeg])

        assert result.success, f'Photo post failed: {result.error_code} — {result.error_message}'
        assert result.platform == 'Facebook Page'
