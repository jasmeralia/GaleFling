"""Tests for logging utilities."""

from __future__ import annotations

import pytest

import src.core.logger as logger
from src.core.logger import redact_credentials


def test_setup_logging_creates_log_file(tmp_path, monkeypatch):
    monkeypatch.setattr(logger, 'get_logs_dir', lambda: tmp_path)

    log = logger.setup_logging(debug_mode=False)
    path = logger.get_current_log_path()

    assert path is not None
    assert path.exists()
    assert log.name == 'GaleFling'


def test_reset_log_file_rotates(tmp_path, monkeypatch):
    monkeypatch.setattr(logger, 'get_logs_dir', lambda: tmp_path)

    logger.setup_logging(debug_mode=False)
    first_path = logger.get_current_log_path()

    logger.reset_log_file()
    second_path = logger.get_current_log_path()

    assert first_path is not None
    assert second_path is not None
    assert second_path.exists()


def test_log_error_writes_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(logger, 'get_logs_dir', lambda: tmp_path)
    monkeypatch.setattr(logger, 'capture_screenshot', lambda *_: None)

    logger.setup_logging(debug_mode=False)

    logger.log_error('POST-FAILED', 'Twitter', details={'info': 'bad'})

    path = logger.get_current_log_path()
    assert path is not None
    content = path.read_text()
    assert 'POST-FAILED' in content
    assert 'Twitter' in content


# ── Credential redaction ────────────────────────────────────────────


@pytest.mark.parametrize(
    ('raw', 'secret'),
    [
        ('GET https://graph.facebook.com/me?access_token=EAAsupersecret failed', 'EAAsupersecret'),
        ('...?access_token_secret=abc123def456&x=1', 'abc123def456'),
        ('POST /oauth/access_token?client_secret=sh0uldnotleak', 'sh0uldnotleak'),
        ('app_secret=an0thersecret&grant_type=x', 'an0thersecret'),
        ('{"access_token": "EAAlongtokenvalue"}', 'EAAlongtokenvalue'),
        ('{"client_secret": "secretvaluehere"}', 'secretvaluehere'),
        ('{"page_access_token": "EAAGpagetoken123"}', 'EAAGpagetoken123'),
        ('Authorization: Bearer EAAbearertokenvalue', 'EAAbearertokenvalue'),
    ],
)
def test_redact_credentials_masks_secrets(raw, secret):
    """Every shape a token reaches a log in — URL param, JSON field, Bearer header."""
    redacted = redact_credentials(raw)
    assert secret not in redacted
    assert '***' in redacted


def test_redact_credentials_keeps_surrounding_context():
    """Redaction must stay useful for debugging, not blank the message."""
    redacted = redact_credentials(
        'ConnectionError: GET https://graph.threads.net/v1.0/me?access_token=EAAsecret123'
    )
    assert 'ConnectionError' in redacted
    assert 'graph.threads.net' in redacted
    assert 'EAAsecret123' not in redacted


def test_redact_credentials_accepts_non_strings():
    """Call sites pass exception objects directly."""
    exc = ValueError('access_token=EAAsecretvalue')
    assert 'EAAsecretvalue' not in redact_credentials(exc)


def test_redact_credentials_leaves_unrelated_text_alone():
    assert redact_credentials('posted 3 items in 1.2s') == 'posted 3 items in 1.2s'
