"""Functional tests for Facebook Page API posting — live calls using real credentials.

Credentials are read from tests/functional/.env:
    META_FACEBOOK_PAGE_ACCESS_TOKEN — long-lived Page access token
    META_FACEBOOK_PAGE_ID           — Facebook Page ID (numeric string)
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


#: A feed post and an uploaded video are different node types with different fields, and
#: Graph rejects a union of the two — asking a page post for ``description`` fails with
#: "(#12) deprecate_post_aggregated_fields_for_attachement is deprecated". So the field
#: set is chosen per node type, using the same distinction ``_facebook_post_id()`` already
#: encodes: a feed post is ``{page_id}_{post_id}``, a video upload is a bare object ID.
PAGE_POST_FIELDS = 'id,message,permalink_url,attachments{media_type,subattachments{media_type}}'
VIDEO_FIELDS = 'id,description,title,permalink_url'


def _is_page_post(artifact_id: str) -> bool:
    """Return whether the ID names a feed post rather than an uploaded video object."""
    return '_' in artifact_id


def _attachment_kinds(payload: dict) -> list[str]:
    """Return one entry per published attachment, in Graph's own vocabulary.

    A multi-photo post reports a single ``album`` attachment carrying the real per-item
    types on its ``subattachments`` edge, so attachments are counted from the children
    when present — the same shape Threads and Instagram use for carousels.
    """
    kinds: list[str] = []
    for attachment in (payload.get('attachments') or {}).get('data', []):
        subs = (attachment.get('subattachments') or {}).get('data', [])
        if subs:
            kinds.extend(sub.get('media_type') for sub in subs)
        else:
            kinds.append(attachment.get('media_type'))
    return kinds


def _fetch_artifact(creds: dict, artifact_id: str) -> tuple[dict | None, str, list[str]]:
    """Read a published artifact back, returning it, its text, and its media kinds.

    Retried briefly, and deliberately not distinguishing "missing" from "not yet
    readable": Graph answers both with 400 / code 100, so the only safe reading of a
    persistent non-200 is that the artifact is not there.
    """
    is_post = _is_page_post(artifact_id)
    fields = PAGE_POST_FIELDS if is_post else VIDEO_FIELDS
    for attempt in range(5):
        resp = requests.get(
            f'{FB_GRAPH_BASE}/{artifact_id}',
            params={'fields': fields, 'access_token': creds['page_access_token']},
            timeout=15,
        )
        if resp.status_code == 200:
            payload = resp.json()
            if is_post:
                return payload, payload.get('message') or '', _attachment_kinds(payload)
            # A video upload *is* the artifact; it has no attachments edge of its own.
            return payload, payload.get('description') or '', ['video']
        if attempt < 4:
            time.sleep(2)
    return None, '', []


def _assert_post_published(
    creds: dict, artifact_id: str, text: str, *, media: list[str] | None = None
) -> dict:
    """Prove the artifact exists on the Page carrying our tag and media, and return it.

    ``result.success`` and a returned ID are the adapter reporting on itself; only reading
    the object back off Graph settles whether anything was published.
    """
    tag = post_tag(text)
    payload, published_text, media_kinds = _fetch_artifact(creds, artifact_id)

    assert payload is not None, (
        f'Facebook returned id {artifact_id} but Graph will not serve it back — '
        f'nothing was published under tag {tag}'
    )
    assert tag in published_text, (
        f'Facebook artifact {artifact_id} does not carry tag {tag} — this is not the post '
        f'we just created: {published_text!r}'
    )
    assert_neutral_live_text('Facebook Page', published_text)

    expected = sorted(media or [])
    assert sorted(media_kinds) == expected, (
        f'Facebook artifact {artifact_id} (tag {tag}) published media '
        f'{sorted(media_kinds)}, expected {expected}'
    )
    return payload


def _delete_post(page_access_token: str, post_id: str) -> None:
    """Delete a Facebook Page post or uploaded object.

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
        f'{FB_GRAPH_BASE}/{post_id}',
        params={'access_token': page_access_token},
        timeout=15,
    )
    if resp.status_code != 200:
        raise ArtifactDeleteFailedError(f'HTTP {resp.status_code}')


def _finish_post(creds: dict, text: str, post_id: str, url: str | None = None) -> None:
    """Delete the post, or leave it up and report it, per the run's cleanup policy."""
    finish_mutating_artifact(
        'Facebook Page',
        text,
        url=url,
        delete=lambda: _delete_post(creds['page_access_token'], post_id),
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

        _assert_post_published(meta_facebook_credentials, post_id, text)
        _finish_post(meta_facebook_credentials, text, post_id, result.post_url)


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

        _assert_post_published(meta_facebook_credentials, post_id, caption, media=['photo'])
        _finish_post(meta_facebook_credentials, caption, post_id, result.post_url)

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

        _assert_post_published(
            meta_facebook_credentials, post_id, caption, media=['photo', 'photo']
        )
        _finish_post(meta_facebook_credentials, caption, post_id, result.post_url)


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

        # Video uploads return a video object ID; Graph DELETE removes it.
        _assert_post_published(meta_facebook_credentials, post_id, description, media=['video'])
        _finish_post(meta_facebook_credentials, description, post_id, result.post_url)
