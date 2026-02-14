"""Upload logs and screenshots to the remote endpoint."""

import base64

import requests

from src.core.config_manager import ConfigManager
from src.core.logger import get_current_log_path, get_logger
from src.utils.constants import APP_VERSION
from src.utils.helpers import get_installation_id, get_logs_dir


class LogUploader:
    """Upload log bundles to the backend endpoint."""

    def __init__(self, config: ConfigManager):
        self._config = config

    def upload(self, error_code: str | None = None,
               platform: str | None = None) -> tuple[bool, str]:
        """Upload current logs and screenshots.

        Returns (success, message).
        """
        logger = get_logger()
        endpoint = self._config.log_upload_endpoint

        if not self._config.log_upload_enabled:
            return False, "Log upload is disabled in settings."

        try:
            log_files = self._collect_log_files()
            screenshots = self._collect_screenshots()

            payload = {
                'app_version': APP_VERSION,
                'error_code': error_code or 'MANUAL',
                'platform': platform or 'Unknown',
                'user_id': get_installation_id(),
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
                logger.info(f"Logs uploaded successfully. ID: {upload_id}")
                return True, f"Logs sent successfully! (ID: {upload_id})"
            else:
                logger.error(f"Log upload failed: HTTP {response.status_code}")
                return False, f"Upload failed (HTTP {response.status_code}). Try again later."

        except requests.Timeout:
            logger.error("Log upload timed out")
            return False, "Upload timed out. Please check your internet connection."
        except requests.ConnectionError:
            logger.error("Log upload connection error")
            return False, "Could not connect to server. Please check your internet."
        except Exception as e:
            logger.error(f"Log upload error: {e}")
            return False, f"Upload failed: {e}"

    def _collect_log_files(self) -> list[dict]:
        """Collect and base64-encode recent log files."""
        log_files = []
        current_log = get_current_log_path()
        if current_log and current_log.exists():
            content = current_log.read_bytes()
            log_files.append({
                'filename': current_log.name,
                'content': base64.b64encode(content).decode('ascii'),
            })

        # Also include the most recent other log file if present
        logs_dir = get_logs_dir()
        other_logs = sorted(logs_dir.glob('app_*.log'), reverse=True)
        for log_path in other_logs[:2]:
            if log_path != current_log:
                content = log_path.read_bytes()
                log_files.append({
                    'filename': log_path.name,
                    'content': base64.b64encode(content).decode('ascii'),
                })

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
            screenshots.append({
                'filename': ss_path.name,
                'content': base64.b64encode(content).decode('ascii'),
            })

        return screenshots
