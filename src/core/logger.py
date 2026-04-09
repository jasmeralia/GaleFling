"""File logging with screenshot capture on errors."""

import json
import logging
import re
import traceback
from datetime import datetime
from pathlib import Path

from src.utils.helpers import get_logs_dir

_logger: logging.Logger | None = None
_log_file_path: Path | None = None
_debug_mode: bool = False

# Patterns that may appear in raw API response bodies or exception messages.
# Each tuple is (compiled_regex, replacement).
_REDACT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # URL query param: access_token=EAA... or access_token_secret=...
    (re.compile(r'(?i)(access_token(?:_secret)?=)[^\s&"\']{6,}'), r'\1***'),
    # JSON field: "access_token": "EAA...", "app_password": "xxx"
    (
        re.compile(
            r'(?i)("(?:access_token|access_token_secret|app_password|api_key|api_secret|'
            r'page_access_token)":\s*")[^"]{6,}(")'
        ),
        r'\1***\2',
    ),
    # HTTP Bearer token
    (re.compile(r'(?i)(Bearer\s+)[A-Za-z0-9._\-]{6,}'), r'\1***'),
]


def redact_credentials(text: object) -> str:
    """Redact common credential patterns from *text* before logging.

    Accepts any object; non-strings are converted via ``str()`` first.
    Applies regex substitutions covering access tokens, API keys, app
    passwords, and Bearer tokens embedded in API response bodies or
    exception messages.
    """
    if not isinstance(text, str):
        text = str(text)
    for pattern, replacement in _REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def setup_logging(debug_mode: bool = False) -> logging.Logger:
    """Initialize logging for the current session."""
    global _logger, _log_file_path, _debug_mode

    _debug_mode = debug_mode
    logs_dir = get_logs_dir()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    _log_file_path = logs_dir / f'app_{timestamp}.log'

    _logger = logging.getLogger('GaleFling')
    _logger.setLevel(logging.DEBUG if debug_mode else logging.INFO)
    _logger.handlers.clear()

    file_handler = logging.FileHandler(_log_file_path, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_fmt)
    _logger.addHandler(file_handler)

    if debug_mode:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(file_fmt)
        _logger.addHandler(console_handler)

    return _logger


def get_logger() -> logging.Logger:
    """Return the application logger, initializing if needed."""
    global _logger
    if _logger is None:
        _logger = setup_logging()
    return _logger


def get_current_log_path() -> Path | None:
    """Return the path to the current session's log file."""
    return _log_file_path


def reset_log_file() -> logging.Logger:
    """Close current log handlers and start a fresh log file."""
    global _logger, _log_file_path
    if _logger is not None:
        for handler in list(_logger.handlers):
            handler.close()
            _logger.removeHandler(handler)
    _logger = None
    _log_file_path = None
    return setup_logging(_debug_mode)


def log_error(
    error_code: str, platform: str, details: dict | None = None, exception: Exception | None = None
):
    """Log a structured error entry."""
    logger = get_logger()

    error_entry = {
        'error_code': error_code,
        'platform': platform,
        'timestamp': datetime.now().isoformat(),
        'details': details or {},
    }

    if exception:
        error_entry['exception'] = {
            'type': type(exception).__name__,
            'message': redact_credentials(str(exception)),
            'traceback': redact_credentials(traceback.format_exc()),
        }

    logger.error(f'Error {error_code} on {platform}\n{json.dumps(error_entry, indent=2)}')

    capture_screenshot(error_code)


def capture_screenshot(error_code: str):
    """Capture a screenshot of the current application state."""
    try:
        from typing import cast

        from PyQt6.QtWidgets import QApplication

        app = cast(QApplication | None, QApplication.instance())
        if app is None:
            return

        screen = app.primaryScreen()
        if screen is None:
            return

        # Find the active window for the screenshot
        active_window = app.activeWindow()
        if active_window is not None:
            screenshot = screen.grabWindow(active_window.winId())  # type: ignore[arg-type]
        else:
            screenshot = screen.grabWindow(0)  # type: ignore[arg-type]

        logs_dir = get_logs_dir()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_path = logs_dir / 'screenshots' / f'error_{timestamp}.png'
        screenshot.save(str(screenshot_path), 'PNG')

        get_logger().info(f'Screenshot saved: {screenshot_path}')
    except Exception as e:
        get_logger().warning(f'Failed to capture screenshot: {e}')
