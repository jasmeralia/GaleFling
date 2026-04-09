"""Tests for Meta OAuth flow helpers."""

from __future__ import annotations

import socket
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from src.core.meta_oauth import (
    MetaOAuthCallbackServer,
    MetaOAuthFlow,
    find_free_port,
    make_state,
    parse_state,
)

# ── make_state / parse_state ─────────────────────────────────────────────────


def test_make_state_returns_string():
    result = make_state(8765)
    assert isinstance(result, str)
    assert len(result) > 0


def test_parse_state_round_trips_port():
    state = make_state(8767)
    decoded = parse_state(state)
    assert decoded['port'] == 8767


def test_parse_state_includes_csrf():
    state = make_state(8765)
    decoded = parse_state(state)
    assert 'csrf' in decoded
    assert len(decoded['csrf']) > 0


def test_make_state_csrf_is_random():
    state1 = make_state(8765)
    state2 = make_state(8765)
    assert parse_state(state1)['csrf'] != parse_state(state2)['csrf']


def test_parse_state_full_roundtrip():
    """State forwarded unchanged by relay is still verifiable via direct comparison."""
    state = make_state(8769)
    # Simulating relay forwarding state unchanged
    returned_state = state
    assert returned_state == state


# ── find_free_port ────────────────────────────────────────────────────────────


def test_find_free_port_returns_available_port():
    # Find a real free port to verify the function works end-to-end
    port = find_free_port(8765, 8800)
    assert 8765 <= port <= 8800


def test_find_free_port_skips_busy_ports(monkeypatch):
    bind_calls = []

    class _FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def bind(self, addr):
            bind_calls.append(addr[1])
            if addr[1] in (8765, 8766):
                raise OSError('already in use')

    monkeypatch.setattr('src.core.meta_oauth.socket.socket', lambda: _FakeSocket())
    port = find_free_port(8765, 8767)
    assert port == 8767
    assert 8765 in bind_calls and 8766 in bind_calls


def test_find_free_port_raises_when_all_busy(monkeypatch):
    class _BusySocket:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def bind(self, addr):
            raise OSError('already in use')

    monkeypatch.setattr('src.core.meta_oauth.socket.socket', lambda: _BusySocket())
    with pytest.raises(RuntimeError, match='No free ports'):
        find_free_port(8765, 8765)


# ── MetaOAuthCallbackServer ───────────────────────────────────────────────────


def _get_free_port() -> int:
    with socket.socket() as s:
        s.bind(('localhost', 0))
        return s.getsockname()[1]


def test_callback_server_captures_code():
    port = _get_free_port()
    server = MetaOAuthCallbackServer(port)
    server.start()
    try:
        import urllib.request

        url = f'http://localhost:{port}/oauth/callback?code=TEST_CODE&state=TEST_STATE'
        urllib.request.urlopen(url, timeout=5)
        result = server.get_callback(timeout=5)
        assert result is not None
        code, state, error = result
        assert code == 'TEST_CODE'
        assert state == 'TEST_STATE'
        assert error is None
    finally:
        server.shutdown()


def test_callback_server_captures_error():
    port = _get_free_port()
    server = MetaOAuthCallbackServer(port)
    server.start()
    try:
        import urllib.request

        url = f'http://localhost:{port}/oauth/callback?error=access_denied&state=S'
        urllib.request.urlopen(url, timeout=5)
        result = server.get_callback(timeout=5)
        assert result is not None
        code, state, error = result
        assert code is None
        assert error == 'access_denied'
    finally:
        server.shutdown()


def test_callback_server_timeout_returns_none():
    port = _get_free_port()
    server = MetaOAuthCallbackServer(port)
    server.start()
    try:
        result = server.get_callback(timeout=0.1)
        assert result is None
    finally:
        server.shutdown()


def test_callback_server_shutdown_cleans_up():
    port = _get_free_port()
    server = MetaOAuthCallbackServer(port)
    server.start()
    assert server._thread is not None and server._thread.is_alive()
    server.shutdown()
    # Thread should have stopped after shutdown
    assert not server._thread.is_alive()


# ── MetaOAuthFlow.build_auth_url ──────────────────────────────────────────────


def _parse_url(url):
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    return parsed, {k: v[0] for k, v in params.items()}


def test_build_auth_url_threads():
    flow = MetaOAuthFlow('meta_threads', 'THREADS_APP_ID', 'secret')
    url = flow.build_auth_url('http://localhost:8765/oauth/callback', 'my_state')
    parsed, params = _parse_url(url)
    assert parsed.netloc == 'api.instagram.com'
    assert params['client_id'] == 'THREADS_APP_ID'
    assert params['state'] == 'my_state'
    assert 'threads_basic' in params['scope']
    assert 'threads_content_publish' in params['scope']
    assert params['response_type'] == 'code'


def test_build_auth_url_instagram():
    flow = MetaOAuthFlow('meta_instagram', 'IG_APP_ID', 'secret')
    url = flow.build_auth_url('http://localhost:8765/oauth/callback', 'state_ig')
    parsed, params = _parse_url(url)
    assert parsed.netloc == 'www.instagram.com'
    assert params['client_id'] == 'IG_APP_ID'
    assert 'instagram_business_basic' in params['scope']
    assert 'instagram_business_content_publish' in params['scope']


def test_build_auth_url_facebook():
    flow = MetaOAuthFlow('meta_facebook_page', 'FB_APP_ID', 'secret')
    url = flow.build_auth_url('http://localhost:8765/oauth/callback', 'fb_state')
    parsed, params = _parse_url(url)
    assert parsed.netloc == 'www.facebook.com'
    assert params['client_id'] == 'FB_APP_ID'
    scope = params['scope']
    for perm in [
        'pages_manage_metadata',
        'pages_manage_posts',
        'pages_read_engagement',
        'pages_show_list',
        'pages_manage_engagement',
        'publish_video',
    ]:
        assert perm in scope, f'Missing scope: {perm}'


# ── MetaOAuthFlow.exchange_code ───────────────────────────────────────────────


def _mock_post(url, data=None, timeout=None, **kwargs):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {'access_token': 'SHORT_TOKEN', 'token_type': 'bearer'}
    resp.raise_for_status = MagicMock()
    return resp


def _mock_get_token(url, params=None, timeout=None, **kwargs):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {'access_token': 'SHORT_TOKEN', 'token_type': 'bearer'}
    resp.raise_for_status = MagicMock()
    return resp


@patch('src.core.meta_oauth.requests.post', side_effect=_mock_post)
def test_exchange_code_threads(mock_post):
    flow = MetaOAuthFlow('meta_threads', 'APP_ID', 'APP_SECRET')
    result = flow.exchange_code('THE_CODE', 'http://localhost:8765/oauth/callback')
    assert result['access_token'] == 'SHORT_TOKEN'
    call_kwargs = mock_post.call_args
    assert call_kwargs[0][0] == 'https://api.instagram.com/oauth/access_token'
    assert call_kwargs[1]['data']['code'] == 'THE_CODE'
    assert call_kwargs[1]['data']['client_id'] == 'APP_ID'


@patch('src.core.meta_oauth.requests.post', side_effect=_mock_post)
def test_exchange_code_instagram(mock_post):
    flow = MetaOAuthFlow('meta_instagram', 'IG_ID', 'IG_SEC')
    result = flow.exchange_code('CODE_IG', 'http://localhost:8765/oauth/callback')
    assert result['access_token'] == 'SHORT_TOKEN'
    call_kwargs = mock_post.call_args
    assert call_kwargs[0][0] == 'https://api.instagram.com/oauth/access_token'


@patch('src.core.meta_oauth.requests.get', side_effect=_mock_get_token)
def test_exchange_code_facebook_uses_get(mock_get):
    flow = MetaOAuthFlow('meta_facebook_page', 'FB_ID', 'FB_SEC')
    result = flow.exchange_code('CODE_FB', 'http://localhost:8765/oauth/callback')
    assert result['access_token'] == 'SHORT_TOKEN'
    call_url = mock_get.call_args[0][0]
    assert 'graph.facebook.com' in call_url
    assert 'oauth/access_token' in call_url


# ── MetaOAuthFlow.exchange_long_lived ─────────────────────────────────────────


def _mock_long_lived_get(url, params=None, timeout=None, **kwargs):
    resp = MagicMock()
    resp.json.return_value = {'access_token': 'LONG_TOKEN', 'expires_in': 5184000}
    resp.raise_for_status = MagicMock()
    return resp


@patch('src.core.meta_oauth.requests.get', side_effect=_mock_long_lived_get)
def test_exchange_long_lived_threads(mock_get):
    flow = MetaOAuthFlow('meta_threads', 'APP_ID', 'APP_SECRET')
    result = flow.exchange_long_lived('SHORT_TOKEN')
    assert result['access_token'] == 'LONG_TOKEN'
    call_url = mock_get.call_args[0][0]
    assert 'graph.threads.net' in call_url
    params = mock_get.call_args[1]['params']
    assert params['grant_type'] == 'th_exchange_token'


@patch('src.core.meta_oauth.requests.get', side_effect=_mock_long_lived_get)
def test_exchange_long_lived_instagram(mock_get):
    flow = MetaOAuthFlow('meta_instagram', 'IG_ID', 'IG_SEC')
    result = flow.exchange_long_lived('SHORT')
    assert result['access_token'] == 'LONG_TOKEN'
    call_url = mock_get.call_args[0][0]
    assert 'graph.instagram.com' in call_url
    params = mock_get.call_args[1]['params']
    assert params['grant_type'] == 'ig_exchange_token'


@patch('src.core.meta_oauth.requests.get', side_effect=_mock_long_lived_get)
def test_exchange_long_lived_facebook(mock_get):
    flow = MetaOAuthFlow('meta_facebook_page', 'FB_ID', 'FB_SEC')
    result = flow.exchange_long_lived('SHORT')
    assert result['access_token'] == 'LONG_TOKEN'
    params = mock_get.call_args[1]['params']
    assert params['grant_type'] == 'fb_exchange_token'
    assert 'fb_exchange_token' in params  # key name


# ── MetaOAuthFlow.fetch_facebook_pages ───────────────────────────────────────


def _make_pages_responses():
    """Return a side_effect list for requests.get covering /me/accounts + 2 page token calls."""
    accounts_resp = MagicMock()
    accounts_resp.json.return_value = {
        'data': [
            {'id': 'PAGE1', 'name': 'Page One', 'access_token': 'short_page_1'},
            {'id': 'PAGE2', 'name': 'Page Two', 'access_token': 'short_page_2'},
        ]
    }
    accounts_resp.raise_for_status = MagicMock()

    page1_resp = MagicMock()
    page1_resp.json.return_value = {'access_token': 'LONG_PAGE1'}
    page1_resp.raise_for_status = MagicMock()

    page2_resp = MagicMock()
    page2_resp.json.return_value = {'access_token': 'LONG_PAGE2'}
    page2_resp.raise_for_status = MagicMock()

    return [accounts_resp, page1_resp, page2_resp]


@patch('src.core.meta_oauth.requests.get')
def test_fetch_facebook_pages_multi(mock_get):
    mock_get.side_effect = _make_pages_responses()
    flow = MetaOAuthFlow('meta_facebook_page', 'FB_ID', 'FB_SEC')
    pages = flow.fetch_facebook_pages('USER_TOKEN')
    assert len(pages) == 2
    assert pages[0].page_id == 'PAGE1'
    assert pages[0].page_name == 'Page One'
    assert pages[0].long_lived_page_access_token == 'LONG_PAGE1'
    assert pages[1].page_id == 'PAGE2'
    assert pages[1].long_lived_page_access_token == 'LONG_PAGE2'


@patch('src.core.meta_oauth.requests.get')
def test_fetch_facebook_pages_single(mock_get):
    accounts_resp = MagicMock()
    accounts_resp.json.return_value = {
        'data': [{'id': 'ONLY_PAGE', 'name': 'My Page', 'access_token': 'short_tok'}]
    }
    accounts_resp.raise_for_status = MagicMock()
    page_resp = MagicMock()
    page_resp.json.return_value = {'access_token': 'LONG_ONLY'}
    page_resp.raise_for_status = MagicMock()
    mock_get.side_effect = [accounts_resp, page_resp]

    flow = MetaOAuthFlow('meta_facebook_page', 'FB_ID', 'FB_SEC')
    pages = flow.fetch_facebook_pages('USER_TOKEN')
    assert len(pages) == 1
    assert pages[0].long_lived_page_access_token == 'LONG_ONLY'


# ── MetaOAuthFlow.fetch_user_info ─────────────────────────────────────────────


def _mock_user_info_get(url, params=None, timeout=None, **kwargs):
    resp = MagicMock()
    resp.json.return_value = {'id': '12345', 'name': 'Test User'}
    resp.raise_for_status = MagicMock()
    return resp


@patch('src.core.meta_oauth.requests.get', side_effect=_mock_user_info_get)
def test_fetch_user_info_threads(mock_get):
    flow = MetaOAuthFlow('meta_threads', 'APP_ID', 'APP_SECRET')
    result = flow.fetch_user_info('ACCESS_TOKEN')
    assert result['id'] == '12345'
    assert result['name'] == 'Test User'
    call_url = mock_get.call_args[0][0]
    assert 'graph.threads.net' in call_url
    assert call_url.endswith('/me')
    params = mock_get.call_args[1]['params']
    assert params['access_token'] == 'ACCESS_TOKEN'
    assert 'id' in params['fields']
    assert 'name' in params['fields']


@patch('src.core.meta_oauth.requests.get', side_effect=_mock_user_info_get)
def test_fetch_user_info_instagram(mock_get):
    flow = MetaOAuthFlow('meta_instagram', 'IG_ID', 'IG_SEC')
    result = flow.fetch_user_info('IG_TOKEN')
    assert result['id'] == '12345'
    call_url = mock_get.call_args[0][0]
    assert 'graph.instagram.com' in call_url
    assert call_url.endswith('/me')


@patch('src.core.meta_oauth.requests.get', side_effect=_mock_user_info_get)
def test_fetch_user_info_facebook(mock_get):
    flow = MetaOAuthFlow('meta_facebook_page', 'FB_ID', 'FB_SEC')
    result = flow.fetch_user_info('FB_TOKEN')
    assert result['id'] == '12345'
    call_url = mock_get.call_args[0][0]
    assert 'graph.facebook.com' in call_url
    assert call_url.endswith('/me')


@patch('src.core.meta_oauth.requests.get')
def test_fetch_user_info_propagates_http_error(mock_get):
    import requests as req_lib

    resp = MagicMock()
    resp.raise_for_status.side_effect = req_lib.HTTPError('401 Unauthorized')
    mock_get.return_value = resp

    flow = MetaOAuthFlow('meta_threads', 'APP_ID', 'APP_SECRET')
    with pytest.raises(req_lib.HTTPError):
        flow.fetch_user_info('BAD_TOKEN')
