"""Pure-Python tests for browser-exported WebView session imports."""

import json

import pytest

from src.core.webview_environment import chrome_compatible_user_agent
from src.core.webview_session_import import (
    ImportedSession,
    SessionImportError,
    effective_user_agent,
    load_auth_json_file,
    load_session_metadata,
    parse_auth_json,
    save_session_metadata,
)

USER_ID = 'fixture-user-id'
USER_AGENT = 'FixtureBrowser/123.0'
X_BC = '0123456789abcdef0123456789abcdef01234567'
SESSION_COOKIE = 'fixture-session-token'
SECRET_VALUES = (USER_ID, USER_AGENT, X_BC, SESSION_COOKIE)


def _payload() -> dict[str, str]:
    return {
        'USER_ID': USER_ID,
        'USER_AGENT': USER_AGENT,
        'X_BC': X_BC,
        'COOKIE': f'sess={SESSION_COOKIE}; auth_id={USER_ID};',
    }


def _assert_safe_error(payload: dict[str, str]) -> SessionImportError:
    with pytest.raises(SessionImportError) as raised:
        parse_auth_json(json.dumps(payload))
    message = str(raised.value)
    assert all(secret not in message for secret in SECRET_VALUES)
    return raised.value


def test_parse_auth_json_accepts_valid_order_independent_cookie_payload():
    session = parse_auth_json(json.dumps(_payload()))

    assert session == ImportedSession(
        user_id=USER_ID,
        user_agent=USER_AGENT,
        x_bc=X_BC,
        cookies={'sess': SESSION_COOKIE, 'auth_id': USER_ID},
    )


@pytest.mark.parametrize('key', ['USER_ID', 'USER_AGENT', 'X_BC', 'COOKIE'])
def test_parse_auth_json_rejects_each_missing_key_without_exposing_secrets(key):
    payload = _payload()
    del payload[key]

    error = _assert_safe_error(payload)

    assert key in str(error)


@pytest.mark.parametrize('key', ['USER_ID', 'USER_AGENT', 'X_BC', 'COOKIE'])
def test_parse_auth_json_rejects_each_empty_value_without_exposing_secrets(key):
    payload = _payload()
    payload[key] = ''

    error = _assert_safe_error(payload)

    assert key in str(error)


def test_parse_auth_json_rejects_cookie_missing_sess_without_exposing_secrets():
    payload = _payload()
    payload['COOKIE'] = f'auth_id={USER_ID};'

    error = _assert_safe_error(payload)

    assert 'sess' in str(error)


def test_parse_auth_json_rejects_user_id_mismatch_without_exposing_secrets():
    payload = _payload()
    payload['USER_ID'] = 'different-fixture-user-id'

    with pytest.raises(SessionImportError) as raised:
        parse_auth_json(json.dumps(payload))
    assert all(secret not in str(raised.value) for secret in (*SECRET_VALUES, payload['USER_ID']))


def test_parse_auth_json_preserves_equals_signs_in_cookie_values():
    payload = _payload()
    payload['COOKIE'] = f'auth_id={USER_ID}; sess={SESSION_COOKIE}==;'

    session = parse_auth_json(json.dumps(payload))

    assert session.cookies['sess'] == f'{SESSION_COOKIE}=='


def test_load_auth_json_file_converts_malformed_json_to_safe_error(tmp_path):
    auth_path = tmp_path / 'auth.json'
    auth_path.write_text('{not valid json', encoding='utf-8')

    with pytest.raises(SessionImportError) as raised:
        load_auth_json_file(auth_path)
    assert all(secret not in str(raised.value) for secret in SECRET_VALUES)


def test_save_and_load_session_metadata_round_trip(tmp_path):
    session = parse_auth_json(json.dumps(_payload()))

    save_session_metadata(tmp_path, session)
    metadata = load_session_metadata(tmp_path)

    assert metadata is not None
    assert metadata['user_agent'] == USER_AGENT
    assert metadata['x_bc'] == X_BC
    assert metadata['user_id'] == USER_ID
    assert metadata['imported_at']


def test_effective_user_agent_uses_imported_user_agent(tmp_path):
    session = parse_auth_json(json.dumps(_payload()))
    save_session_metadata(tmp_path, session)

    assert effective_user_agent(tmp_path, 'Default QtWebEngine/6.11 Chrome/123') == USER_AGENT


def test_effective_user_agent_normalizes_default_without_sidecar(tmp_path):
    default = 'Mozilla/5.0 QtWebEngine/6.11 Chrome/123'

    assert effective_user_agent(tmp_path, default) == chrome_compatible_user_agent(default)


def test_load_session_metadata_returns_none_for_corrupt_sidecar(tmp_path):
    (tmp_path / 'galefling_session.json').write_text('{invalid', encoding='utf-8')

    assert load_session_metadata(tmp_path) is None
