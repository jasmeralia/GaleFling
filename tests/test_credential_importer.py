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
