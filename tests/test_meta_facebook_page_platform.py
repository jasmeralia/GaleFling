"""Unit tests for MetaFacebookPagePlatform."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import requests

import src.platforms.meta_facebook_page as fb_module
from src.platforms.meta_facebook_page import MetaFacebookPagePlatform
from src.utils.constants import META_FACEBOOK_PAGE_SPECS

# ── Fake auth helpers ─────────────────────────────────────────────────────────


class _FakeAuth:
    def get_account_credentials(self, account_id):
        return {
            'page_access_token': 'fake_page_token',
            'page_id': '111222333',
            'provider': 'meta_facebook_page',
            'page_name': 'Test Page',
        }


class _AuthWithExpiry:
    def __init__(self, expires_at: str):
        self._expires_at = expires_at

    def get_account_credentials(self, account_id):
        return {
            'page_access_token': 'fake_token',
            'page_id': '111222333',
            'expires_at': self._expires_at,
        }


class _EmptyAuth:
    def get_account_credentials(self, account_id):
        return None


def _make_platform(auth=None, **kwargs):
    return MetaFacebookPagePlatform(auth or _FakeAuth(), **kwargs)


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
    assert p.get_platform_name() == 'Facebook Page'


def test_get_platform_name_with_profile():
    p = _make_platform(profile_name='My Fan Page')
    assert p.get_platform_name() == 'Facebook Page (My Fan Page)'


def test_get_specs_returns_facebook_page_specs():
    p = _make_platform()
    assert p.get_specs() is META_FACEBOOK_PAGE_SPECS


# ── authenticate ─────────────────────────────────────────────────────────────


def test_authenticate_missing_creds():
    p = _make_platform(auth=_EmptyAuth())
    ok, err = p.authenticate()
    assert not ok
    assert err == 'AUTH-MISSING'


@patch('src.platforms.meta_facebook_page.requests.get')
def test_authenticate_success(mock_get):
    mock_get.return_value = _ok_resp(id='111222333', name='Test Page')
    p = _make_platform()
    ok, err = p.authenticate()
    assert ok
    assert err is None


@patch('src.platforms.meta_facebook_page.requests.get')
def test_authenticate_401_returns_auth_expired(mock_get):
    mock_get.return_value = _error_resp(401)
    p = _make_platform()
    ok, err = p.authenticate()
    assert not ok
    assert err == 'FB-AUTH-EXPIRED'


@patch('src.platforms.meta_facebook_page.requests.get')
def test_authenticate_403_returns_auth_expired(mock_get):
    mock_get.return_value = _error_resp(403)
    p = _make_platform()
    ok, err = p.authenticate()
    assert not ok
    assert err == 'FB-AUTH-EXPIRED'


@patch('src.platforms.meta_facebook_page.requests.get')
def test_authenticate_500_returns_auth_invalid(mock_get):
    mock_get.return_value = _error_resp(500)
    p = _make_platform()
    ok, err = p.authenticate()
    assert not ok
    assert err == 'FB-AUTH-INVALID'


def test_authenticate_timeout(monkeypatch):
    monkeypatch.setattr(
        fb_module.requests,
        'get',
        lambda *a, **kw: (_ for _ in ()).throw(requests.Timeout()),
    )
    p = _make_platform()
    ok, err = p.authenticate()
    assert not ok
    assert err == 'NET-TIMEOUT'


def test_authenticate_connection_error(monkeypatch):
    monkeypatch.setattr(
        fb_module.requests,
        'get',
        lambda *a, **kw: (_ for _ in ()).throw(requests.ConnectionError()),
    )
    p = _make_platform()
    ok, err = p.authenticate()
    assert not ok
    assert err == 'NET-CONNECTION'


# ── test_connection ───────────────────────────────────────────────────────────


@patch('src.platforms.meta_facebook_page.requests.get')
def test_test_connection_success(mock_get):
    mock_get.return_value = _ok_resp(id='111222333', name='Test Page')
    p = _make_platform()
    ok, err = p.test_connection()
    assert ok
    assert err is None


def test_test_connection_missing_creds():
    p = _make_platform(auth=_EmptyAuth())
    ok, err = p.test_connection()
    assert not ok
    assert err == 'AUTH-MISSING'


# ── post() — text/link path ───────────────────────────────────────────────────


@patch('src.platforms.meta_facebook_page.requests.post')
def test_post_text_success(mock_post):
    mock_post.return_value = _ok_resp(id='111222333_456')
    p = _make_platform()
    result = p.post('Hello Facebook!')
    assert result.success
    assert result.platform == 'Facebook Page'
    assert result.raw_response == {'id': '111222333_456'}


def test_post_auth_missing_returns_error():
    p = _make_platform(auth=_EmptyAuth())
    result = p.post('text')
    assert not result.success
    assert result.error_code == 'AUTH-MISSING'


# ── post() — photo path (mocked HTTP) ────────────────────────────────────────


@patch('src.platforms.meta_facebook_page.requests.post')
def test_post_photo_success(mock_post, tmp_path):
    photo = tmp_path / 'photo.jpg'
    photo.write_bytes(b'\xff\xd8\xff\xe0' * 10)

    mock_post.return_value = _ok_resp(id='photo123', post_id='111222333_789')

    p = _make_platform()
    result = p.post('photo caption', media_paths=[photo])
    assert result.success
    assert result.raw_response.get('post_id') == '111222333_789'


# ── post() — video path ───────────────────────────────────────────────────────


@patch('src.platforms.meta_facebook_page.requests.post')
def test_post_video_success(mock_post, tmp_path):
    video = tmp_path / 'clip.mp4'
    video.write_bytes(b'\x00' * 1024)

    mock_post.return_value = _ok_resp(id='vid123')

    p = _make_platform()
    result = p.post('video description', media_paths=[video])
    assert result.success
    assert result.raw_response == {'id': 'vid123'}


# ── post() — error code mapping ──────────────────────────────────────────────


@patch('src.platforms.meta_facebook_page.requests.post')
def test_post_401_maps_to_auth_expired(mock_post):
    mock_post.return_value = _error_resp(401)
    p = _make_platform()
    result = p.post('text')
    assert not result.success
    assert result.error_code == 'FB-AUTH-EXPIRED'


@patch('src.platforms.meta_facebook_page.requests.post')
def test_post_429_maps_to_rate_limit(mock_post):
    mock_post.return_value = _error_resp(429)
    p = _make_platform()
    result = p.post('text')
    assert not result.success
    assert result.error_code == 'FB-RATE-LIMIT'


@patch('src.platforms.meta_facebook_page.requests.post')
def test_post_unexpected_exception_maps_to_post_failed(mock_post):
    mock_post.side_effect = RuntimeError('unexpected')
    p = _make_platform()
    result = p.post('text')
    assert not result.success
    assert result.error_code == 'FB-POST-FAILED'


# ── Phase 10 validation ───────────────────────────────────────────────────────


def test_validate_text_too_long():
    p = _make_platform()
    p._page_access_token = 'tok'
    p._page_id = 'pid'
    long_text = 'x' * 63207
    code = p._validate_pre_post(long_text, None)
    assert code == 'POST-TEXT-TOO-LONG'


def test_validate_text_at_limit_passes():
    p = _make_platform()
    p._page_access_token = 'tok'
    p._page_id = 'pid'
    text = 'x' * 63206
    code = p._validate_pre_post(text, None)
    assert code is None


def test_validate_unsupported_image_format(tmp_path):
    p = _make_platform()
    p._page_access_token = 'tok'
    p._page_id = 'pid'
    webp = tmp_path / 'image.webp'
    webp.write_bytes(b'\x00' * 100)
    code = p._validate_pre_post('caption', [webp])
    assert code == 'IMG-INVALID-FORMAT'


def test_validate_unsupported_video_format(tmp_path):
    p = _make_platform()
    p._page_access_token = 'tok'
    p._page_id = 'pid'
    avi = tmp_path / 'video.avi'
    avi.write_bytes(b'\x00' * 100)
    code = p._validate_pre_post('caption', [avi])
    assert code == 'VID-INVALID-FORMAT'


def test_validate_supported_jpeg_passes(tmp_path):
    p = _make_platform()
    p._page_access_token = 'tok'
    p._page_id = 'pid'
    jpg = tmp_path / 'photo.jpg'
    jpg.write_bytes(b'\xff\xd8\xff\xe0')
    code = p._validate_pre_post('caption', [jpg])
    assert code is None


def test_validate_supported_png_passes(tmp_path):
    p = _make_platform()
    p._page_access_token = 'tok'
    p._page_id = 'pid'
    png = tmp_path / 'image.png'
    png.write_bytes(b'\x89PNG\r\n')
    code = p._validate_pre_post('caption', [png])
    assert code is None


def test_validate_supported_mp4_passes(tmp_path):
    p = _make_platform()
    p._page_access_token = 'tok'
    p._page_id = 'pid'
    mp4 = tmp_path / 'video.mp4'
    mp4.write_bytes(b'\x00' * 100)
    code = p._validate_pre_post('caption', [mp4])
    assert code is None


def test_validate_token_expired():
    past = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    p = _make_platform(auth=_AuthWithExpiry(past))
    p._page_access_token = 'tok'
    p._page_id = 'pid'
    code = p._validate_pre_post('text', None)
    assert code == 'FB-AUTH-EXPIRED'


def test_validate_token_not_yet_expired():
    future = (datetime.now(UTC) + timedelta(days=60)).isoformat()
    p = _make_platform(auth=_AuthWithExpiry(future))
    p._page_access_token = 'tok'
    p._page_id = 'pid'
    code = p._validate_pre_post('text', None)
    assert code is None


def test_validate_unparseable_expires_at_skipped():
    """Invalid expires_at format should not block the post."""

    class _BadExpiryAuth:
        def get_account_credentials(self, _account_id):
            return {
                'page_access_token': 'tok',
                'page_id': 'pid',
                'expires_at': 'not-a-date',
            }

    p = _make_platform(auth=_BadExpiryAuth())
    p._page_access_token = 'tok'
    p._page_id = 'pid'
    code = p._validate_pre_post('text', None)
    assert code is None
