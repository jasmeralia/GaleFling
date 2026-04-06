"""Tests for the log upload Lambda."""

import base64
import json
import sys
import types
from urllib.parse import parse_qs, urlparse

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


def test_ffmpeg_version_accepts_legacy_field_name(monkeypatch):
    fake_ses = FakeSES()
    monkeypatch.setattr(lf, 'ses', fake_ses)

    event = _make_event(
        {
            'app_version': '1.5.2',
            'error_code': 'POST-FAILED',
            'user_id': 'abc',
            'user_notes': 'legacy payload',
            'ffmpegVersion': '6.0-legacy',
            'log_files': [],
            'screenshots': [],
        }
    )

    result = lf.lambda_handler(event, None)
    assert result['statusCode'] == 200
    assert fake_ses.sent
    email_body = fake_ses.sent[0]['Message']['Body']['Text']['Data']
    assert 'FFmpeg Version: 6.0-legacy' in email_body


def test_ffmpeg_version_accepts_nested_metadata(monkeypatch):
    fake_ses = FakeSES()
    monkeypatch.setattr(lf, 'ses', fake_ses)

    event = _make_event(
        {
            'app_version': '1.5.2',
            'error_code': 'POST-FAILED',
            'user_id': 'abc',
            'user_notes': 'nested payload',
            'metadata': {'ffmpeg_version': '7.2.0-nested'},
            'log_files': [],
            'screenshots': [],
        }
    )

    result = lf.lambda_handler(event, None)
    assert result['statusCode'] == 200
    assert fake_ses.sent
    email_body = fake_ses.sent[0]['Message']['Body']['Text']['Data']
    assert 'FFmpeg Version: 7.2.0-nested' in email_body


def test_ffmpeg_version_defaults_to_unknown_when_missing(monkeypatch):
    fake_ses = FakeSES()
    monkeypatch.setattr(lf, 'ses', fake_ses)

    event = _make_event(
        {
            'app_version': '1.5.2',
            'error_code': 'POST-FAILED',
            'user_id': 'abc',
            'user_notes': 'no ffmpeg key',
            'log_files': [],
            'screenshots': [],
        }
    )

    result = lf.lambda_handler(event, None)
    assert result['statusCode'] == 200
    assert fake_ses.sent
    email_body = fake_ses.sent[0]['Message']['Body']['Text']['Data']
    assert 'FFmpeg Version: unknown' in email_body


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


def test_wer_reports_are_included_as_attachments(monkeypatch):
    fake_ses = FakeSES()
    monkeypatch.setattr(lf, 'ses', fake_ses)

    event = _make_event(
        {
            'app_version': '1.5.2',
            'error_code': 'POST-FAILED',
            'user_id': 'abc',
            'user_notes': 'Attached diagnostics',
            'log_files': [],
            'screenshots': [],
            'wer_reports': [
                {
                    'filename': 'AppCrash_GaleFling.exe_001_Report.wer',
                    'content': base64.b64encode(b'wer content').decode('ascii'),
                }
            ],
        }
    )

    result = lf.lambda_handler(event, None)
    assert result['statusCode'] == 200
    assert fake_ses.raw_sent
    raw_body = fake_ses.raw_sent[0]['RawMessage']['Data'].decode('utf-8', errors='ignore')
    assert 'AppCrash_GaleFling.exe_001_Report.wer' in raw_body
    assert 'wer content' not in raw_body  # attachment content should remain base64-encoded


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


# ── _handle_oauth_callback ────────────────────────────────────────────────────


def _make_state(port: int) -> str:
    payload = json.dumps({'csrf': 'testcsrf', 'port': port})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _make_oauth_event(params: dict) -> dict:
    return {'rawPath': '/oauth/callback', 'queryStringParameters': params}


def test_oauth_callback_redirects_to_localhost():
    state = _make_state(8765)
    event = _make_oauth_event({'code': 'AUTH_CODE', 'state': state})
    result = lf.lambda_handler(event, None)
    assert result['statusCode'] == 302
    location = result['headers']['Location']
    assert location.startswith('http://localhost:8765/oauth/callback')
    parsed = urlparse(location)
    qs = parse_qs(parsed.query)
    assert qs['code'] == ['AUTH_CODE']
    assert qs['state'] == [state]


def test_oauth_callback_decodes_port_from_state():
    state = _make_state(8769)
    event = _make_oauth_event({'code': 'CODE', 'state': state})
    result = lf.lambda_handler(event, None)
    assert result['statusCode'] == 302
    assert 'localhost:8769' in result['headers']['Location']


def test_oauth_callback_fallback_port_on_bad_state():
    event = _make_oauth_event({'code': 'CODE', 'state': 'not-valid-base64!!!'})
    result = lf.lambda_handler(event, None)
    assert result['statusCode'] == 302
    assert 'localhost:8765' in result['headers']['Location']


def test_oauth_callback_forwards_error():
    state = _make_state(8765)
    event = _make_oauth_event(
        {'error': 'access_denied', 'error_description': 'User denied', 'state': state}
    )
    result = lf.lambda_handler(event, None)
    assert result['statusCode'] == 302
    location = result['headers']['Location']
    assert 'error=access_denied' in location
    assert 'localhost:8765' in location


def test_oauth_callback_does_not_invoke_ses(monkeypatch):
    fake_ses = FakeSES()
    monkeypatch.setattr(lf, 'ses', fake_ses)
    state = _make_state(8765)
    event = _make_oauth_event({'code': 'CODE', 'state': state})
    lf.lambda_handler(event, None)
    assert not fake_ses.sent
    assert not fake_ses.raw_sent
