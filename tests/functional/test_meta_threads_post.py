"""Functional tests for Threads API posting — live calls using real credentials.

Credentials are read from tests/functional/.env:
    META_THREADS_ACCESS_TOKEN — long-lived Threads user token
    META_THREADS_USER_ID      — numeric Threads user ID

Media posts (image, video, carousel) additionally require AWS staging credentials:
    META_AWS_ACCESS_KEY_ID
    META_AWS_SECRET_ACCESS_KEY
    META_AWS_REGION          (default: us-west-2)
    META_AWS_BUCKET
"""

from __future__ import annotations

import contextlib
import uuid

import pytest
import requests

THREADS_API_BASE = 'https://graph.threads.net/v1.0'


def _make_auth(creds: dict, aws_creds: dict | None = None):
    """Build a minimal AuthManager stand-in from raw credential dict."""

    class _Auth:
        def get_account_credentials(self, account_id):
            return {
                'access_token': creds['access_token'],
                'user_id': creds['user_id'],
                'provider': 'meta_threads',
            }

        def get_aws_media_staging_credentials(self):
            return aws_creds

    return _Auth()


def _delete_post(access_token: str, post_id: str) -> None:
    """Best-effort deletion of a published Threads post."""
    with contextlib.suppress(Exception):
        requests.delete(
            f'{THREADS_API_BASE}/{post_id}',
            params={'access_token': access_token},
            timeout=15,
        )


# ── Connection tests ──────────────────────────────────────────────────────────


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


# ── Text post tests ───────────────────────────────────────────────────────────


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


# ── Image post tests ──────────────────────────────────────────────────────────


@pytest.mark.functional
class TestMetaThreadsImagePost:
    """Single-image Threads posts via the Threads API + S3 staging."""

    def test_single_image_post(self, meta_threads_credentials, meta_aws_credentials, sample_jpeg):
        """Stage a JPEG to S3, post it to Threads, verify permalink, then delete."""
        from src.platforms.meta_threads import MetaThreadsPlatform

        tag = uuid.uuid4().hex[:8]
        caption = f'GaleFling image test {tag} — safe to delete'

        platform = MetaThreadsPlatform(_make_auth(meta_threads_credentials, meta_aws_credentials))
        result = platform.post(caption, media_paths=[sample_jpeg])

        assert result.success, f'Image post failed: {result.error_code} — {result.error_message}'
        assert result.platform == 'Threads'
        post_id = result.raw_response.get('id')
        assert post_id

        if result.post_url:
            assert result.post_url.startswith('https://www.threads.net/')

        # Cleanup
        _delete_post(meta_threads_credentials['access_token'], post_id)

    def test_png_image_post(self, meta_threads_credentials, meta_aws_credentials, sample_png):
        """PNG images must also be accepted by the Threads API."""
        from src.platforms.meta_threads import MetaThreadsPlatform

        tag = uuid.uuid4().hex[:8]
        caption = f'GaleFling PNG test {tag} — safe to delete'

        platform = MetaThreadsPlatform(_make_auth(meta_threads_credentials, meta_aws_credentials))
        result = platform.post(caption, media_paths=[sample_png])

        assert result.success, f'PNG post failed: {result.error_code} — {result.error_message}'
        post_id = result.raw_response.get('id')
        assert post_id

        # Cleanup
        _delete_post(meta_threads_credentials['access_token'], post_id)


# ── Video post tests ──────────────────────────────────────────────────────────


@pytest.mark.functional
class TestMetaThreadsVideoPost:
    """Video Threads posts via the Threads API + S3 staging."""

    def test_video_post(self, meta_threads_credentials, meta_aws_credentials, sample_video):
        """Stage an MP4 to S3, post it to Threads, verify success, then delete."""
        from src.platforms.meta_threads import MetaThreadsPlatform

        tag = uuid.uuid4().hex[:8]
        caption = f'GaleFling video test {tag} — safe to delete'

        platform = MetaThreadsPlatform(_make_auth(meta_threads_credentials, meta_aws_credentials))
        result = platform.post(caption, media_paths=[sample_video])

        assert result.success, f'Video post failed: {result.error_code} — {result.error_message}'
        assert result.platform == 'Threads'
        post_id = result.raw_response.get('id')
        assert post_id

        # Cleanup
        _delete_post(meta_threads_credentials['access_token'], post_id)


# ── Carousel post tests ───────────────────────────────────────────────────────


@pytest.mark.functional
class TestMetaThreadsCarouselPost:
    """Multi-item carousel Threads posts via the Threads API + S3 staging."""

    def test_carousel_two_images(
        self, meta_threads_credentials, meta_aws_credentials, sample_jpeg, sample_png
    ):
        """Post a 2-image carousel, verify the carousel is published, then delete."""
        from src.platforms.meta_threads import MetaThreadsPlatform

        tag = uuid.uuid4().hex[:8]
        caption = f'GaleFling carousel test {tag} — safe to delete'

        platform = MetaThreadsPlatform(_make_auth(meta_threads_credentials, meta_aws_credentials))
        result = platform.post(caption, media_paths=[sample_jpeg, sample_png])

        assert result.success, f'Carousel post failed: {result.error_code} — {result.error_message}'
        assert result.platform == 'Threads'
        post_id = result.raw_response.get('id')
        assert post_id

        # Cleanup
        _delete_post(meta_threads_credentials['access_token'], post_id)
