"""Upload logs and screenshots to the remote endpoint."""

import base64
import getpass
import socket
from datetime import UTC, datetime

import requests

from src.core.config_manager import ConfigManager
from src.core.logger import get_current_log_path, get_logger
from src.core.video_processor import get_ffmpeg_version
from src.utils.constants import APP_VERSION
from src.utils.helpers import OsInfo, get_installation_id, get_logs_dir, get_os_info


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
        os_info = get_os_info()
        ffmpeg_version = get_ffmpeg_version()

        if not self._config.log_upload_enabled:
            return (
                False,
                'Log upload is disabled in settings.',
                self._format_error_details(
                    'LOG-DISABLED',
                    endpoint,
                    'Log upload disabled in settings.',
                    installation_id=installation_id,
                    hostname=hostname,
                    username=username,
                    os_info=os_info,
                    ffmpeg_version=ffmpeg_version,
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
                    installation_id=installation_id,
                    hostname=hostname,
                    username=username,
                    os_info=os_info,
                    ffmpeg_version=ffmpeg_version,
                ),
            )

        try:
            log_files = self._collect_log_files()
            screenshots = self._collect_screenshots()

            payload = {
                'app_version': APP_VERSION,
                'error_code': error_code or 'MANUAL',
                'user_id': installation_id,
                'user_notes': user_notes.strip(),
                'hostname': hostname,
                'username': username,
                'os_version': os_info.get('version', ''),
                'os_platform': os_info.get('platform', ''),
                'ffmpeg_version': ffmpeg_version,
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
                    installation_id=installation_id,
                    hostname=hostname,
                    username=username,
                    os_info=os_info,
                    ffmpeg_version=ffmpeg_version,
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
                    installation_id=installation_id,
                    hostname=hostname,
                    username=username,
                    os_info=os_info,
                    ffmpeg_version=ffmpeg_version,
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
                    installation_id=installation_id,
                    hostname=hostname,
                    username=username,
                    os_info=os_info,
                    ffmpeg_version=ffmpeg_version,
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
                    installation_id=installation_id,
                    hostname=hostname,
                    username=username,
                    os_info=os_info,
                    ffmpeg_version=ffmpeg_version,
                    exception=e,
                ),
            )

    def _format_error_details(
        self,
        error_code: str,
        endpoint: str,
        message: str,
        installation_id: str,
        hostname: str,
        username: str,
        os_info: OsInfo,
        ffmpeg_version: str,
        response_text: str | None = None,
        exception: Exception | None = None,
    ) -> str:
        lines = [
            f'Error Code: {error_code}',
            f'App Version: {APP_VERSION}',
            f'Timestamp (UTC): {datetime.now(UTC).isoformat()}',
            f'Endpoint: {endpoint}',
            f'Installation ID: {installation_id}',
            f'Hostname: {hostname}',
            f'Username: {username}',
            f'OS Platform: {os_info.get("platform", "")}',
            f'FFmpeg Version: {ffmpeg_version}',
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
        log_files: list[dict[str, str]] = []
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
        fatal_log = logs_dir / 'fatal_errors.log'
        if fatal_log.exists():
            content = fatal_log.read_bytes()
            log_files.append(
                {
                    'filename': fatal_log.name,
                    'content': base64.b64encode(content).decode('ascii'),
                }
            )
        crash_logs = sorted(logs_dir.glob('crash_*.log'), reverse=True)
        for crash_log in crash_logs[:3]:
            content = crash_log.read_bytes()
            log_files.append(
                {
                    'filename': crash_log.name,
                    'content': base64.b64encode(content).decode('ascii'),
                }
            )
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
        screenshots: list[dict[str, str]] = []
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
