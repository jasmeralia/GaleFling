"""Tests for Instagram platform with mocked Graph API."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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
    result = p.post('Hello Instagram!', image_path=image)

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
    result = p.post('Hello', image_path=image)

    assert result.success is False
    assert result.error_code == 'IG-RATE-LIMIT'
