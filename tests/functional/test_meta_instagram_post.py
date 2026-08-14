"""Functional tests for Instagram — real Graph API calls against a test account.

Credentials are read from tests/functional/.env:
    INSTAGRAM_ACCESS_TOKEN        — long-lived Instagram user access token
    INSTAGRAM_BUSINESS_ACCOUNT_ID — numeric Instagram Business/Creator account ID

Media posts (image, video, carousel) additionally require AWS staging credentials:
    META_AWS_ACCESS_KEY_ID
    META_AWS_SECRET_ACCESS_KEY
    META_AWS_REGION          (default: us-west-2)
    META_AWS_BUCKET

Instagram requires at least one image or video per post (no text-only posts).
All media is staged to S3 first so the Graph API can fetch it by public URL.
"""

from __future__ import annotations

import time

import pytest
import requests

from tests.functional.conftest import mutating_post_text
from tests.functional.functional_cleanup import (
    ArtifactDeleteFailedError,
    assert_neutral_live_text,
    finish_mutating_artifact,
    post_tag,
)

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


#: Enough to prove the media exists, carries our caption, and published what we sent.
#: ``media_product_type`` separates a FEED post from a REELS one — the adapter publishes
#: video as a Reel, so it is worth seeing rather than assuming.
INSTAGRAM_MEDIA_FIELDS = (
    'id,media_type,media_product_type,caption,permalink,children{id,media_type}'
)


def _fetch_media(creds: dict, media_id: str) -> tuple[dict | None, list[str]]:
    """Read a published Instagram media object back, returning it and its media kinds.

    Retried briefly, and deliberately not distinguishing "missing" from "not yet
    readable": Graph answers both with 400 / code 100, so the only safe reading of a
    persistent non-200 is that the media is not there.
    """
    for attempt in range(5):
        resp = requests.get(
            f'{INSTAGRAM_API_BASE}/{media_id}',
            params={'fields': INSTAGRAM_MEDIA_FIELDS, 'access_token': creds['access_token']},
            timeout=15,
        )
        if resp.status_code == 200:
            payload = resp.json()
            return payload, _published_media_kinds(payload)
        if attempt < 4:
            time.sleep(2)
    return None, []


def _published_media_kinds(media_object: dict) -> list[str]:
    """Return one entry per published item, in the Instagram Graph API's own vocabulary.

    A carousel reports ``CAROUSEL_ALBUM`` at the top level and carries the real per-item
    types on its ``children`` edge, so counting attachments means reading the children
    rather than the parent's own ``media_type``. Instagram has no text-only post, so
    unlike Threads there is no empty case.
    """
    media_type = media_object.get('media_type')
    if media_type == 'CAROUSEL_ALBUM':
        children = (media_object.get('children') or {}).get('data') or []
        return [child.get('media_type') for child in children]
    return [media_type]


def _assert_media_published(creds: dict, media_id: str, caption: str, *, media: list[str]) -> dict:
    """Prove the media exists on Instagram carrying our tag and content, and return it.

    ``result.success`` and a returned media ID are the adapter reporting on itself; only
    reading the object back off Graph settles whether anything was published.
    """
    tag = post_tag(caption)
    payload, media_kinds = _fetch_media(creds, media_id)

    assert payload is not None, (
        f'Instagram returned media id {media_id} but Graph will not serve it back — '
        f'nothing was published under tag {tag}'
    )
    published_caption = payload.get('caption') or ''
    assert tag in published_caption, (
        f'Instagram media {media_id} does not carry tag {tag} — this is not the post we '
        f'just created: {published_caption!r}'
    )
    assert_neutral_live_text('Instagram', published_caption)

    assert sorted(media_kinds) == sorted(media), (
        f'Instagram media {media_id} (tag {tag}) published {sorted(media_kinds)}, '
        f'expected {sorted(media)}'
    )
    return payload


def _delete_media(access_token: str, media_id: str) -> None:
    """Delete a published Instagram media object.

    Reports the HTTP status only.  The request URL carries ``access_token`` in its query
    string, so neither the URL nor the response body may reach the log (rule 8).

    There is deliberately no "already gone" mapping. Graph answers a missing object with
    **400 / code 100**, not 404, and its own message for that code is "does not exist,
    cannot be loaded due to missing permissions, or does not support this operation" —
    one status covering three very different causes. Reporting that as "already gone"
    would disguise a delete broken by a missing scope as a benign outcome, which is the
    exact failure this reporting exists to surface.
    """
    resp = requests.delete(
        f'{INSTAGRAM_API_BASE}/{media_id}',
        params={'access_token': access_token},
        timeout=15,
    )
    if resp.status_code != 200:
        raise ArtifactDeleteFailedError(f'HTTP {resp.status_code}')


def _finish_media(creds: dict, caption: str, media_id: str, url: str | None = None) -> None:
    """Delete the media, or leave it up and report it, per the run's cleanup policy."""
    finish_mutating_artifact(
        'Instagram',
        caption,
        url=url,
        delete=lambda: _delete_media(creds['access_token'], media_id),
    )


# ── Connection tests ──────────────────────────────────────────────────────────


@pytest.mark.functional
@pytest.mark.non_mutating
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

    def test_connection_returns_username(self, instagram_credentials):
        """Profile fetch: Graph API must return a username for the token."""
        resp = requests.get(
            f'{INSTAGRAM_API_BASE}/me',
            params={
                'fields': 'username',
                'access_token': instagram_credentials['access_token'],
            },
            timeout=15,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json().get('username')

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
@pytest.mark.non_mutating
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

    def test_webp_image_rejected(self, instagram_credentials, sample_webp):
        """WEBP is not in Instagram specs; reject before any API or S3 staging."""
        from src.platforms.meta_instagram import MetaInstagramPlatform

        platform = MetaInstagramPlatform(_make_auth(instagram_credentials))
        result = platform.post('caption', media_paths=[sample_webp])

        assert not result.success
        assert result.error_code == 'IMG-INVALID-FORMAT'


# ── Image post tests ──────────────────────────────────────────────────────────


@pytest.mark.functional
@pytest.mark.mutating
class TestInstagramImagePost:
    """Single-image feed posts via the Instagram Graph API + S3 staging."""

    def test_single_image_post(self, instagram_credentials, meta_aws_credentials, sample_jpeg):
        """Stage a JPEG to S3, post it to Instagram, verify permalink, then delete."""
        from src.platforms.meta_instagram import MetaInstagramPlatform

        caption = mutating_post_text()

        platform = MetaInstagramPlatform(_make_auth(instagram_credentials, meta_aws_credentials))
        result = platform.post(caption, media_paths=[sample_jpeg])

        assert result.success, f'Image post failed: {result.error_code} — {result.error_message}'
        assert result.platform == 'Instagram'
        media_id = result.raw_response.get('id')
        assert media_id

        # Unconditional: a guarded URL assertion cannot fail when post_url is None,
        # which is precisely the regression worth catching — the Results dialog then
        # has no link to offer the user. Facebook Page video posts shipped in exactly
        # that state, and no test caught it; the artifact reporter did, by printing
        # 'URL: none reported'.
        assert result.post_url, 'no post_url returned — Results would have no link'
        assert result.post_url.startswith('https://www.instagram.com/')

        _assert_media_published(instagram_credentials, media_id, caption, media=['IMAGE'])
        _finish_media(instagram_credentials, caption, media_id, result.post_url)

    def test_png_image_post(self, instagram_credentials, meta_aws_credentials, sample_png):
        """PNG images must also be accepted by the API."""
        from src.platforms.meta_instagram import MetaInstagramPlatform

        caption = mutating_post_text()

        platform = MetaInstagramPlatform(_make_auth(instagram_credentials, meta_aws_credentials))
        result = platform.post(caption, media_paths=[sample_png])

        assert result.success, f'PNG post failed: {result.error_code} — {result.error_message}'
        media_id = result.raw_response.get('id')
        assert media_id

        _assert_media_published(instagram_credentials, media_id, caption, media=['IMAGE'])
        _finish_media(instagram_credentials, caption, media_id, result.post_url)


# ── Video post tests ──────────────────────────────────────────────────────────


@pytest.mark.functional
@pytest.mark.mutating
class TestInstagramVideoPost:
    """Video feed posts via the Instagram Graph API + S3 staging."""

    def test_video_post(self, instagram_credentials, meta_aws_credentials, sample_video):
        """Stage an MP4 to S3, post it as a Reel, verify success, then delete."""
        from src.platforms.meta_instagram import MetaInstagramPlatform

        caption = mutating_post_text()

        platform = MetaInstagramPlatform(_make_auth(instagram_credentials, meta_aws_credentials))
        result = platform.post(caption, media_paths=[sample_video])

        assert result.success, f'Video post failed: {result.error_code} — {result.error_message}'
        assert result.platform == 'Instagram'
        media_id = result.raw_response.get('id')
        assert media_id

        _assert_media_published(instagram_credentials, media_id, caption, media=['VIDEO'])
        _finish_media(instagram_credentials, caption, media_id, result.post_url)


# ── Carousel post tests ───────────────────────────────────────────────────────


@pytest.mark.functional
@pytest.mark.mutating
class TestInstagramCarouselPost:
    """Multi-image carousel posts via the Instagram Graph API + S3 staging."""

    def test_carousel_two_images(
        self, instagram_credentials, meta_aws_credentials, sample_jpeg, sample_png
    ):
        """Post a 2-image carousel, verify the carousel container is published."""
        from src.platforms.meta_instagram import MetaInstagramPlatform

        caption = mutating_post_text()

        platform = MetaInstagramPlatform(_make_auth(instagram_credentials, meta_aws_credentials))
        result = platform.post(caption, media_paths=[sample_jpeg, sample_png])

        assert result.success, f'Carousel post failed: {result.error_code} — {result.error_message}'
        assert result.platform == 'Instagram'
        media_id = result.raw_response.get('id')
        assert media_id

        _assert_media_published(instagram_credentials, media_id, caption, media=['IMAGE', 'IMAGE'])
        _finish_media(instagram_credentials, caption, media_id, result.post_url)

    def test_carousel_image_and_video(
        self,
        instagram_credentials,
        meta_aws_credentials,
        sample_jpeg,
        sample_video,
    ):
        """Post a mixed image+video carousel, verify publish, then delete."""
        from src.platforms.meta_instagram import MetaInstagramPlatform

        caption = mutating_post_text()

        platform = MetaInstagramPlatform(_make_auth(instagram_credentials, meta_aws_credentials))
        result = platform.post(caption, media_paths=[sample_jpeg, sample_video])

        assert result.success, (
            f'Mixed carousel post failed: {result.error_code} — {result.error_message}'
        )
        assert result.platform == 'Instagram'
        media_id = result.raw_response.get('id')
        assert media_id

        _assert_media_published(instagram_credentials, media_id, caption, media=['IMAGE', 'VIDEO'])
        _finish_media(instagram_credentials, caption, media_id, result.post_url)
