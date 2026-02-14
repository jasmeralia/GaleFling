"""Upload logs and screenshots to the remote endpoint."""

import base64
import getpass
import socket
from datetime import UTC, datetime

import requests

from src.core.config_manager import ConfigManager
from src.core.logger import get_current_log_path, get_logger
from src.utils.constants import APP_VERSION
from src.utils.helpers import get_installation_id, get_logs_dir


class LogUploader:
    """Upload log bundles to the backend endpoint."""

    def __init__(self, config: ConfigManager):
        self._config = config

    def upload(
        self,
        user_notes: str,
        error_code: str | None = None,
        platform: str | None = None,
    ) -> tuple[bool, str, str]:
        """Upload current logs and screenshots.

        Returns (success, message).
        """
        logger = get_logger()
        endpoint = self._config.log_upload_endpoint
        installation_id = get_installation_id()
        hostname = socket.gethostname()
        username = getpass.getuser()
        platform_name = platform or 'Unknown'

        if not self._config.log_upload_enabled:
            return (
                False,
                'Log upload is disabled in settings.',
                self._format_error_details(
                    'LOG-DISABLED',
                    endpoint,
                    'Log upload disabled in settings.',
                    platform_name=platform_name,
                    installation_id=installation_id,
                    hostname=hostname,
                    username=username,
                ),
            )
        if not user_notes.strip():
            return (
                False,
                'Please describe what you were doing before sending logs.',
                self._format_error_details(
                    'LOG-NOTES-MISSING',
                    endpoint,
                    'User notes are required before uploading logs.',
                    platform_name=platform_name,
                    installation_id=installation_id,
                    hostname=hostname,
                    username=username,
                ),
            )

        try:
            log_files = self._collect_log_files()
            screenshots = self._collect_screenshots()

            payload = {
                'app_version': APP_VERSION,
                'error_code': error_code or 'MANUAL',
                'platform': platform_name,
                'user_id': installation_id,
                'user_notes': user_notes.strip(),
                'log_files': log_files,
                'screenshots': screenshots,
            }

            response = requests.post(
                endpoint,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                upload_id = data.get('upload_id', 'unknown')
                logger.info(f'Logs uploaded successfully. ID: {upload_id}')
                return True, f'Logs sent successfully! (ID: {upload_id})', ''
            logger.error(f'Log upload failed: HTTP {response.status_code}')
            error_code = f'LOG-HTTP-{response.status_code}'
            return (
                False,
                f'Upload failed (HTTP {response.status_code}).',
                self._format_error_details(
                    error_code,
                    endpoint,
                    f'HTTP {response.status_code} response.',
                    platform_name=platform_name,
                    installation_id=installation_id,
                    hostname=hostname,
                    username=username,
                    response_text=response.text,
                ),
            )

        except requests.Timeout as exc:
            logger.error('Log upload timed out')
            return (
                False,
                'Upload timed out.',
                self._format_error_details(
                    'LOG-TIMEOUT',
                    endpoint,
                    'Request timed out while uploading logs.',
                    platform_name=platform_name,
                    installation_id=installation_id,
                    hostname=hostname,
                    username=username,
                    exception=exc,
                ),
            )
        except requests.ConnectionError as exc:
            logger.error('Log upload connection error')
            return (
                False,
                'Could not connect to the log server.',
                self._format_error_details(
                    'LOG-CONNECTION',
                    endpoint,
                    'Connection error while uploading logs.',
                    platform_name=platform_name,
                    installation_id=installation_id,
                    hostname=hostname,
                    username=username,
                    exception=exc,
                ),
            )
        except Exception as e:
            logger.error(f'Log upload error: {e}')
            return (
                False,
                'Upload failed due to an unexpected error.',
                self._format_error_details(
                    'LOG-EXCEPTION',
                    endpoint,
                    str(e),
                    platform_name=platform_name,
                    installation_id=installation_id,
                    hostname=hostname,
                    username=username,
                    exception=e,
                ),
            )

    def _format_error_details(
        self,
        error_code: str,
        endpoint: str,
        message: str,
        platform_name: str,
        installation_id: str,
        hostname: str,
        username: str,
        response_text: str | None = None,
        exception: Exception | None = None,
    ) -> str:
        lines = [
            f'Error Code: {error_code}',
            f'App Version: {APP_VERSION}',
            f'Timestamp (UTC): {datetime.now(UTC).isoformat()}',
            f'Endpoint: {endpoint}',
            f'Platform: {platform_name}',
            f'Installation ID: {installation_id}',
            f'Hostname: {hostname}',
            f'Username: {username}',
            f'Message: {message}',
        ]
        if exception is not None:
            lines.append(f'Exception Type: {type(exception).__name__}')
            lines.append(f'Exception: {exception}')
        if response_text:
            lines.append('Response:')
            lines.append(response_text)
        return '\n'.join(lines)

    def _collect_log_files(self) -> list[dict]:
        """Collect and base64-encode recent log files."""
        log_files = []
        current_log = get_current_log_path()
        if current_log and current_log.exists():
            content = current_log.read_bytes()
            log_files.append(
                {
                    'filename': current_log.name,
                    'content': base64.b64encode(content).decode('ascii'),
                }
            )

        # Also include the most recent other log file if present
        logs_dir = get_logs_dir()
        other_logs = sorted(logs_dir.glob('app_*.log'), reverse=True)
        for log_path in other_logs[:2]:
            if log_path != current_log:
                content = log_path.read_bytes()
                log_files.append(
                    {
                        'filename': log_path.name,
                        'content': base64.b64encode(content).decode('ascii'),
                    }
                )

        return log_files

    def _collect_screenshots(self) -> list[dict]:
        """Collect and base64-encode recent screenshots."""
        screenshots = []
        ss_dir = get_logs_dir() / 'screenshots'
        if not ss_dir.exists():
            return screenshots

        recent = sorted(ss_dir.glob('error_*.png'), reverse=True)[:5]
        for ss_path in recent:
            content = ss_path.read_bytes()
            screenshots.append(
                {
                    'filename': ss_path.name,
                    'content': base64.b64encode(content).decode('ascii'),
                }
            )

        return screenshots
