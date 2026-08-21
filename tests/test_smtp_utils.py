"""Tests for SMTP connection-test helper.

smtplib is standard library, so these tests mock smtplib.SMTP / SMTP_SSL
directly rather than faking an optional dependency (contrast test_aws_utils.py).
"""

from __future__ import annotations

import smtplib
from unittest.mock import MagicMock, patch

from src.core.smtp_utils import check_smtp_connection


def _make_server_mock() -> MagicMock:
    server = MagicMock()
    server.__enter__.return_value = server
    server.__exit__.return_value = False
    return server


def test_check_smtp_connection_starttls_success():
    server = _make_server_mock()
    with patch('smtplib.SMTP', return_value=server) as smtp_ctor:
        ok, msg = check_smtp_connection(
            host='smtp.gmail.com',
            port=587,
            username='galefling@rin-city.com',
            app_password='app-pw',
            recipient='rin@example.com',
        )

    assert ok is True
    assert msg == ''
    smtp_ctor.assert_called_once_with('smtp.gmail.com', 587, timeout=10)
    server.starttls.assert_called_once()
    server.login.assert_called_once_with('galefling@rin-city.com', 'app-pw')
    server.send_message.assert_called_once()
    sent_message = server.send_message.call_args[0][0]
    assert sent_message['To'] == 'rin@example.com'
    assert sent_message['From'] == 'galefling@rin-city.com'


def test_check_smtp_connection_implicit_tls_on_port_465():
    server = _make_server_mock()
    with patch('smtplib.SMTP_SSL', return_value=server) as smtp_ssl_ctor:
        ok, _ = check_smtp_connection(
            host='smtp.gmail.com',
            port=465,
            username='galefling@rin-city.com',
            app_password='app-pw',
            recipient='rin@example.com',
        )

    assert ok is True
    smtp_ssl_ctor.assert_called_once_with('smtp.gmail.com', 465, timeout=10)
    server.starttls.assert_not_called()
    server.login.assert_called_once_with('galefling@rin-city.com', 'app-pw')


def test_check_smtp_connection_auth_failure():
    server = _make_server_mock()
    server.login.side_effect = smtplib.SMTPAuthenticationError(535, b'bad credentials')
    with patch('smtplib.SMTP', return_value=server):
        ok, msg = check_smtp_connection(
            host='smtp.gmail.com',
            port=587,
            username='galefling@rin-city.com',
            app_password='wrong',
            recipient='rin@example.com',
        )

    assert ok is False
    assert 'Authentication failed' in msg
    server.send_message.assert_not_called()


def test_check_smtp_connection_connect_failure():
    with patch('smtplib.SMTP', side_effect=OSError('Connection refused')):
        ok, msg = check_smtp_connection(
            host='smtp.gmail.com',
            port=587,
            username='galefling@rin-city.com',
            app_password='app-pw',
            recipient='rin@example.com',
        )

    assert ok is False
    assert 'Could not connect' in msg


def test_check_smtp_connection_timeout():
    with patch('smtplib.SMTP', side_effect=TimeoutError('timed out')):
        ok, msg = check_smtp_connection(
            host='smtp.gmail.com',
            port=587,
            username='galefling@rin-city.com',
            app_password='app-pw',
            recipient='rin@example.com',
        )

    assert ok is False
    assert 'timed out' in msg
