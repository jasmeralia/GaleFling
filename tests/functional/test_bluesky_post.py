"""Functional tests for Bluesky — live AT Protocol calls via BlueskyPlatform."""

from __future__ import annotations

import contextlib

import pytest
from atproto import Client as BskyClient

from tests.functional.conftest import mutating_post_text

BSKY_SERVICE = 'https://bsky.social'


def _make_auth(creds: dict):
    """Build a minimal AuthManager stand-in from raw credential dict."""

    class _Auth:
        def get_bluesky_auth(self):
            return {
                'identifier': creds['identifier'],
                'app_password': creds['app_password'],
                'service': BSKY_SERVICE,
            }

        def get_bluesky_auth_alt(self):
            return None

    return _Auth()


def _delete_post(creds: dict, uri: str) -> None:
    """Best-effort deletion of a Bluesky post by AT URI."""
    if not uri:
        return
    with contextlib.suppress(Exception):
        client = BskyClient(base_url=BSKY_SERVICE)
        client.login(creds['identifier'], creds['app_password'])
        client.delete_post(uri)


@pytest.mark.functional
@pytest.mark.non_mutating
class TestBlueskyConnection:
    """Auth and connection tests — run first to fail fast on bad credentials."""

    def test_authenticate(self, bluesky_credentials):
        from src.platforms.bluesky import BlueskyPlatform

        platform = BlueskyPlatform(_make_auth(bluesky_credentials))
        ok, err = platform.authenticate()
        assert ok, f'authenticate() failed with error: {err}'
        assert err is None

    def test_connection(self, bluesky_credentials):
        from src.platforms.bluesky import BlueskyPlatform

        platform = BlueskyPlatform(_make_auth(bluesky_credentials))
        ok, err = platform.test_connection()
        assert ok, f'test_connection() failed with error: {err}'
        assert err is None

    def test_connection_returns_handle(self, bluesky_credentials):
        """Profile fetch: logged-in session must expose a handle."""
        client = BskyClient(base_url=BSKY_SERVICE)
        profile = client.login(
            bluesky_credentials['identifier'],
            bluesky_credentials['app_password'],
        )
        assert profile.handle

        fetched = client.get_profile(client.me.did)
        assert fetched.handle == profile.handle

    def test_connection_bad_credentials(self):
        from src.platforms.bluesky import BlueskyPlatform

        class _BadAuth:
            def get_bluesky_auth(self):
                return {
                    'identifier': 'invalid.example',
                    'app_password': 'invalid-password',
                    'service': BSKY_SERVICE,
                }

            def get_bluesky_auth_alt(self):
                return None

        platform = BlueskyPlatform(_BadAuth())
        ok, err = platform.test_connection()
        assert not ok
        assert err == 'BS-AUTH-INVALID'


@pytest.mark.functional
@pytest.mark.non_mutating
class TestBlueskyValidation:
    """Pre-post rejection without creating a live post."""

    def test_character_limit_enforcement(self, bluesky_credentials):
        """Posts exceeding 300 graphemes must fail before a record is created."""
        from src.platforms.bluesky import BlueskyPlatform

        platform = BlueskyPlatform(_make_auth(bluesky_credentials))
        platform.authenticate()
        result = platform.post('A' * 301)

        assert not result.success
        assert result.error_code == 'POST-TEXT-TOO-LONG'


@pytest.mark.functional
@pytest.mark.mutating
class TestBlueskyTextPost:
    """Text-only posting and deletion via BlueskyPlatform."""

    def test_text_post_and_delete(self, bluesky_credentials):
        from src.platforms.bluesky import BlueskyPlatform

        text = mutating_post_text()

        platform = BlueskyPlatform(_make_auth(bluesky_credentials))
        result = platform.post(text)

        assert result.success, f'Text post failed: {result.error_code} — {result.error_message}'
        assert result.platform == 'Bluesky'
        uri = result.raw_response.get('uri')
        assert uri
        assert result.post_url.startswith('https://bsky.app/profile/')

        _delete_post(bluesky_credentials, uri)

    def test_post_with_url_facets(self, bluesky_credentials):
        """URL facets must be detected and published end-to-end."""
        from src.platforms.bluesky import BlueskyPlatform

        text = mutating_post_text('https://example.com')

        platform = BlueskyPlatform(_make_auth(bluesky_credentials))
        result = platform.post(text)

        assert result.success, f'Facet post failed: {result.error_code} — {result.error_message}'
        uri = result.raw_response.get('uri')
        assert uri

        _delete_post(bluesky_credentials, uri)


@pytest.mark.functional
@pytest.mark.mutating
class TestBlueskyImagePost:
    """Image upload and posting via BlueskyPlatform."""

    def test_single_image_post(self, bluesky_credentials, sample_jpeg):
        from src.platforms.bluesky import BlueskyPlatform

        caption = mutating_post_text()

        platform = BlueskyPlatform(_make_auth(bluesky_credentials))
        result = platform.post(caption, media_paths=[sample_jpeg])

        assert result.success, f'Image post failed: {result.error_code} — {result.error_message}'
        uri = result.raw_response.get('uri')
        assert uri

        _delete_post(bluesky_credentials, uri)

    def test_png_image_post(self, bluesky_credentials, sample_png):
        from src.platforms.bluesky import BlueskyPlatform

        caption = mutating_post_text()

        platform = BlueskyPlatform(_make_auth(bluesky_credentials))
        result = platform.post(caption, media_paths=[sample_png])

        assert result.success, f'PNG post failed: {result.error_code} — {result.error_message}'
        uri = result.raw_response.get('uri')
        assert uri

        _delete_post(bluesky_credentials, uri)

    def test_multiple_images_post(self, bluesky_credentials, sample_jpeg, sample_png):
        from src.platforms.bluesky import BlueskyPlatform

        caption = mutating_post_text()

        platform = BlueskyPlatform(_make_auth(bluesky_credentials))
        result = platform.post(caption, media_paths=[sample_jpeg, sample_png])

        assert result.success, (
            f'Multi-image post failed: {result.error_code} — {result.error_message}'
        )
        uri = result.raw_response.get('uri')
        assert uri

        _delete_post(bluesky_credentials, uri)


@pytest.mark.functional
@pytest.mark.mutating
class TestBlueskyVideoPost:
    """Video upload and posting via BlueskyPlatform."""

    def test_video_post(self, bluesky_credentials, sample_video):
        from src.platforms.bluesky import BlueskyPlatform

        caption = mutating_post_text()

        platform = BlueskyPlatform(_make_auth(bluesky_credentials))
        result = platform.post(caption, media_paths=[sample_video])

        assert result.success, f'Video post failed: {result.error_code} — {result.error_message}'
        uri = result.raw_response.get('uri')
        assert uri

        _delete_post(bluesky_credentials, uri)
