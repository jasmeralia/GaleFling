"""Token lifecycle management for Meta platform connections.

Tracks expiry for meta_threads and meta_instagram access tokens,
triggers proactive refresh before expiry, and surfaces connection
status (valid / expires_soon / expired / missing) to the rest of
the app.

Facebook Page tokens are not covered by periodic refresh — they are
effectively permanent and are only invalidated by explicit revocation.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime, timedelta

import requests

from src.core.auth_manager import AuthManager
from src.core.logger import get_logger

# Days before expiry at which a token is flagged as "expiring soon".
EXPIRES_SOON_THRESHOLD_DAYS = 7

# Providers whose tokens can be refreshed proactively.
# Facebook Page tokens never expire on their own.
_REFRESHABLE_PROVIDERS = frozenset({'meta_threads', 'meta_instagram'})

_REFRESH_ENDPOINTS: dict[str, str] = {
    'meta_threads': 'https://graph.threads.net/refresh_access_token',
    'meta_instagram': 'https://graph.instagram.com/refresh_access_token',
}
_REFRESH_GRANT_TYPES: dict[str, str] = {
    'meta_threads': 'th_refresh_token',
    'meta_instagram': 'ig_refresh_token',
}


class TokenStatus(enum.Enum):
    """Status of a stored access token."""

    VALID = 'valid'
    EXPIRES_SOON = 'expires_soon'
    EXPIRED = 'expired'
    MISSING = 'missing'


class TokenManager:
    """Check and refresh Meta access tokens.

    Works with the file-based credential store in AuthManager — reads
    the ``expires_at`` field from ``{account_id}_auth.json`` and writes
    updated tokens back to the same file after a successful refresh.
    """

    def __init__(self, auth_manager: AuthManager) -> None:
        self._auth = auth_manager

    # ── Public API ────────────────────────────────────────────────────

    def get_token_status(self, account_id: str) -> TokenStatus:
        """Return the current status of the stored token for *account_id*.

        Returns ``MISSING`` if no credentials are stored or no token field
        is present.  Returns ``EXPIRED`` / ``EXPIRES_SOON`` / ``VALID``
        based on the ``expires_at`` timestamp.  Tokens with no
        ``expires_at`` (e.g. Facebook Page long-lived tokens) are treated
        as ``VALID``.
        """
        creds = self._auth.get_account_credentials(account_id)
        if not creds:
            return TokenStatus.MISSING

        # Accept either field name used by the OAuth flow
        token = creds.get('access_token') or creds.get('page_access_token')
        if not token:
            return TokenStatus.MISSING

        expires_at_raw = creds.get('expires_at')
        if not expires_at_raw:
            # No expiry tracked (e.g. Facebook Page token) — treat as valid.
            return TokenStatus.VALID

        try:
            expires_at = datetime.fromisoformat(expires_at_raw)
        except ValueError:
            get_logger().warning(f'Could not parse expires_at for {account_id}: {expires_at_raw!r}')
            return TokenStatus.VALID  # optimistic; let the API call fail if truly expired

        now = datetime.now(tz=UTC)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        delta = expires_at - now
        if delta.total_seconds() <= 0:
            return TokenStatus.EXPIRED
        if delta < timedelta(days=EXPIRES_SOON_THRESHOLD_DAYS):
            return TokenStatus.EXPIRES_SOON
        return TokenStatus.VALID

    def refresh_token(self, account_id: str) -> tuple[bool, str | None]:
        """Refresh the access token for *account_id* if it is refreshable.

        Returns ``(True, None)`` on success or ``(False, error_message)``
        on failure.

        Facebook Page tokens do not expire on their own, so calling this on
        a ``meta_facebook_page`` account always returns ``(True, None)``
        immediately (the caller must trigger a full re-auth if the page
        token is actually invalidated).
        """
        creds = self._auth.get_account_credentials(account_id)
        if not creds:
            return False, 'No credentials stored for account.'

        provider = creds.get('provider', '')
        if provider not in _REFRESHABLE_PROVIDERS:
            # Facebook Page token — effectively permanent, nothing to do.
            return True, None

        access_token = creds.get('access_token')
        if not access_token:
            return False, 'No access token stored for account.'

        endpoint = _REFRESH_ENDPOINTS[provider]
        grant_type = _REFRESH_GRANT_TYPES[provider]

        try:
            resp = requests.get(
                endpoint,
                params={'grant_type': grant_type, 'access_token': access_token},
                timeout=30,
            )
            resp.raise_for_status()
        except requests.Timeout:
            return False, 'Request timed out while refreshing token.'
        except requests.ConnectionError:
            return False, 'Could not connect to Meta API for token refresh.'
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else '?'
            return False, f'Meta API returned HTTP {status} during token refresh.'
        except Exception as exc:  # noqa: BLE001
            return False, f'Unexpected error during token refresh: {exc}'

        data = resp.json()
        new_token = data.get('access_token')
        if not new_token:
            return False, 'Meta API did not return a new access token.'

        updated_creds: dict = {**creds, 'access_token': new_token}
        expires_in = data.get('expires_in')
        if expires_in is not None:
            new_expires_at = (datetime.now(tz=UTC) + timedelta(seconds=int(expires_in))).isoformat()
            updated_creds['expires_at'] = new_expires_at

        self._auth.save_account_credentials(account_id, updated_creds)
        get_logger().info(f'Refreshed access token for {account_id} ({provider})')
        return True, None

    def get_all_statuses(self) -> dict[str, TokenStatus]:
        """Return token statuses for all Meta platform accounts.

        Only accounts whose ``platform_id`` starts with ``meta_`` are
        included.
        """
        statuses: dict[str, TokenStatus] = {}
        for account in self._auth.get_accounts():
            if account.platform_id.startswith('meta_'):
                statuses[account.account_id] = self.get_token_status(account.account_id)
        return statuses

    def refresh_all_expiring(self) -> dict[str, bool]:
        """Refresh tokens for all Meta accounts that are ``EXPIRES_SOON``.

        Returns a mapping of ``account_id -> success``.
        """
        results: dict[str, bool] = {}
        for account_id, status in self.get_all_statuses().items():
            if status == TokenStatus.EXPIRES_SOON:
                ok, err = self.refresh_token(account_id)
                if not ok:
                    get_logger().warning(f'Token refresh failed for {account_id}: {err}')
                results[account_id] = ok
        return results
