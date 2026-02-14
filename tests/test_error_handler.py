"""Tests for the error handling system."""

from src.core.error_handler import (
    create_error_result,
    format_error_details,
    get_error_message,
    get_user_message,
)
from src.utils.constants import ERROR_CODES, USER_FRIENDLY_MESSAGES, PostResult


class TestErrorCodes:
    def test_all_codes_have_messages(self):
        for code in ERROR_CODES:
            assert code in USER_FRIENDLY_MESSAGES, \
                f"Error code {code} missing user-friendly message"

    def test_all_friendly_messages_have_codes(self):
        for code in USER_FRIENDLY_MESSAGES:
            assert code in ERROR_CODES, \
                f"User message for {code} has no matching error code"

    def test_get_error_message_known(self):
        msg = get_error_message('TW-AUTH-INVALID')
        assert 'Twitter' in msg
        assert 'invalid' in msg.lower()

    def test_get_error_message_unknown(self):
        msg = get_error_message('FAKE-CODE')
        assert 'FAKE-CODE' in msg

    def test_get_user_message_known(self):
        msg = get_user_message('TW-RATE-LIMIT')
        assert '15 minutes' in msg

    def test_get_user_message_unknown(self):
        msg = get_user_message('FAKE-CODE')
        assert 'Jas' in msg


class TestCreateErrorResult:
    def test_creates_failed_result(self):
        result = create_error_result('POST-FAILED', 'Twitter')
        assert not result.success
        assert result.platform == 'Twitter'
        assert result.error_code == 'POST-FAILED'
        assert result.error_message is not None

    def test_includes_exception_info(self):
        try:
            raise ValueError("test error")
        except ValueError as e:
            result = create_error_result('SYS-UNKNOWN', 'Bluesky', exception=e)
        assert not result.success
        assert result.error_code == 'SYS-UNKNOWN'


class TestFormatErrorDetails:
    def test_format_includes_platform(self):
        result = PostResult(
            success=False,
            platform='Twitter',
            error_code='TW-AUTH-EXPIRED',
            error_message='Token expired',
        )
        text = format_error_details(result)
        assert 'Twitter' in text
        assert 'TW-AUTH-EXPIRED' in text

    def test_format_includes_version(self):
        result = PostResult(
            success=False,
            platform='Bluesky',
            error_code='POST-FAILED',
            error_message='Failed',
        )
        text = format_error_details(result)
        assert 'GalePost' in text
