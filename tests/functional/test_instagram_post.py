"""Functional tests for Instagram — real Graph API calls against a test account.

Credentials are read from tests/functional/.env:
    INSTAGRAM_ACCESS_TOKEN        — long-lived Instagram user access token
    INSTAGRAM_BUSINESS_ACCOUNT_ID — numeric Instagram Business/Creator account ID

Media posts (image, video, carousel) additionally require AWS staging credentials:
    INSTAGRAM_AWS_ACCESS_KEY_ID
    INSTAGRAM_AWS_SECRET_ACCESS_KEY
    INSTAGRAM_AWS_REGION          (default: us-west-2)
    INSTAGRAM_AWS_BUCKET

Instagram requires at least one image or video per post (no text-only posts).
All media is staged to S3 first so the Graph API can fetch it by public URL.
"""

from __future__ import annotations

import contextlib
import uuid

import pytest
import requests

INSTAGRAM_API_BASE = 'https://graph.instagram.com'


def _make_auth(creds: dict, aws_creds: dict | None = None):
    """Build a minimal AuthManager stand-in from raw credential dict."""

    class _Auth:
        def get_account_credentials(self, account_id):
            return {
                'access_token': creds['access_token'],
                'user_id': creds['account_id'],
                'provider': 'meta_instagram',
            }

        def get_aws_media_staging_credentials(self):
            return aws_creds

    return _Auth()


def _delete_media(access_token: str, media_id: str) -> None:
    """Best-effort deletion of a published Instagram media object."""
    with contextlib.suppress(Exception):
        requests.delete(
            f'{INSTAGRAM_API_BASE}/{media_id}',
            params={'access_token': access_token},
            timeout=15,
        )


# ── Connection tests ──────────────────────────────────────────────────────────


@pytest.mark.functional
class TestInstagramConnection:
    """Auth and connection tests — run first to fail fast on bad credentials."""

    def test_authenticate(self, instagram_credentials):
        """Verify authenticate() succeeds with valid credentials."""
        from src.platforms.meta_instagram import MetaInstagramPlatform

        platform = MetaInstagramPlatform(_make_auth(instagram_credentials))
        ok, err = platform.authenticate()
        assert ok, f'authenticate() failed with error: {err}'
        assert err is None

    def test_connection(self, instagram_credentials):
        """Verify test_connection() returns the account username."""
        from src.platforms.meta_instagram import MetaInstagramPlatform

        platform = MetaInstagramPlatform(_make_auth(instagram_credentials))
        ok, err = platform.test_connection()
        assert ok, f'test_connection() failed with error: {err}'
        assert err is None

    def test_connection_bad_token(self):
        """A bogus access token must produce an auth error, not an exception."""
        from src.platforms.meta_instagram import MetaInstagramPlatform

        class _BadAuth:
            def get_account_credentials(self, _account_id):
                return {'access_token': 'INVALID_TOKEN', 'user_id': '12345'}

            def get_aws_media_staging_credentials(self):
                return None

        platform = MetaInstagramPlatform(_BadAuth())
        ok, err = platform.test_connection()
        assert not ok
        assert err in ('IG-AUTH-EXPIRED', 'IG-AUTH-INVALID')


# ── Validation tests ──────────────────────────────────────────────────────────


@pytest.mark.functional
class TestInstagramValidation:
    """Pre-post validation — errors returned before any network I/O."""

    def test_text_only_post_rejected(self, instagram_credentials):
        """Instagram must reject posts with no media attached."""
        from src.platforms.meta_instagram import MetaInstagramPlatform

        platform = MetaInstagramPlatform(_make_auth(instagram_credentials))
        result = platform.post('No image here', media_paths=None)

        assert not result.success
        assert result.error_code == 'POST-FAILED'

    def test_caption_too_long_rejected(self, instagram_credentials):
        """Caption exceeding 2200 characters must be rejected client-side."""
        from src.platforms.meta_instagram import MetaInstagramPlatform

        platform = MetaInstagramPlatform(_make_auth(instagram_credentials))
        result = platform.post('A' * 2201, media_paths=None)

        assert not result.success
        assert result.error_code == 'POST-TEXT-TOO-LONG'


# ── Image post tests ──────────────────────────────────────────────────────────


@pytest.mark.functional
class TestInstagramImagePost:
    """Single-image feed posts via the Instagram Graph API + S3 staging."""

    def test_single_image_post(self, instagram_credentials, instagram_aws_credentials, sample_jpeg):
        """Stage a JPEG to S3, post it to Instagram, verify permalink, then delete."""
        from src.platforms.meta_instagram import MetaInstagramPlatform

        tag = uuid.uuid4().hex[:8]
        caption = f'GaleFling functional test {tag} — safe to delete'

        platform = MetaInstagramPlatform(
            _make_auth(instagram_credentials, instagram_aws_credentials)
        )
        result = platform.post(caption, media_paths=[sample_jpeg])

        assert result.success, f'Image post failed: {result.error_code} — {result.error_message}'
        assert result.platform == 'Instagram'
        media_id = result.raw_response.get('id')
        assert media_id

        if result.post_url:
            assert result.post_url.startswith('https://www.instagram.com/')

        # Cleanup
        _delete_media(instagram_credentials['access_token'], media_id)

    def test_png_image_post(self, instagram_credentials, instagram_aws_credentials, sample_png):
        """PNG images must also be accepted by the API."""
        from src.platforms.meta_instagram import MetaInstagramPlatform

        tag = uuid.uuid4().hex[:8]
        caption = f'GaleFling PNG test {tag} — safe to delete'

        platform = MetaInstagramPlatform(
            _make_auth(instagram_credentials, instagram_aws_credentials)
        )
        result = platform.post(caption, media_paths=[sample_png])

        assert result.success, f'PNG post failed: {result.error_code} — {result.error_message}'
        media_id = result.raw_response.get('id')
        assert media_id

        # Cleanup
        _delete_media(instagram_credentials['access_token'], media_id)


# ── Video post tests ──────────────────────────────────────────────────────────


@pytest.mark.functional
class TestInstagramVideoPost:
    """Video feed posts via the Instagram Graph API + S3 staging."""

    def test_video_post(self, instagram_credentials, instagram_aws_credentials, sample_video):
        """Stage an MP4 to S3, post it as a Reel, verify success, then delete."""
        from src.platforms.meta_instagram import MetaInstagramPlatform

        tag = uuid.uuid4().hex[:8]
        caption = f'GaleFling video test {tag} — safe to delete'

        platform = MetaInstagramPlatform(
            _make_auth(instagram_credentials, instagram_aws_credentials)
        )
        result = platform.post(caption, media_paths=[sample_video])

        assert result.success, f'Video post failed: {result.error_code} — {result.error_message}'
        assert result.platform == 'Instagram'
        media_id = result.raw_response.get('id')
        assert media_id

        # Cleanup
        _delete_media(instagram_credentials['access_token'], media_id)


# ── Carousel post tests ───────────────────────────────────────────────────────


@pytest.mark.functional
class TestInstagramCarouselPost:
    """Multi-image carousel posts via the Instagram Graph API + S3 staging."""

    def test_carousel_two_images(
        self, instagram_credentials, instagram_aws_credentials, sample_jpeg, sample_png
    ):
        """Post a 2-image carousel, verify the carousel container is published."""
        from src.platforms.meta_instagram import MetaInstagramPlatform

        tag = uuid.uuid4().hex[:8]
        caption = f'GaleFling carousel test {tag} — safe to delete'

        platform = MetaInstagramPlatform(
            _make_auth(instagram_credentials, instagram_aws_credentials)
        )
        result = platform.post(caption, media_paths=[sample_jpeg, sample_png])

        assert result.success, f'Carousel post failed: {result.error_code} — {result.error_message}'
        assert result.platform == 'Instagram'
        media_id = result.raw_response.get('id')
        assert media_id

        # Cleanup
        _delete_media(instagram_credentials['access_token'], media_id)
