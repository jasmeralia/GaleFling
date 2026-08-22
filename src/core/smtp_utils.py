"""SMTP utility helpers for GaleFling.

smtplib/email are standard library, so unlike aws_utils.py there is no lazy
optional-dependency import to guard.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

_TEST_TIMEOUT_SECONDS = 10


def send_email(
    *,
    host: str,
    port: int,
    username: str,
    app_password: str,
    recipient: str,
    subject: str,
    body: str,
) -> tuple[bool, str]:
    """Send one plain-text notification email."""
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = username
    message['To'] = recipient
    message.set_content(body)
    try:
        server: smtplib.SMTP
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=_TEST_TIMEOUT_SECONDS)
        else:
            server = smtplib.SMTP(host, port, timeout=_TEST_TIMEOUT_SECONDS)
        with server:
            if port != 465:
                server.starttls()
            server.login(username, app_password)
            server.send_message(message)
        return True, ''
    except smtplib.SMTPAuthenticationError as exc:
        return False, f'Authentication failed: {exc}'
    except smtplib.SMTPException as exc:
        return False, f'SMTP error: {exc}'
    except TimeoutError:
        return False, f'Connection to {host}:{port} timed out.'
    except OSError as exc:
        return False, f'Could not connect to {host}:{port}: {exc}'
    except Exception as exc:  # noqa: BLE001
        return False, f'Unexpected error: {exc}'


def check_smtp_connection(
    host: str,
    port: int,
    username: str,
    app_password: str,
    recipient: str,
) -> tuple[bool, str]:
    """Log in and send a real test email to ``recipient``.

    Always sends — this proves the full send path (auth + delivery), not just
    that the login handshake succeeds, mirroring ``check_s3_connection``'s
    real (tiny) probe write rather than a permissions-only check.

    Uses implicit TLS (``SMTP_SSL``) for port 465, STARTTLS otherwise — this
    covers both connection styles Gmail (and most providers) document without
    requiring the caller to specify which to use.

    Returns ``(True, '')`` on success or ``(False, error_message)`` on failure.
    """
    return send_email(
        host=host,
        port=port,
        username=username,
        app_password=app_password,
        recipient=recipient,
        subject='GaleFling SMTP test',
        body=(
            'This is a test message from GaleFling to confirm its email notification '
            'settings are working. No action is needed.'
        ),
    )
