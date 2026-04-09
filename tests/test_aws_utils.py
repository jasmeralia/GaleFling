"""Tests for AWS utility helpers.

boto3 is not installed in the test environment (it's a Windows-only runtime
dependency).  All tests mock the boto3 and botocore packages via
``sys.modules`` so they run without the real packages present.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.aws_utils import MediaStager, MediaStagingError, check_s3_connection

# ── boto3 mock fixture ────────────────────────────────────────────────────────


class _FakeClientError(Exception):
    """Minimal stand-in for botocore.exceptions.ClientError."""

    def __init__(self, error_response: dict, operation_name: str = ''):
        self.response = error_response
        super().__init__(str(error_response))


class _FakeNoCredentialsError(Exception):
    """Minimal stand-in for botocore.exceptions.NoCredentialsError."""


def _make_fake_exceptions():
    fake = MagicMock()
    fake.ClientError = _FakeClientError
    fake.NoCredentialsError = _FakeNoCredentialsError
    return fake


@pytest.fixture
def boto3_env():
    """Install a fake boto3 + botocore into sys.modules for one test.

    Yields ``(mock_boto3_module, mock_s3_client, fake_exceptions)``.
    """
    fake_exceptions = _make_fake_exceptions()
    fake_botocore = MagicMock()
    fake_botocore.exceptions = fake_exceptions

    mock_client = MagicMock()
    fake_boto3 = MagicMock()
    fake_boto3.client.return_value = mock_client

    modules = {
        'boto3': fake_boto3,
        'botocore': fake_botocore,
        'botocore.exceptions': fake_exceptions,
    }
    with patch.dict(sys.modules, modules):
        yield fake_boto3, mock_client, fake_exceptions


# ── check_s3_connection ───────────────────────────────────────────────────────


def test_check_s3_connection_success(boto3_env):
    _, mock_client, _ = boto3_env
    ok, msg = check_s3_connection('AKID', 'secret', 'us-west-2', 'my-bucket')

    assert ok is True
    assert msg == ''
    mock_client.put_object.assert_called_once_with(
        Bucket='my-bucket',
        Key='staging/.galefling-connection-test',
        Body=b'galefling-connection-test',
        ContentType='text/plain',
    )


def test_check_s3_connection_client_error(boto3_env):
    _, mock_client, fake_exc = boto3_env
    mock_client.put_object.side_effect = fake_exc.ClientError(
        {'Error': {'Code': 'AccessDenied', 'Message': 'Access Denied'}},
        'PutObject',
    )
    ok, msg = check_s3_connection('AKID', 'secret', 'us-west-2', 'my-bucket')

    assert ok is False
    assert 'AccessDenied' in msg
    assert 'Access Denied' in msg


def test_check_s3_connection_no_credentials(boto3_env):
    _, mock_client, fake_exc = boto3_env
    mock_client.put_object.side_effect = fake_exc.NoCredentialsError()
    ok, msg = check_s3_connection('', '', 'us-west-2', 'my-bucket')

    assert ok is False
    assert 'credentials' in msg.lower()


def test_check_s3_connection_unexpected_error(boto3_env):
    _, mock_client, _ = boto3_env
    mock_client.put_object.side_effect = RuntimeError('network failure')
    ok, msg = check_s3_connection('AKID', 'secret', 'us-west-2', 'my-bucket')

    assert ok is False
    assert 'network failure' in msg


def test_check_s3_connection_boto3_not_installed():
    fake_modules = {'boto3': None, 'botocore': None, 'botocore.exceptions': None}
    with patch.dict(sys.modules, fake_modules):
        ok, msg = check_s3_connection('AKID', 'secret', 'us-west-2', 'my-bucket')

    assert ok is False
    assert 'boto3' in msg


# ── MediaStager ───────────────────────────────────────────────────────────────


def _make_stager() -> MediaStager:
    return MediaStager(
        access_key_id='AKID',
        secret_access_key='secret',
        region='us-west-2',
        bucket='galefling-staging',
    )


def test_media_stager_upload_success(tmp_path, boto3_env):
    _, mock_client, _ = boto3_env
    image = tmp_path / 'photo.jpg'
    image.write_bytes(b'\xff\xd8\xff')

    url = _make_stager().upload_media(image)

    assert url.startswith('https://galefling-staging.s3.us-west-2.amazonaws.com/staging/')
    assert url.endswith('/photo.jpg')
    mock_client.put_object.assert_called_once()
    kw = mock_client.put_object.call_args[1]
    assert kw['Bucket'] == 'galefling-staging'
    assert kw['ContentType'] == 'image/jpeg'
    assert kw['Key'].startswith('staging/')


def test_media_stager_key_format(tmp_path, boto3_env):
    f = tmp_path / 'clip.mp4'
    f.write_bytes(b'data')

    url = _make_stager().upload_media(f)

    # https://bucket.s3.region.amazonaws.com/staging/date/uuid/filename
    # split('/') → ['https:', '', 'host', 'staging', 'date', 'uuid', 'filename'] = 7 parts
    parts = url.split('/')
    assert parts[3] == 'staging'
    assert len(parts) == 7


def test_media_stager_unique_keys_per_upload(tmp_path, boto3_env):
    f = tmp_path / 'img.png'
    f.write_bytes(b'data')

    stager = _make_stager()
    url1 = stager.upload_media(f)
    url2 = stager.upload_media(f)

    assert url1 != url2  # UUIDs differ


@pytest.mark.parametrize(
    'filename,expected_ct',
    [
        ('img.jpg', 'image/jpeg'),
        ('img.jpeg', 'image/jpeg'),
        ('img.png', 'image/png'),
        ('clip.mp4', 'video/mp4'),
        ('clip.mov', 'video/quicktime'),
        ('file.bin', 'application/octet-stream'),
        ('IMG.JPG', 'image/jpeg'),
    ],
)
def test_media_stager_content_type_detection(filename, expected_ct):
    ct = MediaStager._detect_content_type(Path(filename))
    assert ct == expected_ct


def test_media_stager_client_error_raises(tmp_path, boto3_env):
    _, mock_client, fake_exc = boto3_env
    f = tmp_path / 'img.jpg'
    f.write_bytes(b'data')

    mock_client.put_object.side_effect = fake_exc.ClientError(
        {'Error': {'Code': 'AccessDenied', 'Message': 'Access Denied'}},
        'PutObject',
    )
    with pytest.raises(MediaStagingError, match='AccessDenied'):
        _make_stager().upload_media(f)


def test_media_stager_no_credentials_raises(tmp_path, boto3_env):
    _, mock_client, fake_exc = boto3_env
    f = tmp_path / 'img.jpg'
    f.write_bytes(b'data')

    mock_client.put_object.side_effect = fake_exc.NoCredentialsError()
    with pytest.raises(MediaStagingError, match='credentials'):
        _make_stager().upload_media(f)


def test_media_stager_file_read_error_raises(tmp_path, boto3_env):
    missing = tmp_path / 'nonexistent.jpg'
    with pytest.raises(MediaStagingError, match='Could not read file'):
        _make_stager().upload_media(missing)


def test_media_stager_unexpected_error_raises(tmp_path, boto3_env):
    _, mock_client, _ = boto3_env
    f = tmp_path / 'img.jpg'
    f.write_bytes(b'data')

    mock_client.put_object.side_effect = RuntimeError('network blip')
    with pytest.raises(MediaStagingError, match='network blip'):
        _make_stager().upload_media(f)


def test_media_stager_boto3_not_installed(tmp_path):
    f = tmp_path / 'img.jpg'
    f.write_bytes(b'data')

    fake_modules = {'boto3': None, 'botocore': None, 'botocore.exceptions': None}
    with patch.dict(sys.modules, fake_modules), pytest.raises(MediaStagingError, match='boto3'):
        _make_stager().upload_media(f)
