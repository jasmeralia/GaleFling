"""Functional tests for Facebook Page API posting — live calls using real credentials.

Credentials are read from tests/functional/.env:
    META_FACEBOOK_PAGE_ACCESS_TOKEN — long-lived Page access token
    META_FACEBOOK_PAGE_ID           — Facebook Page ID (numeric string)
"""

from __future__ import annotations

import contextlib

import pytest
import requests

from tests.functional.conftest import mutating_post_text

FB_GRAPH_BASE = 'https://graph.facebook.com/v25.0'


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


def _facebook_post_id(raw_response: dict) -> str:
    """Return the feed post ID when present, else the object ID."""
    return raw_response.get('post_id') or raw_response.get('id', '')


def _delete_post(page_access_token: str, post_id: str) -> None:
    """Best-effort deletion of a Facebook Page post or uploaded object."""
    if not post_id:
        return
    with contextlib.suppress(Exception):
        requests.delete(
            f'{FB_GRAPH_BASE}/{post_id}',
            params={'access_token': page_access_token},
            timeout=15,
        )


@pytest.mark.functional
@pytest.mark.non_mutating
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

    def test_connection_returns_page_name(self, meta_facebook_credentials):
        """Profile fetch: Graph API must return a page name for the token."""
        resp = requests.get(
            f'{FB_GRAPH_BASE}/{meta_facebook_credentials["page_id"]}',
            params={
                'fields': 'name',
                'access_token': meta_facebook_credentials['page_access_token'],
            },
            timeout=15,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json().get('name')

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
@pytest.mark.non_mutating
class TestMetaFacebookPageValidation:
    """Pre-post validation — errors returned before any network I/O."""

    def test_text_too_long_rejected(self, meta_facebook_credentials):
        """A post exceeding 63206 characters should be rejected before API call."""
        from src.platforms.meta_facebook_page import MetaFacebookPagePlatform

        text = 'A' * 63207
        platform = MetaFacebookPagePlatform(_make_auth(meta_facebook_credentials))
        result = platform.post(text)

        assert not result.success
        assert result.error_code == 'POST-TEXT-TOO-LONG'

    def test_webp_image_rejected(self, meta_facebook_credentials, sample_webp):
        """WEBP is not in Facebook Page specs; reject before upload."""
        from src.platforms.meta_facebook_page import MetaFacebookPagePlatform

        platform = MetaFacebookPagePlatform(_make_auth(meta_facebook_credentials))
        result = platform.post('caption', media_paths=[sample_webp])

        assert not result.success
        assert result.error_code == 'IMG-INVALID-FORMAT'


@pytest.mark.functional
@pytest.mark.mutating
class TestMetaFacebookPageTextPost:
    def test_text_post(self, meta_facebook_credentials):
        """Post a text-only update to the Facebook Page and verify success."""
        from src.platforms.meta_facebook_page import MetaFacebookPagePlatform

        text = mutating_post_text()

        platform = MetaFacebookPagePlatform(_make_auth(meta_facebook_credentials))
        result = platform.post(text)

        assert result.success, f'Text post failed: {result.error_code} — {result.error_message}'
        assert result.platform == 'Facebook Page'
        post_id = _facebook_post_id(result.raw_response)
        assert post_id

        # Cleanup
        _delete_post(meta_facebook_credentials['page_access_token'], post_id)


@pytest.mark.functional
@pytest.mark.mutating
class TestMetaFacebookPagePhotoPost:
    def test_photo_post(self, meta_facebook_credentials, sample_jpeg):
        """Upload a single photo to the Facebook Page and verify success."""
        from src.platforms.meta_facebook_page import MetaFacebookPagePlatform

        caption = mutating_post_text()

        platform = MetaFacebookPagePlatform(_make_auth(meta_facebook_credentials))
        result = platform.post(caption, media_paths=[sample_jpeg])

        assert result.success, f'Photo post failed: {result.error_code} — {result.error_message}'
        assert result.platform == 'Facebook Page'
        post_id = _facebook_post_id(result.raw_response)
        assert post_id

        # Cleanup
        _delete_post(meta_facebook_credentials['page_access_token'], post_id)

    def test_multi_photo_post(self, meta_facebook_credentials, sample_jpeg, sample_png):
        """Upload two photos as a multi-photo feed post and verify success."""
        from src.platforms.meta_facebook_page import MetaFacebookPagePlatform

        caption = mutating_post_text()

        platform = MetaFacebookPagePlatform(_make_auth(meta_facebook_credentials))
        result = platform.post(caption, media_paths=[sample_jpeg, sample_png])

        assert result.success, (
            f'Multi-photo post failed: {result.error_code} — {result.error_message}'
        )
        assert result.platform == 'Facebook Page'
        post_id = _facebook_post_id(result.raw_response)
        assert post_id

        # Cleanup
        _delete_post(meta_facebook_credentials['page_access_token'], post_id)


@pytest.mark.functional
@pytest.mark.mutating
class TestMetaFacebookPageVideoPost:
    def test_video_post(self, meta_facebook_credentials, sample_video):
        """Upload a video to the Facebook Page and verify success."""
        from src.platforms.meta_facebook_page import MetaFacebookPagePlatform

        description = mutating_post_text()

        platform = MetaFacebookPagePlatform(_make_auth(meta_facebook_credentials))
        result = platform.post(description, media_paths=[sample_video])

        assert result.success, f'Video post failed: {result.error_code} — {result.error_message}'
        assert result.platform == 'Facebook Page'
        post_id = _facebook_post_id(result.raw_response)
        assert post_id

        # Cleanup — video uploads return a video object ID; Graph DELETE removes it.
        _delete_post(meta_facebook_credentials['page_access_token'], post_id)
