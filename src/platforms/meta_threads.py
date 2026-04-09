"""Threads API platform adapter (GaleFling Threads app registration).

Credentials required in {account_id}_auth.json:
    access_token  — long-lived Threads user token
    user_id       — Threads user ID (numeric string)
    provider      — 'meta_threads' (used by TokenManager)
    expires_at    — ISO-8601 expiry timestamp (optional but recommended)

AWS media staging credentials are required for image and video posts.
Text-only posts do not require S3 access.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

import requests

from src.core.auth_manager import AuthManager
from src.core.aws_utils import MediaStager, MediaStagingError
from src.core.error_handler import create_error_result
from src.core.logger import get_logger
from src.platforms.base import BasePlatform
from src.utils.constants import META_THREADS_API_SPECS, PlatformSpecs, PostResult

THREADS_API_BASE = 'https://graph.threads.net/v1.0'

# Seconds between status poll attempts for image/video containers.
_POLL_INTERVAL = 5
# Maximum seconds to wait for a container to finish processing.
_POLL_TIMEOUT = 120

# File extensions treated as video files for format routing.
_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.m4v', '.3gp'}


class MetaThreadsPlatform(BasePlatform):
    """Threads posting via the Threads API."""

    def __init__(
        self,
        auth_manager: AuthManager,
        account_id: str = 'meta_threads_1',
        profile_name: str = '',
    ) -> None:
        self._auth_manager = auth_manager
        self._account_id = account_id
        self._profile_name = profile_name
        self._access_token: str | None = None
        self._user_id: str | None = None

    def get_platform_name(self) -> str:
        if self._profile_name:
            return f'Threads ({self._profile_name})'
        return 'Threads'

    def get_specs(self) -> PlatformSpecs:
        return META_THREADS_API_SPECS

    # ── Credential helpers ────────────────────────────────────────────

    def _load_credentials(self) -> bool:
        """Load access token and user ID from the stored auth file."""
        creds = self._auth_manager.get_account_credentials(self._account_id)
        if not creds:
            return False
        self._access_token = creds.get('access_token')
        self._user_id = creds.get('user_id')
        return bool(self._access_token and self._user_id)

    def _get_media_stager(self) -> MediaStager | None:
        """Return a configured MediaStager, or None if AWS creds are absent."""
        aws = self._auth_manager.get_aws_media_staging_credentials()
        if not aws:
            return None
        return MediaStager(
            access_key_id=aws['access_key_id'],
            secret_access_key=aws['secret_access_key'],
            region=aws.get('region', 'us-west-2'),
            bucket=aws['media_staging_bucket'],
        )

    # ── Public interface ──────────────────────────────────────────────

    def authenticate(self) -> tuple[bool, str | None]:
        if not self._load_credentials():
            return False, 'AUTH-MISSING'
        return self.test_connection()

    def test_connection(self) -> tuple[bool, str | None]:
        if (not self._access_token or not self._user_id) and not self._load_credentials():
            return False, 'AUTH-MISSING'
        try:
            resp = requests.get(
                f'{THREADS_API_BASE}/{self._user_id}',
                params={'fields': 'username', 'access_token': self._access_token},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                get_logger().info(
                    f'Threads authenticated as @{data.get("username", "?")} '
                    f'(account={self._account_id})'
                )
                return True, None
            if resp.status_code in (401, 403):
                return False, 'TH-AUTH-EXPIRED'
            return False, 'TH-AUTH-INVALID'
        except requests.Timeout:
            return False, 'NET-TIMEOUT'
        except requests.ConnectionError:
            return False, 'NET-CONNECTION'
        except Exception as exc:
            get_logger().error(f'Threads connection test failed: {exc}')
            return False, 'TH-AUTH-INVALID'

    def post(self, text: str, media_paths: list[Path] | None = None) -> PostResult:
        if (not self._access_token or not self._user_id) and not self._load_credentials():
            return create_error_result('AUTH-MISSING', 'Threads')

        error_code = self._validate_pre_post(text, media_paths)
        if error_code:
            return create_error_result(error_code, 'Threads')

        try:
            if not media_paths:
                return self._post_text(text)
            if len(media_paths) == 1:
                path = media_paths[0]
                if path.suffix.lower() in _VIDEO_EXTENSIONS:
                    return self._post_video(text, path)
                return self._post_image(text, path)
            return self._post_carousel(text, media_paths)
        except _AuthError as exc:
            return create_error_result(exc.error_code, 'Threads', exception=exc)
        except _RateLimitError:
            return create_error_result('TH-RATE-LIMIT', 'Threads')
        except Exception as exc:
            return create_error_result('TH-POST-FAILED', 'Threads', exception=exc)

    # ── Pre-post validation ───────────────────────────────────────────

    def _validate_pre_post(self, text: str, media_paths: list[Path] | None) -> str | None:
        """Validate text, media, token freshness, and quota before posting.

        Returns an error code string on failure, or ``None`` if all checks pass.
        """
        specs = META_THREADS_API_SPECS

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
                        return 'TH-AUTH-EXPIRED'
                except ValueError:
                    pass  # Unparseable expiry — skip check

        # 4. Rate limit headroom via Threads quota endpoint
        if self._is_quota_exhausted():
            return 'TH-RATE-LIMIT'

        return None

    def _is_quota_exhausted(self) -> bool:
        """Return True if the daily Threads publishing quota is exhausted.

        Calls ``GET /{user_id}/threads_publishing_limit`` and compares
        ``quota_usage`` against ``config.quota_total``.  Any error (network,
        missing field) is silently ignored — the post attempt proceeds and
        will surface a 429 response if the quota is actually exhausted.
        """
        try:
            resp = requests.get(
                f'{THREADS_API_BASE}/{self._user_id}/threads_publishing_limit',
                params={
                    'fields': 'config,quota_usage',
                    'access_token': self._access_token,
                },
                timeout=10,
            )
            if resp.status_code != 200:
                return False
            data = resp.json().get('data', [{}])[0] if resp.json().get('data') else {}
            quota_usage = data.get('quota_usage', 0)
            config = data.get('config', {})
            quota_total = config.get('quota_total', 250)
            return int(quota_usage) >= int(quota_total)
        except Exception:
            return False

    # ── Post type implementations ─────────────────────────────────────

    def _post_text(self, text: str) -> PostResult:
        container_id = self._create_container(media_type='TEXT', text=text)
        post_id = self._publish_container(container_id)
        post_url = self._get_permalink(post_id)
        get_logger().info(f'Threads text post success: {post_url or post_id}')
        return PostResult(
            success=True,
            platform='Threads',
            post_url=post_url,
            raw_response={'id': post_id},
            account_id=self._account_id,
            profile_name=self._profile_name,
            url_captured=post_url is not None,
        )

    def _post_image(self, text: str, image_path: Path) -> PostResult:
        image_url = self._stage_media(image_path)
        container_id = self._create_container(media_type='IMAGE', text=text, image_url=image_url)
        self._wait_for_container(container_id)
        post_id = self._publish_container(container_id)
        post_url = self._get_permalink(post_id)
        get_logger().info(f'Threads image post success: {post_url or post_id}')
        return PostResult(
            success=True,
            platform='Threads',
            post_url=post_url,
            raw_response={'id': post_id},
            account_id=self._account_id,
            profile_name=self._profile_name,
            url_captured=post_url is not None,
        )

    def _post_video(self, text: str, video_path: Path) -> PostResult:
        video_url = self._stage_media(video_path)
        container_id = self._create_container(media_type='VIDEO', text=text, video_url=video_url)
        self._wait_for_container(container_id)
        post_id = self._publish_container(container_id)
        post_url = self._get_permalink(post_id)
        get_logger().info(f'Threads video post success: {post_url or post_id}')
        return PostResult(
            success=True,
            platform='Threads',
            post_url=post_url,
            raw_response={'id': post_id},
            account_id=self._account_id,
            profile_name=self._profile_name,
            url_captured=post_url is not None,
        )

    def _post_carousel(self, text: str, media_paths: list[Path]) -> PostResult:
        item_ids: list[str] = []
        for path in media_paths:
            media_url = self._stage_media(path)
            if path.suffix.lower() in _VIDEO_EXTENSIONS:
                item_id = self._create_container(
                    media_type='VIDEO', video_url=media_url, is_carousel_item=True
                )
            else:
                item_id = self._create_container(
                    media_type='IMAGE', image_url=media_url, is_carousel_item=True
                )
            self._wait_for_container(item_id)
            item_ids.append(item_id)

        carousel_id = self._create_carousel_container(text, item_ids)
        self._wait_for_container(carousel_id)
        post_id = self._publish_container(carousel_id)
        post_url = self._get_permalink(post_id)
        get_logger().info(f'Threads carousel post success: {post_url or post_id}')
        return PostResult(
            success=True,
            platform='Threads',
            post_url=post_url,
            raw_response={'id': post_id},
            account_id=self._account_id,
            profile_name=self._profile_name,
            url_captured=post_url is not None,
        )

    # ── Threads API helpers ───────────────────────────────────────────

    def _stage_media(self, file_path: Path) -> str:
        """Upload *file_path* to S3 and return its public URL."""
        stager = self._get_media_stager()
        if stager is None:
            raise _PostError('S3 media staging credentials not configured.')
        try:
            return stager.upload_media(file_path)
        except MediaStagingError as exc:
            raise _PostError(f'S3 upload failed: {exc}') from exc

    def _create_container(
        self,
        *,
        media_type: str,
        text: str = '',
        image_url: str = '',
        video_url: str = '',
        is_carousel_item: bool = False,
    ) -> str:
        """Create a Threads media container. Returns the container ID."""
        params: dict[str, str] = {
            'media_type': media_type,
            'access_token': self._access_token,  # type: ignore[dict-item]
        }
        if text:
            params['text'] = text
        if image_url:
            params['image_url'] = image_url
        if video_url:
            params['video_url'] = video_url
        if is_carousel_item:
            params['is_carousel_item'] = 'true'

        resp = requests.post(
            f'{THREADS_API_BASE}/{self._user_id}/threads',
            data=params,
            timeout=30,
        )
        self._raise_for_status(resp)
        return resp.json()['id']

    def _create_carousel_container(self, text: str, item_ids: list[str]) -> str:
        """Create a carousel container referencing *item_ids*. Returns container ID."""
        resp = requests.post(
            f'{THREADS_API_BASE}/{self._user_id}/threads',
            data={
                'media_type': 'CAROUSEL',
                'text': text,
                'children': ','.join(item_ids),
                'access_token': self._access_token,
            },
            timeout=30,
        )
        self._raise_for_status(resp)
        return resp.json()['id']

    def _wait_for_container(self, container_id: str) -> None:
        """Poll container status until FINISHED or timeout.

        Raises ``_PostError`` on ERROR status or if the timeout is exceeded.
        """
        deadline = time.monotonic() + _POLL_TIMEOUT
        while time.monotonic() < deadline:
            resp = requests.get(
                f'{THREADS_API_BASE}/{container_id}',
                params={'fields': 'status', 'access_token': self._access_token},
                timeout=15,
            )
            self._raise_for_status(resp)
            status = resp.json().get('status', '')
            if status == 'FINISHED':
                return
            if status == 'ERROR':
                raise _PostError(f'Threads container {container_id} failed processing.')
            time.sleep(_POLL_INTERVAL)
        raise _PostError(
            f'Threads container {container_id} did not finish within {_POLL_TIMEOUT}s.'
        )

    def _publish_container(self, container_id: str) -> str:
        """Publish the container. Returns the resulting post ID."""
        resp = requests.post(
            f'{THREADS_API_BASE}/{self._user_id}/threads_publish',
            data={
                'creation_id': container_id,
                'access_token': self._access_token,
            },
            timeout=30,
        )
        self._raise_for_status(resp)
        return resp.json()['id']

    def _get_permalink(self, post_id: str) -> str | None:
        """Fetch the permalink for a published post."""
        try:
            resp = requests.get(
                f'{THREADS_API_BASE}/{post_id}',
                params={'fields': 'permalink', 'access_token': self._access_token},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json().get('permalink')
        except Exception as exc:
            get_logger().warning(f'Threads permalink fetch failed: {exc}')
        return None

    @staticmethod
    def _raise_for_status(resp: requests.Response) -> None:
        """Map HTTP error codes to typed exceptions."""
        if resp.status_code == 429:
            raise _RateLimitError()
        if resp.status_code in (401, 403):
            raise _AuthError('TH-AUTH-EXPIRED')
        resp.raise_for_status()


# ── Internal exception types ──────────────────────────────────────────


class _AuthError(Exception):
    def __init__(self, error_code: str = 'TH-AUTH-EXPIRED') -> None:
        self.error_code = error_code
        super().__init__(error_code)


class _RateLimitError(Exception):
    pass


class _PostError(Exception):
    pass
