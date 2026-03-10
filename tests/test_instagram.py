"""Tests for Instagram platform with mocked Graph API."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

import src.platforms.instagram as instagram_module
from src.platforms.instagram import InstagramPlatform


class _FakeAuth:
    def get_account_credentials(self, account_id):
        return {
            'access_token': 'fake_token',
            'ig_user_id': '17841400000',
            'page_id': '100000000000',
        }


class _EmptyAuth:
    def get_account_credentials(self, account_id):
        return None


def _make_platform(auth=None, **kwargs):
    return InstagramPlatform(auth or _FakeAuth(), **kwargs)


def test_instagram_get_platform_name():
    p = _make_platform(profile_name='rinthemodel')
    assert p.get_platform_name() == 'Instagram (rinthemodel)'


def test_instagram_get_platform_name_no_profile():
    p = _make_platform()
    assert p.get_platform_name() == 'Instagram'


def test_instagram_get_specs():
    p = _make_platform()
    specs = p.get_specs()
    assert specs.platform_name == 'Instagram'
    assert specs.api_type == 'graph_api'
    assert specs.max_accounts == 2


def test_instagram_test_connection_delegates_to_authenticate(monkeypatch):
    p = _make_platform()
    monkeypatch.setattr(p, 'authenticate', lambda: (True, None))
    assert p.test_connection() == (True, None)


def test_instagram_authenticate_missing_creds():
    p = _make_platform(auth=_EmptyAuth())
    success, error = p.authenticate()
    assert success is False
    assert error == 'AUTH-MISSING'


@patch('src.platforms.instagram.requests')
def test_instagram_authenticate_success(mock_requests):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {'username': 'rinthemodel'}
    mock_requests.get.return_value = mock_resp

    p = _make_platform()
    success, error = p.authenticate()
    assert success is True
    assert error is None


@patch('src.platforms.instagram.requests')
def test_instagram_authenticate_expired(mock_requests):
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_requests.get.return_value = mock_resp

    p = _make_platform()
    success, error = p.authenticate()
    assert success is False
    assert error == 'IG-AUTH-EXPIRED'


def test_instagram_post_no_image():
    p = _make_platform()
    result = p.post('Hello world')
    assert result.success is False
    assert result.error_code == 'POST-FAILED'


def test_instagram_post_multiple_media_uses_first_path(monkeypatch, tmp_path):
    first = tmp_path / 'first.jpg'
    second = tmp_path / 'second.jpg'
    first.write_bytes(b'\xff\xd8\xff\xe0')
    second.write_bytes(b'\xff\xd8\xff\xe0')

    p = _make_platform()
    called = {}

    def fake_upload(image_path):
        called['image_path'] = image_path
        return 'https://scontent.example.com/photo.jpg'

    monkeypatch.setattr(p, '_upload_image', fake_upload)
    monkeypatch.setattr(p, '_create_media_container', lambda _url, _caption: 'container456')
    monkeypatch.setattr(p, '_publish_container', lambda _container_id: 'media789')
    monkeypatch.setattr(
        p, '_get_permalink', lambda _media_id: 'https://www.instagram.com/p/ABC123/'
    )

    result = p.post('Hello', media_paths=[first, second])

    assert result.success is True
    assert called['image_path'] == first


@patch('src.platforms.instagram.requests')
def test_instagram_post_success(mock_requests, tmp_path):
    # Mock the upload photo call
    upload_resp = MagicMock()
    upload_resp.status_code = 200
    upload_resp.json.return_value = {'id': 'photo123'}

    # Mock the get image URL call
    url_resp = MagicMock()
    url_resp.status_code = 200
    url_resp.json.return_value = {'images': [{'source': 'https://scontent.example.com/photo.jpg'}]}

    # Mock the create container call
    container_resp = MagicMock()
    container_resp.status_code = 200
    container_resp.json.return_value = {'id': 'container456'}
    container_resp.raise_for_status = MagicMock()

    # Mock the publish call
    publish_resp = MagicMock()
    publish_resp.status_code = 200
    publish_resp.json.return_value = {'id': 'media789'}
    publish_resp.raise_for_status = MagicMock()

    # Mock the permalink call
    permalink_resp = MagicMock()
    permalink_resp.status_code = 200
    permalink_resp.json.return_value = {'permalink': 'https://www.instagram.com/p/ABC123/'}

    # Set up the mock to return different responses for each call
    mock_requests.post.side_effect = [upload_resp, container_resp, publish_resp]
    mock_requests.get.side_effect = [url_resp, permalink_resp]

    image = tmp_path / 'test.jpg'
    image.write_bytes(b'\xff\xd8\xff\xe0')

    p = _make_platform()
    result = p.post('Hello Instagram!', media_paths=[image])

    assert result.success is True
    assert result.post_url == 'https://www.instagram.com/p/ABC123/'
    assert result.account_id == 'instagram_1'
    assert result.url_captured is True


@patch('src.platforms.instagram.requests')
def test_instagram_post_rate_limited(mock_requests, tmp_path):
    # Upload succeeds
    upload_resp = MagicMock()
    upload_resp.status_code = 200
    upload_resp.json.return_value = {'id': 'photo123'}

    url_resp = MagicMock()
    url_resp.status_code = 200
    url_resp.json.return_value = {'images': [{'source': 'https://scontent.example.com/photo.jpg'}]}

    # Container creation rate limited
    container_resp = MagicMock()
    container_resp.status_code = 429

    mock_requests.post.side_effect = [upload_resp, container_resp]
    mock_requests.get.return_value = url_resp

    image = tmp_path / 'test.jpg'
    image.write_bytes(b'\xff\xd8\xff\xe0')

    p = _make_platform()
    result = p.post('Hello', media_paths=[image])

    assert result.success is False
    assert result.error_code == 'IG-RATE-LIMIT'


@patch('src.platforms.instagram.requests')
def test_instagram_authenticate_invalid_status(mock_requests):
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_requests.get.return_value = mock_resp

    p = _make_platform()
    success, error = p.authenticate()
    assert success is False
    assert error == 'IG-AUTH-INVALID'


def test_instagram_authenticate_timeout(monkeypatch):
    monkeypatch.setattr(
        instagram_module.requests,
        'get',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(requests.Timeout()),
    )

    p = _make_platform()
    success, error = p.authenticate()
    assert success is False
    assert error == 'NET-TIMEOUT'


def test_instagram_authenticate_connection_error(monkeypatch):
    monkeypatch.setattr(
        instagram_module.requests,
        'get',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(requests.ConnectionError()),
    )

    p = _make_platform()
    success, error = p.authenticate()
    assert success is False
    assert error == 'NET-CONNECTION'


def test_instagram_authenticate_unexpected_exception(monkeypatch):
    monkeypatch.setattr(
        instagram_module.requests,
        'get',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError('boom')),
    )

    p = _make_platform()
    success, error = p.authenticate()
    assert success is False
    assert error == 'IG-AUTH-INVALID'


def test_instagram_post_missing_credentials_returns_auth_missing(tmp_path):
    image = tmp_path / 'test.jpg'
    image.write_bytes(b'\xff\xd8\xff\xe0')

    p = _make_platform(auth=_EmptyAuth())
    result = p.post('Hello', media_paths=[image])
    assert result.success is False
    assert result.error_code == 'AUTH-MISSING'


def test_instagram_post_upload_error_returns_error_code(monkeypatch, tmp_path):
    image = tmp_path / 'test.jpg'
    image.write_bytes(b'\xff\xd8\xff\xe0')

    p = _make_platform()
    monkeypatch.setattr(
        p,
        '_upload_image',
        lambda _image: (_ for _ in ()).throw(
            instagram_module._UploadError('IMG-UPLOAD-FAILED', 'no page')
        ),
    )

    result = p.post('Hello', media_paths=[image])
    assert result.success is False
    assert result.error_code == 'IMG-UPLOAD-FAILED'


def test_instagram_post_auth_error_returns_error_code(monkeypatch, tmp_path):
    image = tmp_path / 'test.jpg'
    image.write_bytes(b'\xff\xd8\xff\xe0')

    p = _make_platform()
    monkeypatch.setattr(p, '_upload_image', lambda _image: 'https://img.example/test.jpg')
    monkeypatch.setattr(
        p,
        '_create_media_container',
        lambda *_args: (_ for _ in ()).throw(instagram_module._AuthError('IG-AUTH-EXPIRED')),
    )

    result = p.post('Hello', media_paths=[image])
    assert result.success is False
    assert result.error_code == 'IG-AUTH-EXPIRED'


def test_instagram_post_unexpected_exception_returns_post_failed(monkeypatch, tmp_path):
    image = tmp_path / 'test.jpg'
    image.write_bytes(b'\xff\xd8\xff\xe0')

    p = _make_platform()
    monkeypatch.setattr(p, '_upload_image', lambda _image: 'https://img.example/test.jpg')
    monkeypatch.setattr(p, '_create_media_container', lambda *_args: 'container-id')
    monkeypatch.setattr(
        p,
        '_publish_container',
        lambda *_args: (_ for _ in ()).throw(RuntimeError('publish failed')),
    )

    result = p.post('Hello', media_paths=[image])
    assert result.success is False
    assert result.error_code == 'POST-FAILED'


@patch('src.platforms.instagram.requests')
def test_instagram_upload_image_status_paths(mock_requests, tmp_path):
    class NoPageAuth:
        def get_account_credentials(self, _account_id):
            return {'access_token': 'fake_token', 'ig_user_id': '17841400000'}

    image = tmp_path / 'test.jpg'
    image.write_bytes(b'\xff\xd8\xff\xe0')
    p = _make_platform(auth=NoPageAuth())

    with pytest.raises(instagram_module._UploadError):
        p._upload_image(image)

    p = _make_platform()
    upload_rate_limited = MagicMock(status_code=429, text='slow down')
    mock_requests.post.return_value = upload_rate_limited
    with pytest.raises(instagram_module._RateLimitError):
        p._upload_image(image)

    upload_auth_error = MagicMock(status_code=401, text='expired')
    mock_requests.post.return_value = upload_auth_error
    with pytest.raises(instagram_module._AuthError):
        p._upload_image(image)

    upload_other_error = MagicMock(status_code=500, text='error')
    mock_requests.post.return_value = upload_other_error
    with pytest.raises(instagram_module._UploadError):
        p._upload_image(image)

    upload_ok = MagicMock(status_code=200)
    upload_ok.json.return_value = {'id': 'photo123'}
    url_missing_images = MagicMock(status_code=200)
    url_missing_images.json.return_value = {'images': []}
    mock_requests.post.return_value = upload_ok
    mock_requests.get.return_value = url_missing_images
    with pytest.raises(instagram_module._UploadError):
        p._upload_image(image)


@patch('src.platforms.instagram.requests')
def test_instagram_create_and_publish_container_error_paths(mock_requests):
    p = _make_platform()
    p._access_token = 'token'
    p._ig_user_id = 'igid'

    mock_requests.post.return_value = MagicMock(status_code=429)
    with pytest.raises(instagram_module._RateLimitError):
        p._create_media_container('https://img.example/test.jpg', 'caption')

    mock_requests.post.return_value = MagicMock(status_code=401)
    with pytest.raises(instagram_module._AuthError):
        p._create_media_container('https://img.example/test.jpg', 'caption')

    mock_requests.post.return_value = MagicMock(status_code=403)
    with pytest.raises(instagram_module._AuthError):
        p._publish_container('container-id')

    mock_requests.post.return_value = MagicMock(status_code=429)
    with pytest.raises(instagram_module._RateLimitError):
        p._publish_container('container-id')


@patch('src.platforms.instagram.requests')
def test_instagram_get_permalink_handles_failures(mock_requests):
    p = _make_platform()
    p._access_token = 'token'

    mock_requests.get.return_value = MagicMock(status_code=500)
    assert p._get_permalink('media-id') is None

    mock_requests.get.side_effect = RuntimeError('broken')
    assert p._get_permalink('media-id') is None
