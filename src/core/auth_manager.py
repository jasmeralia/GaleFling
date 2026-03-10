"""Credential storage and retrieval.

Loads auth from JSON files. In production on Windows, also uses keyring
for secure storage. Falls back to file-based auth in dev or on non-Windows.

Phase 1: Supports account_id-based multi-account storage via accounts_config.json
alongside the original per-platform JSON files for backward compatibility.
"""

import json
import sys
from pathlib import Path
from typing import Any

from src.core.logger import get_logger
from src.utils.constants import AccountConfig
from src.utils.helpers import get_app_data_dir, get_auth_dir


class AuthManager:
    """Manage platform credentials."""

    def __init__(self) -> None:
        self._auth_dir = get_auth_dir()
        self._dev_auth_dir = self._find_dev_auth_dir()
        self._accounts: list[AccountConfig] = []
        self._accounts_path = get_app_data_dir() / 'accounts_config.json'
        self._load_accounts()

    def _find_dev_auth_dir(self) -> Path | None:
        """Find auth files next to the executable / source for dev mode."""
        if getattr(sys, 'frozen', False):
            candidate = Path(sys.executable).parent
        else:
            candidate = Path(__file__).resolve().parent.parent.parent
        if (candidate / 'twitter_auth.json').exists() or (candidate / 'bluesky_auth.json').exists():
            return candidate
        return None

    # ── Account config persistence ──────────────────────────────────

    def _load_accounts(self):
        """Load accounts_config.json, migrating from Phase 0 format if needed."""
        if self._accounts_path.exists():
            try:
                with open(self._accounts_path) as f:
                    data = json.load(f)
                self._accounts = [
                    AccountConfig(
                        platform_id=a['platform_id'],
                        account_id=a['account_id'],
                        profile_name=a.get('profile_name', ''),
                        enabled=a.get('enabled', True),
                    )
                    for a in data.get('accounts', [])
                ]
                return
            except (OSError, json.JSONDecodeError, KeyError) as e:
                get_logger().warning(f'Failed to load accounts config: {e}')

        # Auto-migrate from Phase 0 auth files
        self._migrate_from_phase0()

    def _migrate_from_phase0(self):
        """Create account configs from existing Phase 0 auth JSON files."""
        migrated = []

        tw_data = self._load_json('twitter_auth.json')
        if tw_data and all(
            k in tw_data for k in ('api_key', 'api_secret', 'access_token', 'access_token_secret')
        ):
            migrated.append(
                AccountConfig(
                    platform_id='twitter',
                    account_id='twitter_1',
                    profile_name=tw_data.get('username', ''),
                )
            )

        bs_data = self._load_json('bluesky_auth.json')
        if bs_data and all(k in bs_data for k in ('identifier', 'app_password')):
            migrated.append(
                AccountConfig(
                    platform_id='bluesky',
                    account_id='bluesky_1',
                    profile_name=bs_data.get('identifier', ''),
                )
            )

        bs_alt_data = self._load_json('bluesky_auth_alt.json')
        if bs_alt_data and all(k in bs_alt_data for k in ('identifier', 'app_password')):
            migrated.append(
                AccountConfig(
                    platform_id='bluesky',
                    account_id='bluesky_alt',
                    profile_name=bs_alt_data.get('identifier', ''),
                )
            )

        self._accounts = migrated
        if migrated:
            self._save_accounts()

    def _save_accounts(self):
        """Persist accounts_config.json."""
        data = {
            'accounts': [
                {
                    'platform_id': a.platform_id,
                    'account_id': a.account_id,
                    'profile_name': a.profile_name,
                    'enabled': a.enabled,
                }
                for a in self._accounts
            ]
        }
        self._accounts_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._accounts_path, 'w') as f:
            json.dump(data, f, indent=4)

    def get_accounts(self) -> list[AccountConfig]:
        """Return all configured accounts."""
        return list(self._accounts)

    def get_accounts_for_platform(self, platform_id: str) -> list[AccountConfig]:
        """Return accounts for a specific platform."""
        return [a for a in self._accounts if a.platform_id == platform_id]

    def get_account(self, account_id: str) -> AccountConfig | None:
        """Return a specific account by its ID."""
        for a in self._accounts:
            if a.account_id == account_id:
                return a
        return None

    def add_account(self, account: AccountConfig):
        """Add a new account and persist."""
        existing = self.get_account(account.account_id)
        if existing:
            existing.platform_id = account.platform_id
            existing.profile_name = account.profile_name
            existing.enabled = account.enabled
        else:
            self._accounts.append(account)
        self._save_accounts()

    def remove_account(self, account_id: str):
        """Remove an account by ID and persist."""
        self._accounts = [a for a in self._accounts if a.account_id != account_id]
        self._save_accounts()

    def set_account_enabled(self, account_id: str, enabled: bool) -> bool:
        """Set an account's enabled flag and persist.

        Returns True when the account exists (whether changed or already in the
        requested state), otherwise False.
        """
        account = self.get_account(account_id)
        if not account:
            return False
        if account.enabled == enabled:
            return True
        account.enabled = enabled
        self._save_accounts()
        return True

    # ── Account-based credential storage ────────────────────────────

    def get_account_credentials(self, account_id: str) -> dict[str, Any] | None:
        """Load credentials for an account from its auth JSON file."""
        return self._load_json(f'{account_id}_auth.json')

    def save_account_credentials(self, account_id: str, credentials: dict[str, Any]):
        """Save credentials for an account to its auth JSON file."""
        self._save_json(f'{account_id}_auth.json', credentials)

    def clear_account_credentials(self, account_id: str):
        """Remove credentials file for an account."""
        path = self._auth_dir / f'{account_id}_auth.json'
        if path.exists():
            path.unlink()

    # ── Twitter app credentials (shared across all Twitter accounts) ─

    def get_twitter_app_credentials(self) -> dict[str, str] | None:
        """Return the shared Twitter developer app credentials."""
        data = self._load_json('twitter_app_auth.json')
        if data and all(k in data for k in ('api_key', 'api_secret')):
            return data
        # Fall back to Phase 0 twitter_auth.json which has the app creds embedded
        data = self._load_json('twitter_auth.json')
        if data and all(k in data for k in ('api_key', 'api_secret')):
            return {'api_key': data['api_key'], 'api_secret': data['api_secret']}
        return None

    def save_twitter_app_credentials(self, api_key: str, api_secret: str):
        """Save shared Twitter developer app credentials."""
        self._save_json('twitter_app_auth.json', {'api_key': api_key, 'api_secret': api_secret})

    # ── Low-level JSON I/O ──────────────────────────────────────────

    def _load_json(self, filename: str) -> dict[str, Any] | None:
        """Load an auth JSON file, checking dev dir first, then appdata."""
        for directory in filter(None, [self._dev_auth_dir, self._auth_dir]):
            path = directory / filename
            if path.exists():
                try:
                    with open(path) as f:
                        return json.load(f)
                except (OSError, json.JSONDecodeError) as e:
                    get_logger().warning(f'Failed to load {path}: {e}')
        return None

    def _save_json(self, filename: str, data: dict[str, Any]):
        """Save auth data to appdata directory."""
        path = self._auth_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f, indent=4)

    # ── Phase 0 backward-compatible methods ─────────────────────────
    # These are kept for existing GUI code that hasn't been migrated yet.

    def get_twitter_auth(self) -> dict[str, str] | None:
        """Return Twitter OAuth credentials or None."""
        # Try account-based first
        creds = self.get_account_credentials('twitter_1')
        if creds and all(k in creds for k in ('access_token', 'access_token_secret')):
            # Merge in app credentials
            app_creds = self.get_twitter_app_credentials()
            if app_creds:
                return {**app_creds, **creds}
        # Fall back to Phase 0 format
        data = self._load_json('twitter_auth.json')
        if data and all(
            k in data for k in ('api_key', 'api_secret', 'access_token', 'access_token_secret')
        ):
            return data
        return None

    def save_twitter_auth(
        self,
        api_key: str,
        api_secret: str,
        access_token: str,
        access_token_secret: str,
        username: str | None = None,
    ):
        payload: dict[str, Any] = {
            'api_key': api_key,
            'api_secret': api_secret,
            'access_token': access_token,
            'access_token_secret': access_token_secret,
        }
        if username:
            payload['username'] = username
        self._save_json(
            'twitter_auth.json',
            payload,
        )

    def clear_twitter_auth(self):
        path = self._auth_dir / 'twitter_auth.json'
        if path.exists():
            path.unlink()

    def get_bluesky_auth(self) -> dict[str, str] | None:
        """Return Bluesky credentials or None."""
        data = self._load_json('bluesky_auth.json')
        if data and all(k in data for k in ('identifier', 'app_password')):
            return data
        return None

    def get_bluesky_auth_alt(self) -> dict[str, str] | None:
        """Return secondary Bluesky credentials or None."""
        data = self._load_json('bluesky_auth_alt.json')
        if data and all(k in data for k in ('identifier', 'app_password')):
            return data
        return None

    def save_bluesky_auth(
        self, identifier: str, app_password: str, service: str = 'https://bsky.social'
    ):
        self._save_json(
            'bluesky_auth.json',
            {
                'identifier': identifier,
                'app_password': app_password,
                'service': service,
            },
        )

    def save_bluesky_auth_alt(
        self, identifier: str, app_password: str, service: str = 'https://bsky.social'
    ):
        self._save_json(
            'bluesky_auth_alt.json',
            {
                'identifier': identifier,
                'app_password': app_password,
                'service': service,
            },
        )

    def clear_bluesky_auth(self):
        path = self._auth_dir / 'bluesky_auth.json'
        if path.exists():
            path.unlink()

    def clear_bluesky_auth_alt(self):
        path = self._auth_dir / 'bluesky_auth_alt.json'
        if path.exists():
            path.unlink()

    def has_twitter_auth(self) -> bool:
        data = self.get_twitter_auth()
        if not data:
            return False
        return bool(data.get('username'))

    def has_bluesky_auth(self) -> bool:
        data = self.get_bluesky_auth()
        if not data:
            return False
        return bool(data.get('identifier'))

    def has_bluesky_auth_alt(self) -> bool:
        data = self.get_bluesky_auth_alt()
        if not data:
            return False
        return bool(data.get('identifier'))
