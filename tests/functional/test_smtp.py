"""Functional tests for SMTP notification credentials — see docs/EMAIL_NOTIFICATIONS.md.

Exercises src.core.smtp_utils.check_smtp_connection() against a real mailbox,
mirroring how the Settings > Advanced > Email Notifications > Test Connection
button behaves. Unlike the social platforms, a delivered test email is not
public content, so the mutating_post_tag()/neutral-content conventions
(AGENTS.md rule 15) do not apply — it only ever reaches an inbox the
operator configured in tests/functional/.env.
"""

from __future__ import annotations

import pytest

from src.core.smtp_utils import check_smtp_connection


@pytest.mark.functional
@pytest.mark.non_mutating
class TestSMTPConnectionAuth:
    """Auth-only checks that never reach send_message() — safe to run unattended."""

    def test_bad_app_password_rejected_before_send(self, smtp_credentials):
        ok, msg = check_smtp_connection(
            host=smtp_credentials['host'],
            port=smtp_credentials['port'],
            username=smtp_credentials['username'],
            app_password='not-the-real-app-password',
            recipient=smtp_credentials['recipient'],
        )
        assert not ok
        assert 'auth' in msg.lower() or 'authentication' in msg.lower()

    def test_unreachable_host_reported_cleanly(self, smtp_credentials):
        ok, msg = check_smtp_connection(
            host='smtp.invalid.example',
            port=smtp_credentials['port'],
            username=smtp_credentials['username'],
            app_password=smtp_credentials['app_password'],
            recipient=smtp_credentials['recipient'],
        )
        assert not ok
        assert msg


@pytest.mark.functional
@pytest.mark.mutating
class TestSMTPTestEmail:
    """Real send — delivers one test email per run to the configured recipient."""

    def test_check_smtp_connection_sends_real_email(self, smtp_credentials):
        ok, msg = check_smtp_connection(
            host=smtp_credentials['host'],
            port=smtp_credentials['port'],
            username=smtp_credentials['username'],
            app_password=smtp_credentials['app_password'],
            recipient=smtp_credentials['recipient'],
        )
        assert ok, f'SMTP test email failed: {msg}'
        assert msg == ''
