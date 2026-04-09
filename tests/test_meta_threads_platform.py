"""Unit tests for MetaThreadsPlatform."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import requests

import src.platforms.meta_threads as threads_module
from src.platforms.meta_threads import MetaThreadsPlatform
from src.utils.constants import META_THREADS_API_SPECS

# ── Fake auth helpers ─────────────────────────────────────────────────────────


class _FakeAuth:
    def get_account_credentials(self, account_id):
        return {
            'access_token': 'fake_access_token',
            'user_id': '99887766',
            'provider': 'meta_threads',
        }

    def get_aws_media_staging_credentials(self):
        return None


class _AuthWithExpiry:
    def __init__(self, expires_at: str):
        self._expires_at = expires_at

    def get_account_credentials(self, account_id):
        return {
            'access_token': 'fake_token',
            'user_id': '99887766',
            'expires_at': self._expires_at,
        }

    def get_aws_media_staging_credentials(self):
        return None


class _EmptyAuth:
    def get_account_credentials(self, account_id):
        return None

    def get_aws_media_staging_credentials(self):
        return None


def _make_platform(auth=None, **kwargs):
    return MetaThreadsPlatform(auth or _FakeAuth(), **kwargs)


def _ok_resp(**json_data):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


def _error_resp(status_code: int):
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    return resp


# ── get_platform_name / get_specs ─────────────────────────────────────────────


def test_get_platform_name_default():
    p = _make_platform()
    assert p.get_platform_name() == 'Threads'


def test_get_platform_name_with_profile():
    p = _make_platform(profile_name='rinthemodel')
    assert p.get_platform_name() == 'Threads (rinthemodel)'


def test_get_specs_returns_meta_threads_api_specs():
    p = _make_platform()
    assert p.get_specs() is META_THREADS_API_SPECS


# ── authenticate ─────────────────────────────────────────────────────────────


def test_authenticate_missing_creds():
    p = _make_platform(auth=_EmptyAuth())
    ok, err = p.authenticate()
    assert not ok
    assert err == 'AUTH-MISSING'


@patch('src.platforms.meta_threads.requests.get')
def test_authenticate_success(mock_get):
    mock_get.return_value = _ok_resp(id='99887766', username='rin')
    p = _make_platform()
    ok, err = p.authenticate()
    assert ok
    assert err is None


@patch('src.platforms.meta_threads.requests.get')
def test_authenticate_401_returns_auth_expired(mock_get):
    mock_get.return_value = _error_resp(401)
    p = _make_platform()
    ok, err = p.authenticate()
    assert not ok
    assert err == 'TH-AUTH-EXPIRED'


@patch('src.platforms.meta_threads.requests.get')
def test_authenticate_403_returns_auth_expired(mock_get):
    mock_get.return_value = _error_resp(403)
    p = _make_platform()
    ok, err = p.authenticate()
    assert not ok
    assert err == 'TH-AUTH-EXPIRED'


@patch('src.platforms.meta_threads.requests.get')
def test_authenticate_500_returns_auth_invalid(mock_get):
    mock_get.return_value = _error_resp(500)
    p = _make_platform()
    ok, err = p.authenticate()
    assert not ok
    assert err == 'TH-AUTH-INVALID'


def test_authenticate_timeout(monkeypatch):
    monkeypatch.setattr(
        threads_module.requests,
        'get',
        lambda *a, **kw: (_ for _ in ()).throw(requests.Timeout()),
    )
    p = _make_platform()
    ok, err = p.authenticate()
    assert not ok
    assert err == 'NET-TIMEOUT'


def test_authenticate_connection_error(monkeypatch):
    monkeypatch.setattr(
        threads_module.requests,
        'get',
        lambda *a, **kw: (_ for _ in ()).throw(requests.ConnectionError()),
    )
    p = _make_platform()
    ok, err = p.authenticate()
    assert not ok
    assert err == 'NET-CONNECTION'


# ── test_connection ───────────────────────────────────────────────────────────


@patch('src.platforms.meta_threads.requests.get')
def test_test_connection_success(mock_get):
    mock_get.return_value = _ok_resp(id='99887766', username='rin')
    p = _make_platform()
    ok, err = p.test_connection()
    assert ok
    assert err is None


def test_test_connection_missing_creds():
    p = _make_platform(auth=_EmptyAuth())
    ok, err = p.test_connection()
    assert not ok
    assert err == 'AUTH-MISSING'


# ── post() — text-only (no S3 upload) ────────────────────────────────────────


@patch('src.platforms.meta_threads.requests.get')
@patch('src.platforms.meta_threads.requests.post')
def test_post_text_only_success(mock_post, mock_get):
    # _create_container → id = 'container1'
    mock_post.side_effect = [
        _ok_resp(id='container1'),    # create container
        _ok_resp(id='post1'),         # publish
    ]
    mock_get.return_value = _ok_resp(
        data=[{'quota_usage': 5, 'config': {'quota_total': 250}}],
        permalink='https://www.threads.net/@rin/post/post1',
    )
    p = _make_platform()
    result = p.post('Hello Threads!')
    assert result.success
    assert result.platform == 'Threads'
    assert result.raw_response == {'id': 'post1'}


def test_post_auth_missing_returns_error():
    p = _make_platform(auth=_EmptyAuth())
    result = p.post('text')
    assert not result.success
    assert result.error_code == 'AUTH-MISSING'


# ── post() — image path (mocked MediaStager + container/publish) ──────────────


@patch('src.platforms.meta_threads.requests.get')
@patch('src.platforms.meta_threads.requests.post')
def test_post_image_success(mock_post, mock_get, tmp_path):
    img = tmp_path / 'photo.jpg'
    img.write_bytes(b'\xff\xd8\xff\xe0' * 10)

    class _FakeAuthWithAWS(_FakeAuth):
        def get_aws_media_staging_credentials(self):
            return {
                'access_key_id': 'AKID',
                'secret_access_key': 'SECRET',
                'region': 'us-west-2',
                'media_staging_bucket': 'test-bucket',
            }

    mock_post.side_effect = [
        _ok_resp(id='img_container'),  # create container
        _ok_resp(id='img_post'),       # publish
    ]
    mock_get.side_effect = [
        _ok_resp(data=[{'quota_usage': 0, 'config': {'quota_total': 250}}]),  # quota
        _ok_resp(status='FINISHED'),   # wait_for_container
        _ok_resp(permalink='https://www.threads.net/@rin/post/img_post'),  # permalink
    ]

    p = MetaThreadsPlatform(_FakeAuthWithAWS())
    with patch.object(p, '_stage_media', return_value='https://s3.example.com/photo.jpg'):
        result = p.post('image post', media_paths=[img])

    assert result.success
    assert result.raw_response == {'id': 'img_post'}


# ── post() — video path (mocked polling loop) ─────────────────────────────────


@patch('src.platforms.meta_threads.requests.get')
@patch('src.platforms.meta_threads.requests.post')
def test_post_video_success(mock_post, mock_get, tmp_path):
    video = tmp_path / 'clip.mp4'
    video.write_bytes(b'\x00' * 1024)

    mock_post.side_effect = [
        _ok_resp(id='vid_container'),
        _ok_resp(id='vid_post'),
    ]
    mock_get.side_effect = [
        _ok_resp(data=[{'quota_usage': 0, 'config': {'quota_total': 250}}]),
        _ok_resp(status='FINISHED'),
        _ok_resp(permalink='https://www.threads.net/@rin/post/vid_post'),
    ]

    p = _make_platform()
    with patch.object(p, '_stage_media', return_value='https://s3.example.com/clip.mp4'):
        result = p.post('video post', media_paths=[video])

    assert result.success
    assert result.raw_response == {'id': 'vid_post'}


# ── post() — carousel path ────────────────────────────────────────────────────


@patch('src.platforms.meta_threads.requests.get')
@patch('src.platforms.meta_threads.requests.post')
def test_post_carousel_success(mock_post, mock_get, tmp_path):
    img1 = tmp_path / 'a.jpg'
    img2 = tmp_path / 'b.jpg'
    img1.write_bytes(b'\xff\xd8\xff\xe0' * 10)
    img2.write_bytes(b'\xff\xd8\xff\xe0' * 10)

    mock_post.side_effect = [
        _ok_resp(id='item1'),
        _ok_resp(id='item2'),
        _ok_resp(id='carousel_container'),
        _ok_resp(id='carousel_post'),
    ]
    mock_get.side_effect = [
        _ok_resp(data=[{'quota_usage': 0, 'config': {'quota_total': 250}}]),  # quota
        _ok_resp(status='FINISHED'),   # item1 wait
        _ok_resp(status='FINISHED'),   # item2 wait
        _ok_resp(status='FINISHED'),   # carousel wait
        _ok_resp(permalink='https://www.threads.net/@rin/post/carousel_post'),
    ]

    p = _make_platform()
    with patch.object(p, '_stage_media', return_value='https://s3.example.com/img.jpg'):
        result = p.post('carousel post', media_paths=[img1, img2])

    assert result.success
    assert result.raw_response == {'id': 'carousel_post'}


# ── error code mapping ────────────────────────────────────────────────────────


@patch('src.platforms.meta_threads.requests.get')
@patch('src.platforms.meta_threads.requests.post')
def test_post_401_maps_to_auth_expired(mock_post, mock_get):
    mock_get.return_value = _ok_resp(
        data=[{'quota_usage': 0, 'config': {'quota_total': 250}}]
    )
    mock_post.return_value = _error_resp(401)
    p = _make_platform()
    result = p.post('text')
    assert not result.success
    assert result.error_code == 'TH-AUTH-EXPIRED'


@patch('src.platforms.meta_threads.requests.get')
@patch('src.platforms.meta_threads.requests.post')
def test_post_429_maps_to_rate_limit(mock_post, mock_get):
    mock_get.return_value = _ok_resp(
        data=[{'quota_usage': 0, 'config': {'quota_total': 250}}]
    )
    mock_post.return_value = _error_resp(429)
    p = _make_platform()
    result = p.post('text')
    assert not result.success
    assert result.error_code == 'TH-RATE-LIMIT'


@patch('src.platforms.meta_threads.requests.get')
@patch('src.platforms.meta_threads.requests.post')
def test_post_unexpected_exception_maps_to_post_failed(mock_post, mock_get):
    mock_get.return_value = _ok_resp(
        data=[{'quota_usage': 0, 'config': {'quota_total': 250}}]
    )
    mock_post.side_effect = RuntimeError('unexpected')
    p = _make_platform()
    result = p.post('text')
    assert not result.success
    assert result.error_code == 'TH-POST-FAILED'


# ── Phase 10 validation ───────────────────────────────────────────────────────


def test_validate_text_too_long():
    p = _make_platform()
    p._access_token = 'tok'
    p._user_id = 'uid'
    long_text = 'x' * 501
    with patch.object(p, '_is_quota_exhausted', return_value=False):
        code = p._validate_pre_post(long_text, None)
    assert code == 'POST-TEXT-TOO-LONG'


def test_validate_text_exactly_at_limit():
    p = _make_platform()
    p._access_token = 'tok'
    p._user_id = 'uid'
    text_500 = 'x' * 500
    with patch.object(p, '_is_quota_exhausted', return_value=False):
        code = p._validate_pre_post(text_500, None)
    assert code is None


def test_validate_unsupported_image_format(tmp_path):
    p = _make_platform()
    p._access_token = 'tok'
    p._user_id = 'uid'
    webp = tmp_path / 'image.webp'
    webp.write_bytes(b'\x00' * 100)
    with patch.object(p, '_is_quota_exhausted', return_value=False):
        code = p._validate_pre_post('caption', [webp])
    assert code == 'IMG-INVALID-FORMAT'


def test_validate_unsupported_video_format(tmp_path):
    p = _make_platform()
    p._access_token = 'tok'
    p._user_id = 'uid'
    avi = tmp_path / 'video.avi'
    avi.write_bytes(b'\x00' * 100)
    with patch.object(p, '_is_quota_exhausted', return_value=False):
        code = p._validate_pre_post('caption', [avi])
    assert code == 'VID-INVALID-FORMAT'


def test_validate_supported_image_format_passes(tmp_path):
    p = _make_platform()
    p._access_token = 'tok'
    p._user_id = 'uid'
    jpg = tmp_path / 'photo.jpg'
    jpg.write_bytes(b'\xff\xd8\xff\xe0')
    with patch.object(p, '_is_quota_exhausted', return_value=False):
        code = p._validate_pre_post('caption', [jpg])
    assert code is None


def test_validate_supported_video_format_passes(tmp_path):
    p = _make_platform()
    p._access_token = 'tok'
    p._user_id = 'uid'
    mp4 = tmp_path / 'video.mp4'
    mp4.write_bytes(b'\x00' * 100)
    with patch.object(p, '_is_quota_exhausted', return_value=False):
        code = p._validate_pre_post('caption', [mp4])
    assert code is None


def test_validate_token_expired_iso_timestamp():
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    p = _make_platform(auth=_AuthWithExpiry(past))
    p._access_token = 'tok'
    p._user_id = 'uid'
    with patch.object(p, '_is_quota_exhausted', return_value=False):
        code = p._validate_pre_post('text', None)
    assert code == 'TH-AUTH-EXPIRED'


def test_validate_token_not_yet_expired():
    future = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    p = _make_platform(auth=_AuthWithExpiry(future))
    p._access_token = 'tok'
    p._user_id = 'uid'
    with patch.object(p, '_is_quota_exhausted', return_value=False):
        code = p._validate_pre_post('text', None)
    assert code is None


def test_validate_quota_exhausted_returns_rate_limit():
    p = _make_platform()
    p._access_token = 'tok'
    p._user_id = 'uid'
    with patch.object(p, '_is_quota_exhausted', return_value=True):
        code = p._validate_pre_post('text', None)
    assert code == 'TH-RATE-LIMIT'


@patch('src.platforms.meta_threads.requests.get')
def test_is_quota_exhausted_true_when_at_limit(mock_get):
    mock_get.return_value = _ok_resp(
        data=[{'quota_usage': 250, 'config': {'quota_total': 250}}]
    )
    p = _make_platform()
    p._access_token = 'tok'
    p._user_id = 'uid'
    assert p._is_quota_exhausted() is True


@patch('src.platforms.meta_threads.requests.get')
def test_is_quota_exhausted_false_when_headroom_available(mock_get):
    mock_get.return_value = _ok_resp(
        data=[{'quota_usage': 5, 'config': {'quota_total': 250}}]
    )
    p = _make_platform()
    p._access_token = 'tok'
    p._user_id = 'uid'
    assert p._is_quota_exhausted() is False


@patch('src.platforms.meta_threads.requests.get')
def test_is_quota_exhausted_false_on_api_error(mock_get):
    mock_get.side_effect = requests.ConnectionError()
    p = _make_platform()
    p._access_token = 'tok'
    p._user_id = 'uid'
    assert p._is_quota_exhausted() is False
