"""Tests for AWS utility helpers."""

import sys
from unittest.mock import MagicMock, patch

from src.core.aws_utils import check_s3_connection


def test_check_s3_connection_success():
    mock_client = MagicMock()
    with patch('boto3.client', return_value=mock_client):
        ok, msg = check_s3_connection('AKID', 'secret', 'us-west-2', 'my-bucket')

    assert ok is True
    assert msg == ''
    mock_client.put_object.assert_called_once_with(
        Bucket='my-bucket',
        Key='staging/.galefling-connection-test',
        Body=b'galefling-connection-test',
        ContentType='text/plain',
    )


def test_check_s3_connection_client_error():
    import botocore.exceptions

    mock_client = MagicMock()
    mock_client.put_object.side_effect = botocore.exceptions.ClientError(
        {'Error': {'Code': 'AccessDenied', 'Message': 'Access Denied'}},
        'PutObject',
    )
    with patch('boto3.client', return_value=mock_client):
        ok, msg = check_s3_connection('AKID', 'secret', 'us-west-2', 'my-bucket')

    assert ok is False
    assert 'AccessDenied' in msg
    assert 'Access Denied' in msg


def test_check_s3_connection_no_credentials():
    import botocore.exceptions

    mock_client = MagicMock()
    mock_client.put_object.side_effect = botocore.exceptions.NoCredentialsError()
    with patch('boto3.client', return_value=mock_client):
        ok, msg = check_s3_connection('', '', 'us-west-2', 'my-bucket')

    assert ok is False
    assert 'credentials' in msg.lower()


def test_check_s3_connection_unexpected_error():
    mock_client = MagicMock()
    mock_client.put_object.side_effect = RuntimeError('network failure')
    with patch('boto3.client', return_value=mock_client):
        ok, msg = check_s3_connection('AKID', 'secret', 'us-west-2', 'my-bucket')

    assert ok is False
    assert 'network failure' in msg


def test_boto3_not_installed():
    fake_modules = {
        'boto3': None,
        'botocore': None,
        'botocore.exceptions': None,
    }
    with patch.dict(sys.modules, fake_modules):
        ok, msg = check_s3_connection('AKID', 'secret', 'us-west-2', 'my-bucket')

    assert ok is False
    assert 'boto3' in msg
