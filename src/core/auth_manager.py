"""Credential storage and retrieval.

Loads auth from JSON files. In production on Windows, also uses keyring
for secure storage. Falls back to file-based auth in dev or on non-Windows.
"""

import json
import sys
from pathlib import Path
from typing import Any

from src.core.logger import get_logger
from src.utils.helpers import get_auth_dir


class AuthManager:
    """Manage platform credentials."""

    def __init__(self):
        self._auth_dir = get_auth_dir()
        self._dev_auth_dir = self._find_dev_auth_dir()

    def _find_dev_auth_dir(self) -> Path | None:
        """Find auth files next to the executable / source for dev mode."""
        if getattr(sys, 'frozen', False):
            candidate = Path(sys.executable).parent
        else:
            candidate = Path(__file__).resolve().parent.parent.parent
        if (candidate / 'twitter_auth.json').exists() or \
           (candidate / 'bluesky_auth.json').exists():
            return candidate
        return None

    def _load_json(self, filename: str) -> dict[str, Any] | None:
        """Load an auth JSON file, checking dev dir first, then appdata."""
        for directory in filter(None, [self._dev_auth_dir, self._auth_dir]):
            path = directory / filename
            if path.exists():
                try:
                    with open(path) as f:
                        return json.load(f)
                except (OSError, json.JSONDecodeError) as e:
                    get_logger().warning(f"Failed to load {path}: {e}")
        return None

    def _save_json(self, filename: str, data: dict[str, Any]):
        """Save auth data to appdata directory."""
        path = self._auth_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f, indent=4)

    def get_twitter_auth(self) -> dict[str, str] | None:
        """Return Twitter OAuth credentials or None."""
        data = self._load_json('twitter_auth.json')
        if data and all(k in data for k in
                        ('api_key', 'api_secret', 'access_token', 'access_token_secret')):
            return data
        return None

    def save_twitter_auth(self, api_key: str, api_secret: str,
                          access_token: str, access_token_secret: str):
        self._save_json('twitter_auth.json', {
            'api_key': api_key,
            'api_secret': api_secret,
            'access_token': access_token,
            'access_token_secret': access_token_secret,
        })

    def get_bluesky_auth(self) -> dict[str, str] | None:
        """Return Bluesky credentials or None."""
        data = self._load_json('bluesky_auth.json')
        if data and all(k in data for k in ('identifier', 'app_password')):
            return data
        return None

    def save_bluesky_auth(self, identifier: str, app_password: str,
                          service: str = 'https://bsky.social'):
        self._save_json('bluesky_auth.json', {
            'identifier': identifier,
            'app_password': app_password,
            'service': service,
        })

    def has_twitter_auth(self) -> bool:
        return self.get_twitter_auth() is not None

    def has_bluesky_auth(self) -> bool:
        return self.get_bluesky_auth() is not None
