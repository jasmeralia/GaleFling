"""Tests for the credential JSON import module."""

import json
from pathlib import Path

import pytest

from src.core.auth_manager import AuthManager
from src.core.credential_importer import SUPPORTED_VERSION, import_credentials


@pytest.fixture()
def auth(tmp_path, monkeypatch):
    monkeypatch.setattr('src.core.auth_manager.get_auth_dir', lambda: tmp_path)
    monkeypatch.setattr(AuthManager, '_find_dev_auth_dir', lambda self: None)
    return AuthManager()


def _write_json(tmp_path: Path, data: object) -> Path:
    p = tmp_path / 'creds.json'
    p.write_text(json.dumps(data))
    return p


def test_full_import(auth, tmp_path):
    data = {
        'version': SUPPORTED_VERSION,
        'meta': {
            'threads': {'app_id': 'th_id', 'app_secret': 'th_sec'},
            'instagram': {'app_id': 'ig_id', 'app_secret': 'ig_sec'},
            'facebook': {'app_id': 'fb_id', 'app_secret': 'fb_sec'},
        },
        'twitter': {'client_id': 'tw_cid', 'client_secret': 'tw_csec'},
        'aws': {
            'access_key_id': 'AKID',
            'secret_access_key': 'secret',
            'region': 'us-west-2',
            'media_staging_bucket': 'my-bucket',
        },
        'smtp': {
            'host': 'smtp.gmail.com',
            'port': 587,
            'username': 'galefling@rin-city.com',
            'app_password': 'app-pw',
        },
    }
    result = import_credentials(_write_json(tmp_path, data), auth)

    assert result.success
    assert not result.errors
    assert set(result.imported) == {
        'meta.threads',
        'meta.instagram',
        'meta.facebook',
        'twitter',
        'aws',
        'smtp',
    }

    th = auth.get_meta_threads_app_credentials()
    assert th is not None and th['app_id'] == 'th_id'
    ig = auth.get_meta_instagram_app_credentials()
    assert ig is not None and ig['app_id'] == 'ig_id'
    fb = auth.get_meta_facebook_app_credentials()
    assert fb is not None and fb['app_id'] == 'fb_id'
    tw = auth.get_twitter_oauth2_app_credentials()
    assert tw is not None and tw['client_id'] == 'tw_cid'
    aws = auth.get_aws_media_staging_credentials()
    assert aws is not None
    assert aws['access_key_id'] == 'AKID'
    assert aws['media_staging_bucket'] == 'my-bucket'
    smtp = auth.get_smtp_credentials()
    assert smtp is not None
    assert smtp['host'] == 'smtp.gmail.com'
    assert smtp['port'] == 587
    assert smtp['username'] == 'galefling@rin-city.com'


def test_partial_import_meta_only(auth, tmp_path):
    data = {
        'version': SUPPORTED_VERSION,
        'meta': {
            'threads': {'app_id': 'th_id', 'app_secret': 'th_sec'},
        },
    }
    result = import_credentials(_write_json(tmp_path, data), auth)

    assert result.success
    assert 'meta.threads' in result.imported
    assert 'twitter' not in result.imported
    assert 'aws' not in result.imported
    assert auth.get_meta_instagram_app_credentials() is None
    assert auth.get_meta_facebook_app_credentials() is None


def test_version_mismatch_rejected(auth, tmp_path):
    data = {'version': 99, 'meta': {}}
    result = import_credentials(_write_json(tmp_path, data), auth)

    assert not result.success
    assert result.version_mismatch
    assert result.errors


def test_invalid_json_rejected(auth, tmp_path):
    p = tmp_path / 'bad.json'
    p.write_text('not json {{{')
    result = import_credentials(p, auth)

    assert not result.success
    assert result.errors


def test_missing_file_rejected(auth, tmp_path):
    result = import_credentials(tmp_path / 'nonexistent.json', auth)

    assert not result.success
    assert result.errors


def test_incomplete_meta_section_skipped(auth, tmp_path):
    data = {
        'version': SUPPORTED_VERSION,
        'meta': {
            'threads': {'app_id': 'th_id'},  # missing app_secret
        },
    }
    result = import_credentials(_write_json(tmp_path, data), auth)

    assert not result.success
    assert 'meta.threads' in result.skipped
    assert auth.get_meta_threads_app_credentials() is None


def test_incomplete_aws_section_skipped(auth, tmp_path):
    data = {
        'version': SUPPORTED_VERSION,
        'aws': {'access_key_id': 'AKID'},  # missing secret and bucket
    }
    result = import_credentials(_write_json(tmp_path, data), auth)

    assert 'aws' in result.skipped
    assert auth.get_aws_media_staging_credentials() is None


def test_incomplete_twitter_section_skipped(auth, tmp_path):
    data = {
        'version': SUPPORTED_VERSION,
        'twitter': {'client_id': 'cid'},  # missing client_secret
    }
    result = import_credentials(_write_json(tmp_path, data), auth)

    assert 'twitter' in result.skipped
    assert auth.get_twitter_oauth2_app_credentials() is None


def test_incomplete_smtp_section_skipped(auth, tmp_path):
    data = {
        'version': SUPPORTED_VERSION,
        'smtp': {'host': 'smtp.gmail.com', 'username': 'user@example.com'},  # missing app_password
    }
    result = import_credentials(_write_json(tmp_path, data), auth)

    assert 'smtp' in result.skipped
    assert auth.get_smtp_credentials() is None


def test_smtp_default_port(auth, tmp_path):
    data = {
        'version': SUPPORTED_VERSION,
        'smtp': {
            'host': 'smtp.gmail.com',
            'username': 'galefling@rin-city.com',
            'app_password': 'app-pw',
            # no 'port' key — should default to 587
        },
    }
    result = import_credentials(_write_json(tmp_path, data), auth)

    assert 'smtp' in result.imported
    smtp = auth.get_smtp_credentials()
    assert smtp is not None and smtp['port'] == 587


def test_aws_default_region(auth, tmp_path):
    data = {
        'version': SUPPORTED_VERSION,
        'aws': {
            'access_key_id': 'AKID',
            'secret_access_key': 'secret',
            'media_staging_bucket': 'my-bucket',
            # no 'region' key — should default to us-west-2
        },
    }
    result = import_credentials(_write_json(tmp_path, data), auth)

    assert 'aws' in result.imported
    aws = auth.get_aws_media_staging_credentials()
    assert aws is not None and aws['region'] == 'us-west-2'


def test_meta_oauth_redirect_uri_imported(auth, tmp_path):
    data = {
        'version': SUPPORTED_VERSION,
        'meta': {
            'oauth_redirect_uri': 'https://galefling.jasmer.tools/oauth/callback',
            'threads': {'app_id': 'th_id', 'app_secret': 'th_sec'},
        },
    }
    result = import_credentials(_write_json(tmp_path, data), auth)

    assert 'meta.oauth_redirect_uri' in result.imported
    assert auth.get_meta_oauth_redirect_uri() == 'https://galefling.jasmer.tools/oauth/callback'


def test_meta_oauth_redirect_uri_absent_does_not_override_default(auth, tmp_path):
    data = {
        'version': SUPPORTED_VERSION,
        'meta': {
            'threads': {'app_id': 'th_id', 'app_secret': 'th_sec'},
        },
    }
    result = import_credentials(_write_json(tmp_path, data), auth)

    assert 'meta.oauth_redirect_uri' not in result.imported
    # Default value still returned
    assert auth.get_meta_oauth_redirect_uri() == 'https://galefling.jasmer.tools/oauth/callback'


# ── Malformed input — must report an error, never raise ────────────────────


def test_top_level_not_an_object_reports_error(auth, tmp_path):
    result = import_credentials(_write_json(tmp_path, [1, 2, 3]), auth)

    assert not result.success
    assert any('list' in err for err in result.errors)


def test_top_level_string_reports_error(auth, tmp_path):
    result = import_credentials(_write_json(tmp_path, 'oops'), auth)

    assert not result.success
    assert any('str' in err for err in result.errors)


def test_meta_section_wrong_type_reports_error_not_crash(auth, tmp_path):
    data = {'version': SUPPORTED_VERSION, 'meta': 'oops'}
    result = import_credentials(_write_json(tmp_path, data), auth)

    assert any("'meta'" in err and 'str' in err for err in result.errors)
    assert auth.get_meta_threads_app_credentials() is None


def test_meta_section_null_is_silently_ignored(auth, tmp_path):
    data = {'version': SUPPORTED_VERSION, 'meta': None}
    result = import_credentials(_write_json(tmp_path, data), auth)

    assert result.errors == []
    assert result.skipped == []


def test_twitter_section_wrong_type_reports_error_not_crash(auth, tmp_path):
    data = {'version': SUPPORTED_VERSION, 'twitter': 'oops'}
    result = import_credentials(_write_json(tmp_path, data), auth)

    assert any("'twitter'" in err and 'str' in err for err in result.errors)
    assert auth.get_twitter_oauth2_app_credentials() is None


def test_meta_threads_subsection_wrong_type_reports_error_not_crash(auth, tmp_path):
    data = {'version': SUPPORTED_VERSION, 'meta': {'threads': [1, 2]}}
    result = import_credentials(_write_json(tmp_path, data), auth)

    assert any("'meta.threads'" in err and 'list' in err for err in result.errors)
    assert auth.get_meta_threads_app_credentials() is None


def test_smtp_field_wrong_type_skipped_not_crash(auth, tmp_path):
    data = {
        'version': SUPPORTED_VERSION,
        'smtp': {'host': 'h', 'username': 'u', 'app_password': 12345},  # int, not str
    }
    result = import_credentials(_write_json(tmp_path, data), auth)

    assert 'smtp' in result.skipped
    assert auth.get_smtp_credentials() is None


def test_missing_field_diagnostics_never_log_credential_values(auth, tmp_path, caplog):
    """Skipped/malformed-section diagnostics must name fields, never leak values.

    This log can be uploaded and emailed (see docs/testing/FUNCTIONAL_TESTING.md /
    the log-upload path) — a leaked value here would reach an inbox, not just a
    local file. Uses a section with one real-looking secret value plus a wrong-type
    field, and asserts that literal string appears nowhere in any log record.
    """
    caplog.set_level('DEBUG', logger='GaleFling')
    secret_value = 'sk_live_super_secret_value_12345'
    data = {
        'version': SUPPORTED_VERSION,
        'twitter': {'client_id': secret_value, 'client_secret': ''},  # incomplete: skipped
        'smtp': {'host': 'h', 'username': 'u', 'app_password': 999},  # wrong type: skipped
        'meta': {'threads': 'not-an-object'},  # malformed: error
    }
    result = import_credentials(_write_json(tmp_path, data), auth)

    assert 'twitter' in result.skipped
    assert 'smtp' in result.skipped
    assert any('meta.threads' in err for err in result.errors)

    all_log_text = '\n'.join(record.getMessage() for record in caplog.records)
    assert secret_value not in all_log_text
    assert '999' not in all_log_text
    # Errors/skips only ever surface as ImportResult data, not printed here —
    # confirm the result itself doesn't carry the value either.
    assert secret_value not in '\n'.join(result.errors)
    assert secret_value not in '\n'.join(result.skipped)


def test_valid_import_unaffected_by_hardening(auth, tmp_path):
    data = {
        'version': SUPPORTED_VERSION,
        'meta': {'threads': {'app_id': 'a', 'app_secret': 'b'}},
        'twitter': {'client_id': 'c', 'client_secret': 'd'},
        'aws': {'access_key_id': 'e', 'secret_access_key': 'f', 'media_staging_bucket': 'g'},
        'smtp': {'host': 'h', 'username': 'i', 'app_password': 'j'},
    }
    result = import_credentials(_write_json(tmp_path, data), auth)

    assert result.success
    assert result.errors == []
    assert set(result.imported) == {'meta.threads', 'twitter', 'aws', 'smtp'}
