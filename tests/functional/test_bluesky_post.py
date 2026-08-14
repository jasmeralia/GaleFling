"""Functional tests for Bluesky — live AT Protocol calls via BlueskyPlatform."""

from __future__ import annotations

import time

import pytest
from atproto import Client as BskyClient

from tests.functional.conftest import mutating_post_text
from tests.functional.functional_cleanup import (
    assert_neutral_live_text,
    finish_mutating_artifact,
    post_tag,
)

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


def _fetch_post(creds: dict, uri: str) -> tuple[object | None, list[str]]:
    """Read a published post back from Bluesky, returning its view and its media kinds.

    Uses ``app.bsky.feed.getPosts``, which returns the *hydrated* view — the record plus
    the resolved embed — rather than ``getRecord``, so media can be asserted from what the
    network actually serves instead of from what we asked it to store.

    Retried briefly: the write is committed when ``send_post`` returns, but the AppView
    that serves ``getPosts`` indexes asynchronously, so a cold read can legitimately miss
    a post that exists.
    """
    client = BskyClient(base_url=BSKY_SERVICE)
    client.login(creds['identifier'], creds['app_password'])
    for attempt in range(5):
        posts = client.get_posts([uri]).posts
        if posts:
            return posts[0], _embed_media_kinds(posts[0].embed)
        if attempt < 4:
            time.sleep(2)
    return None, []


def _embed_media_kinds(embed) -> list[str]:
    """Return one entry per published media item, in Bluesky's own vocabulary.

    Matched on the embed view's ``py_type`` discriminator rather than by duck-typing
    attributes, so an unrecognised embed reports as unknown instead of silently counting
    as no media at all.
    """
    if embed is None:
        return []
    py_type = getattr(embed, 'py_type', None)
    if py_type == 'app.bsky.embed.images#view':
        return ['image'] * len(embed.images)
    if py_type == 'app.bsky.embed.video#view':
        return ['video']
    return [f'unexpected:{py_type}']


def _published_link_facets(post_view) -> list[str]:
    """Return the URIs of every link facet on the published record."""
    facets = getattr(post_view.record, 'facets', None) or []
    return [
        feature.uri
        for facet in facets
        for feature in (getattr(facet, 'features', None) or [])
        if getattr(feature, 'uri', None)
    ]


def _assert_post_published(
    creds: dict, uri: str, text: str, *, media: list[str] | None = None
) -> object:
    """Prove the post exists on Bluesky carrying our tag and media, and return its view.

    ``result.success`` and a returned AT URI are the adapter reporting on itself; only
    reading the record back off the network settles whether anything was published. The
    view is returned so a caller can assert on record detail without a second fetch.
    """
    tag = post_tag(text)
    post_view, media_kinds = _fetch_post(creds, uri)

    assert post_view is not None, (
        f'Bluesky returned {uri} but will not serve it back — nothing was published under tag {tag}'
    )
    assert tag in post_view.record.text, (
        f'Post {uri} does not carry tag {tag} — this is not the post we just created: '
        f'{post_view.record.text!r}'
    )

    assert_neutral_live_text('Bluesky', post_view.record.text)

    expected = sorted(media or [])
    assert sorted(media_kinds) == expected, (
        f'Post {uri} (tag {tag}) published media {sorted(media_kinds)}, expected {expected}'
    )
    return post_view


def _delete_post(creds: dict, uri: str) -> None:
    """Delete a Bluesky post by AT URI.

    ``com.atproto.repo.deleteRecord`` is idempotent, so there is no "already gone"
    outcome to translate — a repeat delete succeeds rather than reporting absence.
    """
    client = BskyClient(base_url=BSKY_SERVICE)
    client.login(creds['identifier'], creds['app_password'])
    client.delete_post(uri)


def _finish_post(creds: dict, text: str, uri: str, url: str | None = None) -> None:
    """Delete the post, or leave it up and report it, per the run's cleanup policy."""
    finish_mutating_artifact(
        'Bluesky',
        text,
        url=url,
        delete=lambda: _delete_post(creds, uri),
    )


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
    """Text-only posting via BlueskyPlatform."""

    def test_text_post(self, bluesky_credentials):
        from src.platforms.bluesky import BlueskyPlatform

        text = mutating_post_text()

        platform = BlueskyPlatform(_make_auth(bluesky_credentials))
        result = platform.post(text)

        assert result.success, f'Text post failed: {result.error_code} — {result.error_message}'
        assert result.platform == 'Bluesky'
        uri = result.raw_response.get('uri')
        assert uri
        assert result.post_url.startswith('https://bsky.app/profile/')

        _assert_post_published(bluesky_credentials, uri, text)
        _finish_post(bluesky_credentials, text, uri, result.post_url)

    def test_post_with_url_facets(self, bluesky_credentials):
        """URL facets must be detected and published end-to-end."""
        from src.platforms.bluesky import BlueskyPlatform

        text = mutating_post_text('https://example.com')

        platform = BlueskyPlatform(_make_auth(bluesky_credentials))
        result = platform.post(text)

        assert result.success, f'Facet post failed: {result.error_code} — {result.error_message}'
        uri = result.raw_response.get('uri')
        assert uri

        # The point of this test: the facet has to survive to the published record, not
        # merely be built locally by detect_urls().
        post = _assert_post_published(bluesky_credentials, uri, text)
        published_links = _published_link_facets(post)
        assert published_links == ['https://example.com'], (
            f'Post {uri} published link facets {published_links}, expected the URL in the '
            f'text — detect_urls() output did not reach the record'
        )

        _finish_post(bluesky_credentials, text, uri, result.post_url)


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

        _assert_post_published(bluesky_credentials, uri, caption, media=['image'])
        _finish_post(bluesky_credentials, caption, uri, result.post_url)

    def test_png_image_post(self, bluesky_credentials, sample_png):
        from src.platforms.bluesky import BlueskyPlatform

        caption = mutating_post_text()

        platform = BlueskyPlatform(_make_auth(bluesky_credentials))
        result = platform.post(caption, media_paths=[sample_png])

        assert result.success, f'PNG post failed: {result.error_code} — {result.error_message}'
        uri = result.raw_response.get('uri')
        assert uri

        _assert_post_published(bluesky_credentials, uri, caption, media=['image'])
        _finish_post(bluesky_credentials, caption, uri, result.post_url)

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

        _assert_post_published(bluesky_credentials, uri, caption, media=['image', 'image'])
        _finish_post(bluesky_credentials, caption, uri, result.post_url)


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

        _assert_post_published(bluesky_credentials, uri, caption, media=['video'])
        _finish_post(bluesky_credentials, caption, uri, result.post_url)
