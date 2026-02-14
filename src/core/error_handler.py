"""Error code system with user-friendly messages."""


from src.core.logger import log_error
from src.utils.constants import ERROR_CODES, USER_FRIENDLY_MESSAGES, PostResult


def get_error_message(error_code: str) -> str:
    """Return the technical error message for a code."""
    return ERROR_CODES.get(error_code, f'Unknown error: {error_code}')


def get_user_message(error_code: str) -> str:
    """Return a user-friendly message for an error code."""
    return USER_FRIENDLY_MESSAGES.get(
        error_code,
        "Something went wrong. Please send your logs to Jas for help."
    )


def create_error_result(error_code: str, platform: str,
                        exception: Exception | None = None,
                        details: dict | None = None) -> PostResult:
    """Create a PostResult for a failed operation, logging the error."""
    log_error(error_code, platform, details=details, exception=exception)

    return PostResult(
        success=False,
        platform=platform,
        error_code=error_code,
        error_message=get_user_message(error_code),
        raw_response=details,
    )


def format_error_details(result: PostResult) -> str:
    """Format error details for clipboard copy."""
    from src.core.logger import get_current_log_path
    from src.utils.constants import APP_VERSION

    lines = [
        f"Platform: {result.platform}",
        f"Error Code: {result.error_code}",
        f"Timestamp: {result.timestamp}",
        f"Message: {result.error_message}",
        "",
    ]

    if result.raw_response:
        lines.append("Request Details:")
        for k, v in result.raw_response.items():
            lines.append(f"  {k}: {v}")
        lines.append("")

    lines.append(f"Application: GalePost v{APP_VERSION}")
    log_path = get_current_log_path()
    if log_path:
        lines.append(f"Log File: {log_path.name}")

    return "\n".join(lines)
