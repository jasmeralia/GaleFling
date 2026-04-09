"""Tests for TokenManager — Meta token lifecycle management."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.core.token_manager import EXPIRES_SOON_THRESHOLD_DAYS, TokenManager, TokenStatus

# ── Helpers ───────────────────────────────────────────────────────────────────


def _future(days: int) -> str:
    """Return an ISO-8601 UTC timestamp *days* from now."""
    return (datetime.now(tz=UTC) + timedelta(days=days)).isoformat()


def _past(days: int) -> str:
    """Return an ISO-8601 UTC timestamp *days* ago."""
    return (datetime.now(tz=UTC) - timedelta(days=days)).isoformat()


def _make_auth(creds: dict, accounts=None) -> MagicMock:
    """Return a mocked AuthManager with preconfigured get_account_credentials."""
    auth = MagicMock()
    auth.get_account_credentials.return_value = creds
    auth.get_accounts.return_value = accounts or []
    return auth


# ── get_token_status ──────────────────────────────────────────────────────────


def test_status_missing_no_creds():
    auth = _make_auth(None)
    tm = TokenManager(auth)
    assert tm.get_token_status('acct_1') == TokenStatus.MISSING


def test_status_missing_no_token_field():
    auth = _make_auth({'provider': 'meta_threads', 'expires_at': _future(30)})
    tm = TokenManager(auth)
    assert tm.get_token_status('acct_1') == TokenStatus.MISSING


def test_status_valid_with_far_expiry():
    auth = _make_auth(
        {'provider': 'meta_threads', 'access_token': 'tok', 'expires_at': _future(30)}
    )
    tm = TokenManager(auth)
    assert tm.get_token_status('acct_1') == TokenStatus.VALID


def test_status_expires_soon_within_threshold():
    auth = _make_auth(
        {
            'provider': 'meta_threads',
            'access_token': 'tok',
            'expires_at': _future(EXPIRES_SOON_THRESHOLD_DAYS - 1),
        }
    )
    tm = TokenManager(auth)
    assert tm.get_token_status('acct_1') == TokenStatus.EXPIRES_SOON


def test_status_expires_soon_exactly_at_boundary():
    # Exactly at threshold - 1 second should still be EXPIRES_SOON
    auth = _make_auth(
        {
            'provider': 'meta_threads',
            'access_token': 'tok',
            'expires_at': _future(EXPIRES_SOON_THRESHOLD_DAYS - 1),
        }
    )
    tm = TokenManager(auth)
    assert tm.get_token_status('acct_1') == TokenStatus.EXPIRES_SOON


def test_status_expired():
    auth = _make_auth({'provider': 'meta_threads', 'access_token': 'tok', 'expires_at': _past(1)})
    tm = TokenManager(auth)
    assert tm.get_token_status('acct_1') == TokenStatus.EXPIRED


def test_status_valid_no_expires_at():
    """Credentials without expires_at (e.g. Facebook Page token) → VALID."""
    auth = _make_auth({'provider': 'meta_facebook_page', 'page_access_token': 'tok'})
    tm = TokenManager(auth)
    assert tm.get_token_status('acct_1') == TokenStatus.VALID


def test_status_page_access_token_field():
    """page_access_token field is also accepted as evidence of a stored token."""
    auth = _make_auth(
        {'provider': 'meta_facebook_page', 'page_access_token': 'tok', 'expires_at': _future(30)}
    )
    tm = TokenManager(auth)
    assert tm.get_token_status('acct_1') == TokenStatus.VALID


def test_status_invalid_expires_at_treated_as_valid():
    """Malformed expires_at should not crash; be optimistic."""
    auth = _make_auth(
        {'provider': 'meta_threads', 'access_token': 'tok', 'expires_at': 'not-a-date'}
    )
    tm = TokenManager(auth)
    assert tm.get_token_status('acct_1') == TokenStatus.VALID


def test_status_naive_datetime_treated_as_utc():
    """expires_at without timezone info is assumed UTC."""
    naive_future = (
        (datetime.now(tz=UTC) + timedelta(days=30)).replace(tzinfo=None).isoformat()
    )  # no tzinfo
    auth = _make_auth(
        {'provider': 'meta_threads', 'access_token': 'tok', 'expires_at': naive_future}
    )
    tm = TokenManager(auth)
    assert tm.get_token_status('acct_1') == TokenStatus.VALID


# ── refresh_token ─────────────────────────────────────────────────────────────


def test_refresh_missing_account():
    auth = _make_auth(None)
    tm = TokenManager(auth)
    ok, err = tm.refresh_token('acct_1')
    assert ok is False
    assert err is not None


def test_refresh_facebook_page_is_noop():
    """Facebook Page tokens never expire; refresh is a no-op."""
    auth = _make_auth({'provider': 'meta_facebook_page', 'page_access_token': 'pgtok'})
    tm = TokenManager(auth)
    ok, err = tm.refresh_token('fb_acct')
    assert ok is True
    assert err is None
    auth.save_account_credentials.assert_not_called()


def test_refresh_unknown_provider_is_noop():
    """Unknown provider is treated as non-refreshable (no-op)."""
    auth = _make_auth({'provider': 'meta_unknown', 'access_token': 'tok'})
    tm = TokenManager(auth)
    ok, err = tm.refresh_token('acct_1')
    assert ok is True
    assert err is None


def test_refresh_no_access_token():
    auth = _make_auth({'provider': 'meta_threads'})
    tm = TokenManager(auth)
    ok, err = tm.refresh_token('acct_1')
    assert ok is False
    assert 'access token' in (err or '').lower()


def _mock_refresh_response(new_token: str = 'new_tok', expires_in: int = 5184000) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {'access_token': new_token, 'expires_in': expires_in}
    resp.raise_for_status.return_value = None
    return resp


@pytest.mark.parametrize(
    'provider,endpoint_fragment',
    [
        ('meta_threads', 'graph.threads.net'),
        ('meta_instagram', 'graph.instagram.com'),
    ],
)
def test_refresh_threads_and_instagram_success(provider, endpoint_fragment):
    creds = {
        'provider': provider,
        'access_token': 'old_tok',
        'expires_at': _future(3),
    }
    auth = _make_auth(creds)
    tm = TokenManager(auth)

    with patch('requests.get', return_value=_mock_refresh_response()) as mock_get:
        ok, err = tm.refresh_token('acct_1')

    assert ok is True
    assert err is None
    called_url = mock_get.call_args[0][0]
    assert endpoint_fragment in called_url
    saved = auth.save_account_credentials.call_args[0][1]
    assert saved['access_token'] == 'new_tok'
    assert 'expires_at' in saved


def test_refresh_updates_expires_at():
    creds = {'provider': 'meta_threads', 'access_token': 'old_tok', 'expires_at': _future(3)}
    auth = _make_auth(creds)
    tm = TokenManager(auth)

    with patch('requests.get', return_value=_mock_refresh_response(expires_in=5184000)):
        ok, _ = tm.refresh_token('acct_1')

    assert ok is True
    saved = auth.save_account_credentials.call_args[0][1]
    new_expiry = datetime.fromisoformat(saved['expires_at'])
    # Should be roughly 60 days from now
    assert (new_expiry - datetime.now(tz=UTC)).days >= 59


def test_refresh_response_missing_access_token():
    creds = {'provider': 'meta_threads', 'access_token': 'old_tok'}
    auth = _make_auth(creds)
    tm = TokenManager(auth)

    resp = MagicMock()
    resp.json.return_value = {}  # no access_token field
    resp.raise_for_status.return_value = None
    with patch('requests.get', return_value=resp):
        ok, err = tm.refresh_token('acct_1')

    assert ok is False
    assert 'access token' in (err or '').lower()
    auth.save_account_credentials.assert_not_called()


def test_refresh_timeout():
    creds = {'provider': 'meta_threads', 'access_token': 'tok'}
    auth = _make_auth(creds)
    tm = TokenManager(auth)

    with patch('requests.get', side_effect=requests.Timeout):
        ok, err = tm.refresh_token('acct_1')

    assert ok is False
    assert 'timed out' in (err or '').lower()


def test_refresh_connection_error():
    creds = {'provider': 'meta_instagram', 'access_token': 'tok'}
    auth = _make_auth(creds)
    tm = TokenManager(auth)

    with patch('requests.get', side_effect=requests.ConnectionError):
        ok, err = tm.refresh_token('acct_1')

    assert ok is False
    assert 'connect' in (err or '').lower()


def test_refresh_http_error():
    creds = {'provider': 'meta_threads', 'access_token': 'tok'}
    auth = _make_auth(creds)
    tm = TokenManager(auth)

    resp = MagicMock()
    resp.status_code = 401
    with patch('requests.get', side_effect=requests.HTTPError(response=resp)):
        ok, err = tm.refresh_token('acct_1')

    assert ok is False
    assert '401' in (err or '')


def test_refresh_unexpected_exception():
    creds = {'provider': 'meta_threads', 'access_token': 'tok'}
    auth = _make_auth(creds)
    tm = TokenManager(auth)

    with patch('requests.get', side_effect=RuntimeError('boom')):
        ok, err = tm.refresh_token('acct_1')

    assert ok is False
    assert 'boom' in (err or '')


# ── get_all_statuses ──────────────────────────────────────────────────────────


def test_get_all_statuses_filters_to_meta_only():
    from src.utils.constants import AccountConfig

    accounts = [
        AccountConfig(platform_id='twitter', account_id='twitter_1', profile_name=''),
        AccountConfig(platform_id='meta_threads', account_id='meta_threads_1', profile_name=''),
        AccountConfig(platform_id='meta_instagram', account_id='meta_instagram_1', profile_name=''),
        AccountConfig(platform_id='bluesky', account_id='bluesky_1', profile_name=''),
    ]
    auth = MagicMock()
    auth.get_accounts.return_value = accounts

    def _creds(account_id):
        if account_id == 'meta_threads_1':
            return {'provider': 'meta_threads', 'access_token': 'tok', 'expires_at': _future(30)}
        if account_id == 'meta_instagram_1':
            return {'provider': 'meta_instagram', 'access_token': 'tok', 'expires_at': _past(1)}
        return None

    auth.get_account_credentials.side_effect = _creds
    tm = TokenManager(auth)
    statuses = tm.get_all_statuses()

    assert set(statuses.keys()) == {'meta_threads_1', 'meta_instagram_1'}
    assert statuses['meta_threads_1'] == TokenStatus.VALID
    assert statuses['meta_instagram_1'] == TokenStatus.EXPIRED


def test_get_all_statuses_empty_when_no_meta_accounts():
    from src.utils.constants import AccountConfig

    accounts = [
        AccountConfig(platform_id='twitter', account_id='twitter_1', profile_name=''),
    ]
    auth = MagicMock()
    auth.get_accounts.return_value = accounts
    tm = TokenManager(auth)
    assert tm.get_all_statuses() == {}


# ── refresh_all_expiring ──────────────────────────────────────────────────────


def test_refresh_all_expiring_only_refreshes_expires_soon():
    from src.utils.constants import AccountConfig

    accounts = [
        AccountConfig(platform_id='meta_threads', account_id='th_1', profile_name=''),
        AccountConfig(platform_id='meta_instagram', account_id='ig_1', profile_name=''),
        AccountConfig(platform_id='meta_facebook_page', account_id='fb_1', profile_name=''),
    ]
    auth = MagicMock()
    auth.get_accounts.return_value = accounts

    def _creds(account_id):
        if account_id == 'th_1':
            # EXPIRES_SOON
            return {
                'provider': 'meta_threads',
                'access_token': 'tok',
                'expires_at': _future(3),
            }
        if account_id == 'ig_1':
            # VALID (far future)
            return {
                'provider': 'meta_instagram',
                'access_token': 'tok',
                'expires_at': _future(30),
            }
        if account_id == 'fb_1':
            # No expiry — Facebook Page
            return {'provider': 'meta_facebook_page', 'page_access_token': 'pgtok'}
        return None

    auth.get_account_credentials.side_effect = _creds

    tm = TokenManager(auth)
    with patch('requests.get', return_value=_mock_refresh_response()) as mock_get:
        results = tm.refresh_all_expiring()

    # Only th_1 should have been refreshed (ig_1 is VALID, fb_1 has no expiry → VALID)
    assert set(results.keys()) == {'th_1'}
    assert results['th_1'] is True
    assert mock_get.call_count == 1


def test_refresh_all_expiring_returns_false_on_failure():
    from src.utils.constants import AccountConfig

    accounts = [
        AccountConfig(platform_id='meta_threads', account_id='th_1', profile_name=''),
    ]
    auth = MagicMock()
    auth.get_accounts.return_value = accounts
    auth.get_account_credentials.return_value = {
        'provider': 'meta_threads',
        'access_token': 'tok',
        'expires_at': _future(3),
    }

    tm = TokenManager(auth)
    with patch('requests.get', side_effect=requests.Timeout):
        results = tm.refresh_all_expiring()

    assert results == {'th_1': False}


def test_refresh_all_expiring_empty_when_nothing_expires_soon():
    from src.utils.constants import AccountConfig

    accounts = [
        AccountConfig(platform_id='meta_threads', account_id='th_1', profile_name=''),
    ]
    auth = MagicMock()
    auth.get_accounts.return_value = accounts
    auth.get_account_credentials.return_value = {
        'provider': 'meta_threads',
        'access_token': 'tok',
        'expires_at': _future(30),
    }
    tm = TokenManager(auth)
    results = tm.refresh_all_expiring()
    assert results == {}
