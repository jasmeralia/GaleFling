"""Tests for the log upload Lambda."""

import json
import sys
import types

fake_boto3 = types.SimpleNamespace(client=lambda _name: object())
sys.modules.setdefault('boto3', fake_boto3)

import infrastructure.lambda_function as lf  # noqa: E402


class FakeSES:
    def __init__(self):
        self.sent = []
        self.raw_sent = []

    def send_email(self, **kwargs):
        self.sent.append(kwargs)

    def send_raw_email(self, **kwargs):
        self.raw_sent.append(kwargs)


def _make_event(body: dict) -> dict:
    return {
        'httpMethod': 'POST',
        'body': json.dumps(body),
    }


def test_missing_user_notes_returns_400(monkeypatch):
    fake_ses = FakeSES()
    monkeypatch.setattr(lf, 'ses', fake_ses)

    event = _make_event({'user_id': 'abc'})
    result = lf.lambda_handler(event, None)

    assert result['statusCode'] == 400
    body = json.loads(result['body'])
    assert body['message'] == 'Missing required field: user_notes'


def test_user_notes_in_metadata_and_email(monkeypatch):
    fake_ses = FakeSES()
    monkeypatch.setattr(lf, 'ses', fake_ses)

    event = _make_event(
        {
            'app_version': '1.5.2',
            'error_code': 'POST-FAILED',
            'user_id': 'abc',
            'user_notes': 'Attached an image and clicked OK',
            'hostname': 'storm-pc',
            'username': 'morgan',
            'os_version': '10.0.26100',
            'os_platform': 'Windows-11-10.0.26100-SP0',
            'ffmpeg_version': '7.1.1-custom',
            'log_files': [],
            'screenshots': [],
        }
    )

    result = lf.lambda_handler(event, None)
    assert result['statusCode'] == 200

    assert fake_ses.sent
    email_body = fake_ses.sent[0]['Message']['Body']['Text']['Data']
    assert 'Hostname: storm-pc' in email_body
    assert 'Username: morgan' in email_body
    assert 'OS Version: 10.0.26100' in email_body
    assert 'User Notes:' in email_body
    assert 'Attached an image and clicked OK' in email_body
    assert 'OS Platform: Windows-11-10.0.26100-SP0' in email_body
    assert 'FFmpeg Version: 7.1.1-custom' in email_body


def test_attachments_use_raw_email(monkeypatch):
    fake_ses = FakeSES()
    monkeypatch.setattr(lf, 'ses', fake_ses)

    event = _make_event(
        {
            'app_version': '1.5.2',
            'error_code': 'POST-FAILED',
            'user_id': 'abc',
            'user_notes': 'Attached an image and clicked OK',
            'os_platform': 'Windows-11-10.0.26100-SP0',
            'log_files': [{'filename': 'app.log', 'content': 'SGVsbG8='}],
            'screenshots': [],
        }
    )

    result = lf.lambda_handler(event, None)
    assert result['statusCode'] == 200
    assert fake_ses.raw_sent


def test_rejects_payload_when_app_version_below_cutoff(monkeypatch):
    fake_ses = FakeSES()
    monkeypatch.setattr(lf, 'ses', fake_ses)

    event = _make_event(
        {
            'app_version': '1.5.0',
            'error_code': 'POST-FAILED',
            'user_id': 'abc',
            'user_notes': 'Attached an image and clicked OK',
            'log_files': [],
            'screenshots': [],
        }
    )

    result = lf.lambda_handler(event, None)
    assert result['statusCode'] == 426
    body = json.loads(result['body'])
    assert body['error_code'] == 'LOG-CLIENT-TOO-OLD'
    assert body['min_supported_version'] == '1.5.1'
    assert 'upgrade' in body['message'].lower()
    assert not fake_ses.sent
    assert not fake_ses.raw_sent


def test_accepts_payload_at_cutoff_version(monkeypatch):
    fake_ses = FakeSES()
    monkeypatch.setattr(lf, 'ses', fake_ses)

    event = _make_event(
        {
            'app_version': '1.5.1',
            'error_code': 'POST-FAILED',
            'user_id': 'abc',
            'user_notes': 'Attached an image and clicked OK',
            'log_files': [],
            'screenshots': [],
        }
    )

    result = lf.lambda_handler(event, None)
    assert result['statusCode'] == 200
    assert fake_ses.sent
