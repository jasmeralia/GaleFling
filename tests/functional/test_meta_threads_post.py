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

import time

import pytest
import requests

from tests.functional.conftest import MUTATING_TEST_EMOJI, mutating_post_text
from tests.functional.functional_cleanup import (
    ArtifactDeleteFailedError,
    assert_neutral_live_text,
    finish_mutating_artifact,
    post_tag,
)

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


#: Enough to prove the post exists, carries our text, and published the media we sent.
THREADS_MEDIA_FIELDS = 'id,media_type,text,permalink,children{id,media_type}'


def _fetch_post(creds: dict, post_id: str) -> tuple[dict | None, list[str]]:
    """Read a published Threads post back, returning the media object and its media kinds.

    Retried briefly, and deliberately not distinguishing "missing" from "not yet
    readable": Graph answers both with 400 / code 100, so the only safe reading of a
    persistent non-200 is that the post is not there.
    """
    for attempt in range(5):
        resp = requests.get(
            f'{THREADS_API_BASE}/{post_id}',
            params={'fields': THREADS_MEDIA_FIELDS, 'access_token': creds['access_token']},
            timeout=15,
        )
        if resp.status_code == 200:
            payload = resp.json()
            return payload, _published_media_kinds(payload)
        if attempt < 4:
            time.sleep(2)
    return None, []


def _published_media_kinds(media_object: dict) -> list[str]:
    """Return one entry per published media item, in the Threads API's own vocabulary.

    A carousel reports ``CAROUSEL_ALBUM`` at the top level and carries the real per-item
    types on its ``children`` edge, so counting attachments means reading the children
    rather than the parent's own ``media_type``.
    """
    media_type = media_object.get('media_type')
    if media_type == 'TEXT_POST':
        return []
    if media_type == 'CAROUSEL_ALBUM':
        children = (media_object.get('children') or {}).get('data') or []
        return [child.get('media_type') for child in children]
    return [media_type]


def _assert_post_published(
    creds: dict, post_id: str, text: str, *, media: list[str] | None = None
) -> dict:
    """Prove the post exists on Threads carrying our tag and media, and return it.

    ``result.success`` and a returned media ID are the adapter reporting on itself; only
    reading the object back off Graph settles whether anything was published.
    """
    tag = post_tag(text)
    payload, media_kinds = _fetch_post(creds, post_id)

    assert payload is not None, (
        f'Threads returned media id {post_id} but Graph will not serve it back — '
        f'nothing was published under tag {tag}'
    )
    assert tag in (payload.get('text') or ''), (
        f'Threads post {post_id} does not carry tag {tag} — this is not the post we just '
        f'created: {(payload.get("text") or "")!r}'
    )
    assert MUTATING_TEST_EMOJI in (payload.get('text') or ''), (
        f'Threads did not preserve the emoji in the published text: {(payload.get("text") or "")!r}'
    )

    assert_neutral_live_text('Threads', payload.get('text') or '')

    expected = sorted(media or [])
    assert sorted(media_kinds) == expected, (
        f'Threads post {post_id} (tag {tag}) published media {sorted(media_kinds)}, '
        f'expected {expected}'
    )
    return payload


def _delete_post(access_token: str, post_id: str) -> None:
    """Delete a published Threads post.

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
        f'{THREADS_API_BASE}/{post_id}',
        params={'access_token': access_token},
        timeout=15,
    )
    if resp.status_code != 200:
        raise ArtifactDeleteFailedError(f'HTTP {resp.status_code}')


def _finish_post(creds: dict, text: str, post_id: str, url: str | None = None) -> None:
    """Delete the post, or leave it up and report it, per the run's cleanup policy."""
    finish_mutating_artifact(
        'Threads',
        text,
        url=url,
        delete=lambda: _delete_post(creds['access_token'], post_id),
    )


# ── Connection tests ──────────────────────────────────────────────────────────


@pytest.mark.functional
@pytest.mark.non_mutating
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

    def test_connection_returns_username(self, meta_threads_credentials):
        """Profile fetch: Threads API must return a username for the token."""
        resp = requests.get(
            f'{THREADS_API_BASE}/me',
            params={
                'fields': 'username',
                'access_token': meta_threads_credentials['access_token'],
            },
            timeout=15,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json().get('username')

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


# ── Validation tests ──────────────────────────────────────────────────────────


@pytest.mark.functional
@pytest.mark.non_mutating
class TestMetaThreadsValidation:
    """Pre-post validation — errors returned before any network I/O."""

    def test_text_too_long_rejected(self, meta_threads_credentials):
        """A post exceeding 500 characters should be rejected before API call."""
        from src.platforms.meta_threads import MetaThreadsPlatform

        text = 'A' * 501
        platform = MetaThreadsPlatform(_make_auth(meta_threads_credentials))
        result = platform.post(text)

        assert not result.success
        assert result.error_code == 'POST-TEXT-TOO-LONG'

    def test_webp_image_rejected(self, meta_threads_credentials, sample_webp):
        """WEBP is not in Threads specs; reject before any API or S3 staging."""
        from src.platforms.meta_threads import MetaThreadsPlatform

        platform = MetaThreadsPlatform(_make_auth(meta_threads_credentials))
        result = platform.post('caption', media_paths=[sample_webp])

        assert not result.success
        assert result.error_code == 'IMG-INVALID-FORMAT'


# ── Text post tests ───────────────────────────────────────────────────────────


@pytest.mark.functional
@pytest.mark.mutating
class TestMetaThreadsTextPost:
    def test_text_post(self, meta_threads_credentials):
        """Post a text-only thread and verify success."""
        from src.platforms.meta_threads import MetaThreadsPlatform

        text = mutating_post_text(MUTATING_TEST_EMOJI)

        platform = MetaThreadsPlatform(_make_auth(meta_threads_credentials))
        result = platform.post(text)

        assert result.success, f'Text post failed: {result.error_code} — {result.error_message}'
        assert result.platform == 'Threads'
        post_id = result.raw_response.get('id')
        assert post_id

        _assert_post_published(meta_threads_credentials, post_id, text)
        _finish_post(meta_threads_credentials, text, post_id, result.post_url)


# ── Image post tests ──────────────────────────────────────────────────────────


@pytest.mark.functional
@pytest.mark.mutating
class TestMetaThreadsImagePost:
    """Single-image Threads posts via the Threads API + S3 staging."""

    def test_single_image_post(self, meta_threads_credentials, meta_aws_credentials, sample_jpeg):
        """Stage a JPEG to S3, post it to Threads, verify permalink, then delete."""
        from src.platforms.meta_threads import MetaThreadsPlatform

        caption = mutating_post_text(MUTATING_TEST_EMOJI)

        platform = MetaThreadsPlatform(_make_auth(meta_threads_credentials, meta_aws_credentials))
        result = platform.post(caption, media_paths=[sample_jpeg])

        assert result.success, f'Image post failed: {result.error_code} — {result.error_message}'
        assert result.platform == 'Threads'
        post_id = result.raw_response.get('id')
        assert post_id

        # Unconditional: a guarded URL assertion cannot fail when post_url is None,
        # which is precisely the regression worth catching — the Results dialog then
        # has no link to offer the user. Facebook Page video posts shipped in exactly
        # that state, and no test caught it; the artifact reporter did, by printing
        # 'URL: none reported'.
        assert result.post_url, 'no post_url returned — Results would have no link'
        assert 'threads.' in result.post_url and '/post/' in result.post_url

        _assert_post_published(meta_threads_credentials, post_id, caption, media=['IMAGE'])
        _finish_post(meta_threads_credentials, caption, post_id, result.post_url)

    def test_png_image_post(self, meta_threads_credentials, meta_aws_credentials, sample_png):
        """PNG images must also be accepted by the Threads API."""
        from src.platforms.meta_threads import MetaThreadsPlatform

        caption = mutating_post_text(MUTATING_TEST_EMOJI)

        platform = MetaThreadsPlatform(_make_auth(meta_threads_credentials, meta_aws_credentials))
        result = platform.post(caption, media_paths=[sample_png])

        assert result.success, f'PNG post failed: {result.error_code} — {result.error_message}'
        post_id = result.raw_response.get('id')
        assert post_id

        _assert_post_published(meta_threads_credentials, post_id, caption, media=['IMAGE'])
        _finish_post(meta_threads_credentials, caption, post_id, result.post_url)


# ── Video post tests ──────────────────────────────────────────────────────────


@pytest.mark.functional
@pytest.mark.mutating
class TestMetaThreadsVideoPost:
    """Video Threads posts via the Threads API + S3 staging."""

    def test_video_post(self, meta_threads_credentials, meta_aws_credentials, sample_video):
        """Stage an MP4 to S3, post it to Threads, verify success, then delete."""
        from src.platforms.meta_threads import MetaThreadsPlatform

        caption = mutating_post_text(MUTATING_TEST_EMOJI)

        platform = MetaThreadsPlatform(_make_auth(meta_threads_credentials, meta_aws_credentials))
        result = platform.post(caption, media_paths=[sample_video])

        assert result.success, f'Video post failed: {result.error_code} — {result.error_message}'
        assert result.platform == 'Threads'
        post_id = result.raw_response.get('id')
        assert post_id

        _assert_post_published(meta_threads_credentials, post_id, caption, media=['VIDEO'])
        _finish_post(meta_threads_credentials, caption, post_id, result.post_url)


# ── Carousel post tests ───────────────────────────────────────────────────────


@pytest.mark.functional
@pytest.mark.mutating
class TestMetaThreadsCarouselPost:
    """Multi-item carousel Threads posts via the Threads API + S3 staging."""

    def test_carousel_two_images(
        self, meta_threads_credentials, meta_aws_credentials, sample_jpeg, sample_png
    ):
        """Post a 2-image carousel, verify the carousel is published, then delete."""
        from src.platforms.meta_threads import MetaThreadsPlatform

        caption = mutating_post_text(MUTATING_TEST_EMOJI)

        platform = MetaThreadsPlatform(_make_auth(meta_threads_credentials, meta_aws_credentials))
        result = platform.post(caption, media_paths=[sample_jpeg, sample_png])

        assert result.success, f'Carousel post failed: {result.error_code} — {result.error_message}'
        assert result.platform == 'Threads'
        post_id = result.raw_response.get('id')
        assert post_id

        _assert_post_published(meta_threads_credentials, post_id, caption, media=['IMAGE', 'IMAGE'])
        _finish_post(meta_threads_credentials, caption, post_id, result.post_url)

    def test_carousel_image_and_video(
        self,
        meta_threads_credentials,
        meta_aws_credentials,
        sample_jpeg,
        sample_video,
    ):
        """Post a mixed image+video carousel, verify publish, then delete."""
        from src.platforms.meta_threads import MetaThreadsPlatform

        caption = mutating_post_text(MUTATING_TEST_EMOJI)

        platform = MetaThreadsPlatform(_make_auth(meta_threads_credentials, meta_aws_credentials))
        result = platform.post(caption, media_paths=[sample_jpeg, sample_video])

        assert result.success, (
            f'Mixed carousel post failed: {result.error_code} — {result.error_message}'
        )
        assert result.platform == 'Threads'
        post_id = result.raw_response.get('id')
        assert post_id

        _assert_post_published(meta_threads_credentials, post_id, caption, media=['IMAGE', 'VIDEO'])
        _finish_post(meta_threads_credentials, caption, post_id, result.post_url)
