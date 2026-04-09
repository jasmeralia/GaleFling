"""Facebook Page API platform adapter (GaleFling Facebook app registration).

Credentials required in {account_id}_auth.json:
    page_access_token — long-lived Page access token
    page_id           — Facebook Page ID (numeric string)
    provider          — 'meta_facebook_page' (used by TokenManager)
    page_name         — display name of the page (optional)

Facebook's /photos endpoint accepts direct binary uploads, so S3 staging
is not required for photo posts. Text posts use the /feed endpoint.
Video uploads use the /videos endpoint with a direct binary upload.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import requests

from src.core.auth_manager import AuthManager
from src.core.error_handler import create_error_result
from src.core.logger import get_logger
from src.platforms.base import BasePlatform
from src.utils.constants import META_FACEBOOK_PAGE_SPECS, PlatformSpecs, PostResult

FB_GRAPH_BASE = 'https://graph.facebook.com/v25.0'

# File extensions treated as video files for format routing.
_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.m4v', '.3gp'}


class MetaFacebookPagePlatform(BasePlatform):
    """Facebook Page posting via the Graph API."""

    def __init__(
        self,
        auth_manager: AuthManager,
        account_id: str = 'meta_facebook_page_1',
        profile_name: str = '',
    ) -> None:
        self._auth_manager = auth_manager
        self._account_id = account_id
        self._profile_name = profile_name
        self._page_access_token: str | None = None
        self._page_id: str | None = None

    def get_platform_name(self) -> str:
        if self._profile_name:
            return f'Facebook Page ({self._profile_name})'
        return 'Facebook Page'

    def get_specs(self) -> PlatformSpecs:
        return META_FACEBOOK_PAGE_SPECS

    # ── Credential helpers ────────────────────────────────────────────

    def _load_credentials(self) -> bool:
        """Load page access token and page ID from the stored auth file."""
        creds = self._auth_manager.get_account_credentials(self._account_id)
        if not creds:
            return False
        self._page_access_token = creds.get('page_access_token')
        self._page_id = creds.get('page_id')
        return bool(self._page_access_token and self._page_id)

    # ── Public interface ──────────────────────────────────────────────

    def authenticate(self) -> tuple[bool, str | None]:
        if not self._load_credentials():
            return False, 'AUTH-MISSING'
        return self.test_connection()

    def test_connection(self) -> tuple[bool, str | None]:
        if (not self._page_access_token or not self._page_id) and not self._load_credentials():
            return False, 'AUTH-MISSING'
        try:
            resp = requests.get(
                f'{FB_GRAPH_BASE}/{self._page_id}',
                params={
                    'fields': 'name',
                    'access_token': self._page_access_token,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                get_logger().info(
                    f'Facebook Page authenticated: {data.get("name", "?")} '
                    f'(account={self._account_id})'
                )
                return True, None
            if resp.status_code in (401, 403):
                _log_api_error('Facebook Page', resp)
                return False, 'FB-AUTH-EXPIRED'
            _log_api_error('Facebook Page', resp)
            return False, 'FB-AUTH-INVALID'
        except requests.Timeout:
            return False, 'NET-TIMEOUT'
        except requests.ConnectionError:
            return False, 'NET-CONNECTION'
        except Exception as exc:
            get_logger().error(f'Facebook Page connection test failed: {exc}')
            return False, 'FB-AUTH-INVALID'

    def post(self, text: str, media_paths: list[Path] | None = None) -> PostResult:
        if (not self._page_access_token or not self._page_id) and not self._load_credentials():
            return create_error_result('AUTH-MISSING', 'Facebook Page')

        error_code = self._validate_pre_post(text, media_paths)
        if error_code:
            return create_error_result(error_code, 'Facebook Page')

        try:
            if not media_paths:
                return self._post_text(text)
            if len(media_paths) == 1:
                path = media_paths[0]
                if path.suffix.lower() in _VIDEO_EXTENSIONS:
                    return self._post_video(text, path)
                return self._post_photo(text, path)
            # Multiple photos: post each as a separate photo attached to a feed post
            return self._post_multi_photo(text, media_paths)
        except _AuthError as exc:
            return create_error_result(exc.error_code, 'Facebook Page', exception=exc)
        except _RateLimitError:
            return create_error_result('FB-RATE-LIMIT', 'Facebook Page')
        except Exception as exc:
            return create_error_result('FB-POST-FAILED', 'Facebook Page', exception=exc)

    # ── Pre-post validation ───────────────────────────────────────────

    def _validate_pre_post(self, text: str, media_paths: list[Path] | None) -> str | None:
        """Validate text, media, and token freshness before posting.

        Returns an error code string on failure, or ``None`` if all checks pass.
        """
        specs = META_FACEBOOK_PAGE_SPECS

        # 1. Caption/text length
        if specs.max_text_length is not None and len(text) > specs.max_text_length:
            return 'POST-TEXT-TOO-LONG'

        # 2. Media format and file size
        if media_paths:
            for path in media_paths:
                suffix = path.suffix.lower()
                if suffix in _VIDEO_EXTENSIONS:
                    fmt = suffix.lstrip('.').upper()
                    if fmt not in specs.supported_video_formats:
                        return 'VID-INVALID-FORMAT'
                    if specs.max_video_file_size_mb is not None:
                        size_mb = path.stat().st_size / (1024 * 1024)
                        if size_mb > specs.max_video_file_size_mb:
                            return 'VID-TOO-LARGE'
                else:
                    fmt = suffix.lstrip('.').upper()
                    if fmt == 'JPG':
                        fmt = 'JPEG'
                    if fmt not in specs.supported_formats:
                        return 'IMG-INVALID-FORMAT'
                    size_mb = path.stat().st_size / (1024 * 1024)
                    if size_mb > specs.max_file_size_mb:
                        return 'IMG-TOO-LARGE'

        # 3. Token freshness — check stored expires_at if present
        creds = self._auth_manager.get_account_credentials(self._account_id)
        if creds:
            expires_at = creds.get('expires_at')
            if expires_at:
                try:
                    expiry = datetime.fromisoformat(expires_at)
                    if expiry.tzinfo is None:
                        expiry = expiry.replace(tzinfo=UTC)
                    if expiry <= datetime.now(UTC):
                        return 'FB-AUTH-EXPIRED'
                except ValueError:
                    pass  # Unparseable expiry — skip check

        return None

    # ── Post type implementations ─────────────────────────────────────

    def _post_text(self, text: str) -> PostResult:
        resp = requests.post(
            f'{FB_GRAPH_BASE}/{self._page_id}/feed',
            data={
                'message': text,
                'access_token': self._page_access_token,
            },
            timeout=30,
        )
        self._raise_for_status(resp)
        post_id = resp.json().get('id', '')
        post_url = self._build_post_url(post_id)
        get_logger().info(f'Facebook Page text post success: {post_id}')
        return PostResult(
            success=True,
            platform='Facebook Page',
            post_url=post_url,
            raw_response={'id': post_id},
            account_id=self._account_id,
            profile_name=self._profile_name,
            url_captured=post_url is not None,
        )

    def _post_photo(self, caption: str, photo_path: Path) -> PostResult:
        with open(photo_path, 'rb') as fh:
            resp = requests.post(
                f'{FB_GRAPH_BASE}/{self._page_id}/photos',
                data={
                    'caption': caption,
                    'access_token': self._page_access_token,
                },
                files={'source': fh},
                timeout=60,
            )
        self._raise_for_status(resp)
        data = resp.json()
        post_id = data.get('post_id') or data.get('id', '')
        post_url = self._build_post_url(post_id)
        get_logger().info(f'Facebook Page photo post success: {post_id}')
        return PostResult(
            success=True,
            platform='Facebook Page',
            post_url=post_url,
            raw_response=data,
            account_id=self._account_id,
            profile_name=self._profile_name,
            url_captured=post_url is not None,
        )

    def _post_multi_photo(self, caption: str, photo_paths: list[Path]) -> PostResult:
        """Upload each photo as unpublished, then create a feed post linking them."""
        photo_ids: list[str] = []
        for path in photo_paths:
            with open(path, 'rb') as fh:
                resp = requests.post(
                    f'{FB_GRAPH_BASE}/{self._page_id}/photos',
                    data={
                        'published': 'false',
                        'access_token': self._page_access_token,
                    },
                    files={'source': fh},
                    timeout=60,
                )
            self._raise_for_status(resp)
            photo_ids.append(resp.json()['id'])

        attached = [{'media_fbid': pid} for pid in photo_ids]
        resp = requests.post(
            f'{FB_GRAPH_BASE}/{self._page_id}/feed',
            data={
                'message': caption,
                'attached_media': json.dumps(attached),
                'access_token': self._page_access_token,
            },
            timeout=30,
        )
        self._raise_for_status(resp)
        post_id = resp.json().get('id', '')
        post_url = self._build_post_url(post_id)
        get_logger().info(f'Facebook Page multi-photo post success: {post_id}')
        return PostResult(
            success=True,
            platform='Facebook Page',
            post_url=post_url,
            raw_response={'id': post_id},
            account_id=self._account_id,
            profile_name=self._profile_name,
            url_captured=post_url is not None,
        )

    def _post_video(self, description: str, video_path: Path) -> PostResult:
        with open(video_path, 'rb') as fh:
            resp = requests.post(
                f'{FB_GRAPH_BASE}/{self._page_id}/videos',
                data={
                    'description': description,
                    'access_token': self._page_access_token,
                },
                files={'source': fh},
                timeout=300,
            )
        self._raise_for_status(resp)
        post_id = resp.json().get('id', '')
        get_logger().info(f'Facebook Page video post success: {post_id}')
        return PostResult(
            success=True,
            platform='Facebook Page',
            post_url=None,
            raw_response={'id': post_id},
            account_id=self._account_id,
            profile_name=self._profile_name,
            url_captured=False,
        )

    # ── Helpers ───────────────────────────────────────────────────────

    def _build_post_url(self, post_id: str) -> str | None:
        """Return a Facebook post URL for *post_id* if it looks valid."""
        if not post_id or '_' not in post_id:
            return None
        page_part, obj_part = post_id.split('_', 1)
        return f'https://www.facebook.com/{page_part}/posts/{obj_part}'

    @staticmethod
    def _raise_for_status(resp: requests.Response) -> None:
        """Map HTTP error codes to typed exceptions.

        Non-2xx responses outside the handled ranges are logged with the full
        Meta API error body before raising, so that misconfigured app settings
        (wrong app ID, missing scopes, wrong page ID, app not in dev mode)
        produce actionable log entries.
        """
        if resp.status_code == 429:
            raise _RateLimitError()
        if resp.status_code in (401, 403):
            _log_api_error('Facebook Page', resp)
            raise _AuthError('FB-AUTH-EXPIRED')
        if not resp.ok:
            detail = _log_api_error('Facebook Page', resp)
            raise _PostError(f'API error {resp.status_code}: {detail}')


# ── Module-level helpers ──────────────────────────────────────────────


def _log_api_error(platform: str, resp: requests.Response) -> str:
    """Parse and log a Meta API error response. Returns a short summary string."""
    try:
        body = resp.json()
        err = body.get('error', {})
        code = err.get('code', resp.status_code)
        subcode = err.get('error_subcode')
        etype = err.get('type', '')
        msg = err.get('message', resp.text[:300])
        detail = (
            f'code={code}'
            + (f' subcode={subcode}' if subcode else '')
            + f' type={etype!r} message={msg!r}'
        )
    except Exception:
        detail = resp.text[:300]
    get_logger().error(f'{platform} API error {resp.status_code}: {detail}')
    return detail


# ── Internal exception types ──────────────────────────────────────────


class _AuthError(Exception):
    def __init__(self, error_code: str = 'FB-AUTH-EXPIRED') -> None:
        self.error_code = error_code
        super().__init__(error_code)


class _RateLimitError(Exception):
    pass


class _PostError(Exception):
    pass
