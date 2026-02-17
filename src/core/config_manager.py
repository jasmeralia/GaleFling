"""Application settings persistence."""

import json
from typing import Any

from src.utils.constants import APP_VERSION, LOG_UPLOAD_ENDPOINT
from src.utils.helpers import get_app_data_dir

DEFAULT_CONFIG = {
    'version': APP_VERSION,
    'last_selected_platforms': ['twitter', 'bluesky'],
    'debug_mode': False,
    'auto_check_updates': True,
    'theme_mode': 'system',
    'log_upload_endpoint': LOG_UPLOAD_ENDPOINT,
    'log_upload_enabled': True,
    'window_geometry': {
        'width': 900,
        'height': 700,
        'x': 100,
        'y': 100,
    },
    'last_image_directory': '',
    'auto_save_draft': True,
    'draft_auto_save_interval_seconds': 30,
}


class ConfigManager:
    """Manage application configuration with JSON persistence."""

    def __init__(self):
        self._config_path = get_app_data_dir() / 'app_config.json'
        self._config: dict[str, Any] = {}
        self.load()

    def load(self):
        """Load config from disk, falling back to defaults."""
        if self._config_path.exists():
            try:
                with open(self._config_path) as f:
                    self._config = json.load(f)
            except (OSError, json.JSONDecodeError):
                self._config = {}

        # Merge defaults for any missing keys
        for key, value in DEFAULT_CONFIG.items():
            if key not in self._config:
                self._config[key] = value

    def save(self):
        """Persist config to disk."""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._config_path, 'w') as f:
            json.dump(self._config, f, indent=4)

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def set(self, key: str, value: Any):
        self._config[key] = value
        self.save()

    @property
    def debug_mode(self) -> bool:
        return self._config.get('debug_mode', False)

    @debug_mode.setter
    def debug_mode(self, value: bool):
        self.set('debug_mode', value)

    @property
    def last_selected_platforms(self):
        return self._config.get('last_selected_platforms', ['twitter', 'bluesky'])

    @last_selected_platforms.setter
    def last_selected_platforms(self, value):
        self.set('last_selected_platforms', value)

    @property
    def window_geometry(self) -> dict:
        return self._config.get('window_geometry', DEFAULT_CONFIG['window_geometry'])

    @window_geometry.setter
    def window_geometry(self, value: dict):
        self.set('window_geometry', value)

    @property
    def last_image_directory(self) -> str:
        return self._config.get('last_image_directory', '')

    @last_image_directory.setter
    def last_image_directory(self, value: str):
        self.set('last_image_directory', value)

    @property
    def log_upload_endpoint(self) -> str:
        return self._config.get('log_upload_endpoint', LOG_UPLOAD_ENDPOINT)

    @property
    def log_upload_enabled(self) -> bool:
        return self._config.get('log_upload_enabled', True)

    @property
    def auto_check_updates(self) -> bool:
        return self._config.get('auto_check_updates', True)

    @property
    def theme_mode(self) -> str:
        return self._config.get('theme_mode', 'system')

    @theme_mode.setter
    def theme_mode(self, value: str):
        self.set('theme_mode', value)

    @property
    def auto_save_draft(self) -> bool:
        return self._config.get('auto_save_draft', True)

    @property
    def draft_interval(self) -> int:
        return self._config.get('draft_auto_save_interval_seconds', 30)
