"""Tests for MetaInstagramPlatform with mocked Graph API and S3 staging."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import requests

import src.platforms.meta_instagram as ig_module
from src.platforms.meta_instagram import MetaInstagramPlatform
from src.utils.constants import META_INSTAGRAM_API_SPECS

# ── Fake auth helpers ─────────────────────────────────────────────────────────


class _FakeAuth:
    def get_account_credentials(self, account_id):
        return {
            'access_token': 'fake_access_token',
            'user_id': '17841400000',
            'provider': 'meta_instagram',
        }

    def get_aws_media_staging_credentials(self):
        return None


class _EmptyAuth:
    def get_account_credentials(self, account_id):
        return None

    def get_aws_media_staging_credentials(self):
        return None


class _FakeAuthWithExternalId:
    """Simulates OAuth-saved credentials that use external_account_id instead of user_id."""

    def get_account_credentials(self, account_id):
        return {
            'access_token': 'fake_access_token',
            'external_account_id': '17841400000',
            'provider': 'meta_instagram',
        }

    def get_aws_media_staging_credentials(self):
        return None


class _FakeAuthWithAWS(_FakeAuth):
    def get_aws_media_staging_credentials(self):
        return {
            'access_key_id': 'AKID',
            'secret_access_key': 'SECRET',
            'region': 'us-west-2',
            'media_staging_bucket': 'galefling-staging',
        }


def _make_platform(auth=None, **kwargs):
    return MetaInstagramPlatform(auth or _FakeAuth(), **kwargs)


def _ok_resp(**json_data):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


# ── Identity and specs ────────────────────────────────────────────────────────


def test_meta_instagram_get_platform_name():
    p = _make_platform(profile_name='rinthemodel')
    assert p.get_platform_name() == 'Instagram (rinthemodel)'


def test_meta_instagram_get_platform_name_no_profile():
    p = _make_platform()
    assert p.get_platform_name() == 'Instagram'


def test_meta_instagram_get_specs():
    p = _make_platform()
    specs = p.get_specs()
    assert specs is META_INSTAGRAM_API_SPECS
    assert specs.api_type == 'graph_api'
    assert specs.max_accounts == 2


# ── Credential loading ────────────────────────────────────────────────────────


def test_meta_instagram_load_credentials_from_user_id():
    p = _make_platform()
    assert p._load_credentials() is True
    assert p._user_id == '17841400000'


def test_meta_instagram_load_credentials_falls_back_to_external_account_id():
    p = _make_platform(auth=_FakeAuthWithExternalId())
    assert p._load_credentials() is True
    assert p._user_id == '17841400000'


# ── authenticate / test_connection ───────────────────────────────────────────


def test_meta_instagram_authenticate_missing_creds():
    p = _make_platform(auth=_EmptyAuth())
    ok, err = p.authenticate()
    assert ok is False
    assert err == 'AUTH-MISSING'


@patch('src.platforms.meta_instagram.requests')
def test_meta_instagram_authenticate_success(mock_requests):
    mock_requests.get.return_value = _ok_resp(username='rinthemodel')
    p = _make_platform()
    ok, err = p.authenticate()
    assert ok is True
    assert err is None


@patch('src.platforms.meta_instagram.requests')
def test_meta_instagram_authenticate_expired(mock_requests):
    mock_requests.get.return_value = MagicMock(status_code=401)
    p = _make_platform()
    ok, err = p.authenticate()
    assert ok is False
    assert err == 'IG-AUTH-EXPIRED'


@patch('src.platforms.meta_instagram.requests')
def test_meta_instagram_authenticate_invalid_status(mock_requests):
    mock_requests.get.return_value = MagicMock(status_code=500)
    p = _make_platform()
    ok, err = p.authenticate()
    assert ok is False
    assert err == 'IG-AUTH-INVALID'


def test_meta_instagram_authenticate_timeout(monkeypatch):
    monkeypatch.setattr(
        ig_module.requests,
        'get',
        lambda *_a, **_k: (_ for _ in ()).throw(requests.Timeout()),
    )
    p = _make_platform()
    ok, err = p.authenticate()
    assert ok is False
    assert err == 'NET-TIMEOUT'


def test_meta_instagram_authenticate_connection_error(monkeypatch):
    monkeypatch.setattr(
        ig_module.requests,
        'get',
        lambda *_a, **_k: (_ for _ in ()).throw(requests.ConnectionError()),
    )
    p = _make_platform()
    ok, err = p.authenticate()
    assert ok is False
    assert err == 'NET-CONNECTION'


def test_meta_instagram_authenticate_unexpected_exception(monkeypatch):
    monkeypatch.setattr(
        ig_module.requests,
        'get',
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError('boom')),
    )
    p = _make_platform()
    ok, err = p.authenticate()
    assert ok is False
    assert err == 'IG-AUTH-INVALID'


# ── post() — pre-flight failures ─────────────────────────────────────────────


def test_meta_instagram_post_missing_credentials(tmp_path):
    image = tmp_path / 'img.jpg'
    image.write_bytes(b'\xff\xd8')
    p = _make_platform(auth=_EmptyAuth())
    result = p.post('hi', media_paths=[image])
    assert result.success is False
    assert result.error_code == 'AUTH-MISSING'


def test_meta_instagram_post_no_media():
    p = _make_platform()
    result = p.post('Hello world')
    assert result.success is False
    assert result.error_code == 'POST-FAILED'


def test_meta_instagram_post_text_too_long():
    p = _make_platform()
    long_caption = 'x' * (META_INSTAGRAM_API_SPECS.max_text_length + 1)
    # Need a dummy image to avoid the no-media short-circuit
    result = p.post(long_caption)
    assert result.success is False
    assert result.error_code == 'POST-TEXT-TOO-LONG'


def test_meta_instagram_post_token_expired(tmp_path):
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()

    class _ExpiredAuth(_FakeAuth):
        def get_account_credentials(self, account_id):
            return {
                'access_token': 'tok',
                'user_id': '123',
                'provider': 'meta_instagram',
                'expires_at': past,
            }

    image = tmp_path / 'img.jpg'
    image.write_bytes(b'\xff\xd8')
    p = _make_platform(auth=_ExpiredAuth())
    result = p.post('hi', media_paths=[image])
    assert result.success is False
    assert result.error_code == 'IG-AUTH-EXPIRED'


def test_meta_instagram_post_no_s3_credentials(tmp_path):
    image = tmp_path / 'img.jpg'
    image.write_bytes(b'\xff\xd8')
    p = _make_platform()  # _FakeAuth returns None for AWS creds
    result = p.post('hi', media_paths=[image])
    assert result.success is False
    assert result.error_code == 'IG-POST-FAILED'


# ── post() — success paths ────────────────────────────────────────────────────


@patch('src.platforms.meta_instagram.requests.get')
@patch('src.platforms.meta_instagram.requests.post')
def test_meta_instagram_post_image_success(mock_post, mock_get, tmp_path):
    img = tmp_path / 'photo.jpg'
    img.write_bytes(b'\xff\xd8\xff\xe0' * 10)

    mock_post.side_effect = [
        _ok_resp(id='container456'),   # create media container
        _ok_resp(id='media789'),        # publish container
    ]
    mock_get.side_effect = [
        _ok_resp(status_code='FINISHED'),  # wait_for_container poll
        _ok_resp(permalink='https://www.instagram.com/p/ABC123/'),  # permalink
    ]

    p = _make_platform(auth=_FakeAuthWithAWS())
    with patch.object(p, '_stage_media', return_value='https://s3.example.com/photo.jpg'):
        result = p.post('hello', media_paths=[img])

    assert result.success is True
    assert result.raw_response == {'id': 'media789'}
    assert result.post_url == 'https://www.instagram.com/p/ABC123/'
    assert result.account_id == 'meta_instagram_1'
    assert result.url_captured is True


@patch('src.platforms.meta_instagram.requests.get')
@patch('src.platforms.meta_instagram.requests.post')
def test_meta_instagram_post_video_success(mock_post, mock_get, tmp_path):
    vid = tmp_path / 'clip.mp4'
    vid.write_bytes(b'\x00' * 100)

    mock_post.side_effect = [
        _ok_resp(id='container_vid'),
        _ok_resp(id='post_vid'),
    ]
    mock_get.side_effect = [
        _ok_resp(status_code='FINISHED'),
        _ok_resp(permalink='https://www.instagram.com/p/VID123/'),
    ]

    p = _make_platform(auth=_FakeAuthWithAWS())
    with patch.object(p, '_stage_media', return_value='https://s3.example.com/clip.mp4'):
        result = p.post('video post', media_paths=[vid])

    assert result.success is True
    assert result.raw_response == {'id': 'post_vid'}


@patch('src.platforms.meta_instagram.requests.get')
@patch('src.platforms.meta_instagram.requests.post')
def test_meta_instagram_post_carousel_success(mock_post, mock_get, tmp_path):
    img1 = tmp_path / 'a.jpg'
    img2 = tmp_path / 'b.jpg'
    img1.write_bytes(b'\xff\xd8' * 10)
    img2.write_bytes(b'\xff\xd8' * 10)

    mock_post.side_effect = [
        _ok_resp(id='item1'),      # create item 1 container
        _ok_resp(id='item2'),      # create item 2 container
        _ok_resp(id='carousel'),   # create carousel container
        _ok_resp(id='post_car'),   # publish
    ]
    mock_get.side_effect = [
        _ok_resp(status_code='FINISHED'),  # wait item 1
        _ok_resp(status_code='FINISHED'),  # wait item 2
        _ok_resp(status_code='FINISHED'),  # wait carousel
        _ok_resp(permalink='https://www.instagram.com/p/CAR123/'),
    ]

    p = _make_platform(auth=_FakeAuthWithAWS())
    with patch.object(p, '_stage_media', return_value='https://s3.example.com/img.jpg'):
        result = p.post('carousel', media_paths=[img1, img2])

    assert result.success is True
    assert result.raw_response == {'id': 'post_car'}


# ── post() — error paths ──────────────────────────────────────────────────────


@patch('src.platforms.meta_instagram.requests.get')
@patch('src.platforms.meta_instagram.requests.post')
def test_meta_instagram_post_rate_limited(mock_post, mock_get, tmp_path):
    img = tmp_path / 'photo.jpg'
    img.write_bytes(b'\xff\xd8' * 10)

    mock_post.return_value = MagicMock(status_code=429)

    p = _make_platform(auth=_FakeAuthWithAWS())
    with patch.object(p, '_stage_media', return_value='https://s3.example.com/photo.jpg'):
        result = p.post('hi', media_paths=[img])

    assert result.success is False
    assert result.error_code == 'IG-RATE-LIMIT'


@patch('src.platforms.meta_instagram.requests.get')
@patch('src.platforms.meta_instagram.requests.post')
def test_meta_instagram_post_auth_error(mock_post, mock_get, tmp_path):
    img = tmp_path / 'photo.jpg'
    img.write_bytes(b'\xff\xd8' * 10)

    mock_post.return_value = MagicMock(status_code=401)

    p = _make_platform(auth=_FakeAuthWithAWS())
    with patch.object(p, '_stage_media', return_value='https://s3.example.com/photo.jpg'):
        result = p.post('hi', media_paths=[img])

    assert result.success is False
    assert result.error_code == 'IG-AUTH-EXPIRED'


def test_meta_instagram_post_unexpected_exception(tmp_path):
    img = tmp_path / 'photo.jpg'
    img.write_bytes(b'\xff\xd8' * 10)

    p = _make_platform(auth=_FakeAuthWithAWS())
    with (
        patch.object(p, '_stage_media', return_value='https://s3.example.com/photo.jpg'),
        patch.object(p, '_create_media_container', side_effect=RuntimeError('kaboom')),
    ):
        result = p.post('hi', media_paths=[img])

    assert result.success is False
    assert result.error_code == 'IG-POST-FAILED'


# ── _wait_for_container ───────────────────────────────────────────────────────


@patch('src.platforms.meta_instagram.requests')
def test_wait_for_container_error_status(mock_requests):
    mock_requests.get.return_value = _ok_resp(status_code='ERROR')
    p = _make_platform()
    p._access_token = 'tok'
    with pytest.raises(ig_module._PostError):
        p._wait_for_container('cid')


@patch('src.platforms.meta_instagram.time')
@patch('src.platforms.meta_instagram.requests')
def test_wait_for_container_timeout(mock_requests, mock_time):
    mock_requests.get.return_value = _ok_resp(status_code='IN_PROGRESS')
    # Simulate time advancing past timeout on the second monotonic call
    mock_time.monotonic.side_effect = [0, 200]
    mock_time.sleep = MagicMock()
    p = _make_platform()
    p._access_token = 'tok'
    with pytest.raises(ig_module._PostError, match='did not finish'):
        p._wait_for_container('cid')


# ── API helper error paths ────────────────────────────────────────────────────


@patch('src.platforms.meta_instagram.requests')
def test_create_container_error_paths(mock_requests):
    p = _make_platform()
    p._access_token = 'tok'
    p._user_id = 'uid'

    mock_requests.post.return_value = MagicMock(status_code=429)
    with pytest.raises(ig_module._RateLimitError):
        p._create_media_container(image_url='https://s3.example.com/img.jpg')

    mock_requests.post.return_value = MagicMock(status_code=401)
    with pytest.raises(ig_module._AuthError):
        p._create_media_container(image_url='https://s3.example.com/img.jpg')

    mock_requests.post.return_value = MagicMock(status_code=403)
    with pytest.raises(ig_module._AuthError):
        p._create_media_container(image_url='https://s3.example.com/img.jpg')


@patch('src.platforms.meta_instagram.requests')
def test_publish_container_error_paths(mock_requests):
    p = _make_platform()
    p._access_token = 'tok'
    p._user_id = 'uid'

    mock_requests.post.return_value = MagicMock(status_code=429)
    with pytest.raises(ig_module._RateLimitError):
        p._publish_container('container-id')

    mock_requests.post.return_value = MagicMock(status_code=403)
    with pytest.raises(ig_module._AuthError):
        p._publish_container('container-id')


@patch('src.platforms.meta_instagram.requests')
def test_get_permalink_handles_failures(mock_requests):
    p = _make_platform()
    p._access_token = 'tok'

    mock_requests.get.return_value = MagicMock(status_code=500)
    assert p._get_permalink('media-id') is None

    mock_requests.get.side_effect = RuntimeError('broken')
    assert p._get_permalink('media-id') is None
