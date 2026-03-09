"""Instagram platform implementation using the Graph API."""

from pathlib import Path

import requests

from src.core.auth_manager import AuthManager
from src.core.error_handler import create_error_result
from src.core.logger import get_logger
from src.platforms.base import BasePlatform
from src.utils.constants import INSTAGRAM_SPECS, PlatformSpecs, PostResult

GRAPH_API_BASE = 'https://graph.facebook.com/v21.0'


class InstagramPlatform(BasePlatform):
    """Instagram posting via the Graph API (Business/Creator accounts)."""

    def __init__(
        self,
        auth_manager: AuthManager,
        account_id: str = 'instagram_1',
        profile_name: str = '',
    ):
        self._auth_manager = auth_manager
        self._account_id = account_id
        self._profile_name = profile_name
        self._access_token: str | None = None
        self._ig_user_id: str | None = None

    def get_platform_name(self) -> str:
        if self._profile_name:
            return f'Instagram ({self._profile_name})'
        return 'Instagram'

    def get_specs(self) -> PlatformSpecs:
        return INSTAGRAM_SPECS

    def _load_credentials(self) -> bool:
        """Load access token and IG user ID from stored credentials."""
        creds = self._auth_manager.get_account_credentials(self._account_id)
        if not creds:
            return False
        self._access_token = creds.get('access_token')
        self._ig_user_id = creds.get('ig_user_id')
        return bool(self._access_token and self._ig_user_id)

    def authenticate(self) -> tuple[bool, str | None]:
        if not self._load_credentials():
            return False, 'AUTH-MISSING'

        try:
            resp = requests.get(
                f'{GRAPH_API_BASE}/{self._ig_user_id}',
                params={'fields': 'username', 'access_token': self._access_token},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                get_logger().info(f'Instagram authenticated as @{data.get("username", "?")}')
                return True, None
            if resp.status_code == 401:
                return False, 'IG-AUTH-EXPIRED'
            return False, 'IG-AUTH-INVALID'
        except requests.Timeout:
            return False, 'NET-TIMEOUT'
        except requests.ConnectionError:
            return False, 'NET-CONNECTION'
        except Exception as e:
            get_logger().error(f'Instagram auth failed: {e}')
            return False, 'IG-AUTH-INVALID'

    def test_connection(self) -> tuple[bool, str | None]:
        return self.authenticate()

    def post(self, text: str, media_paths: list[Path] | None = None) -> PostResult:
        if (not self._access_token or not self._ig_user_id) and not self._load_credentials():
            return create_error_result('AUTH-MISSING', 'Instagram')

        image_path = media_paths[0] if media_paths else None
        if not image_path:
            return create_error_result(
                'POST-FAILED',
                'Instagram',
                details={'reason': 'Instagram requires an image for each post.'},
            )

        try:
            image_url = self._upload_image(image_path)
        except _UploadError as e:
            return create_error_result(
                e.error_code,
                'Instagram',
                exception=e,
                details={'image_path': str(image_path)},
            )

        try:
            container_id = self._create_media_container(image_url, text)
            post_id = self._publish_container(container_id)
            post_url = self._get_permalink(post_id)

            get_logger().info(f'Instagram post success: {post_url or post_id}')
            return PostResult(
                success=True,
                platform='Instagram',
                post_url=post_url,
                raw_response={'id': post_id},
                account_id=self._account_id,
                profile_name=self._profile_name,
                url_captured=post_url is not None,
            )
        except _RateLimitError:
            return create_error_result('IG-RATE-LIMIT', 'Instagram')
        except _AuthError as e:
            return create_error_result(e.error_code, 'Instagram', exception=e)
        except Exception as e:
            return create_error_result('POST-FAILED', 'Instagram', exception=e)

    # ── Graph API helpers ─────────────────────────────────────────────

    def _upload_image(self, image_path: Path) -> str:
        """Upload image and return the hosted image URL.

        The Graph API requires a publicly accessible image URL. For desktop
        apps, we use the /photos endpoint on the linked Facebook Page to host
        the image and retrieve its URL.
        """
        creds = self._auth_manager.get_account_credentials(self._account_id)
        page_id = creds.get('page_id') if creds else None
        if not page_id:
            raise _UploadError('IMG-UPLOAD-FAILED', 'No Facebook Page ID configured.')

        with open(image_path, 'rb') as f:
            resp = requests.post(
                f'{GRAPH_API_BASE}/{page_id}/photos',
                files={'source': f},
                data={
                    'published': 'false',
                    'access_token': self._access_token,
                },
                timeout=60,
            )

        if resp.status_code == 429:
            raise _RateLimitError()
        if resp.status_code in (401, 403):
            raise _AuthError('IG-AUTH-EXPIRED')
        if resp.status_code != 200:
            raise _UploadError('IMG-UPLOAD-FAILED', resp.text)

        # Get the image URL from the uploaded photo
        photo_id = resp.json().get('id')
        url_resp = requests.get(
            f'{GRAPH_API_BASE}/{photo_id}',
            params={'fields': 'images', 'access_token': self._access_token},
            timeout=15,
        )
        if url_resp.status_code == 200:
            images = url_resp.json().get('images', [])
            if images:
                return images[0]['source']

        raise _UploadError('IMG-UPLOAD-FAILED', 'Could not retrieve hosted image URL.')

    def _create_media_container(self, image_url: str, caption: str) -> str:
        """Create an IG media container. Returns the container ID."""
        resp = requests.post(
            f'{GRAPH_API_BASE}/{self._ig_user_id}/media',
            data={
                'image_url': image_url,
                'caption': caption,
                'access_token': self._access_token,
            },
            timeout=30,
        )
        if resp.status_code == 429:
            raise _RateLimitError()
        if resp.status_code in (401, 403):
            raise _AuthError('IG-AUTH-EXPIRED')
        resp.raise_for_status()
        return resp.json()['id']

    def _publish_container(self, container_id: str) -> str:
        """Publish the media container. Returns the media ID."""
        resp = requests.post(
            f'{GRAPH_API_BASE}/{self._ig_user_id}/media_publish',
            data={
                'creation_id': container_id,
                'access_token': self._access_token,
            },
            timeout=30,
        )
        if resp.status_code == 429:
            raise _RateLimitError()
        if resp.status_code in (401, 403):
            raise _AuthError('IG-AUTH-EXPIRED')
        resp.raise_for_status()
        return resp.json()['id']

    def _get_permalink(self, media_id: str) -> str | None:
        """Fetch the permalink for a published media object."""
        try:
            resp = requests.get(
                f'{GRAPH_API_BASE}/{media_id}',
                params={'fields': 'permalink', 'access_token': self._access_token},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json().get('permalink')
        except Exception as e:
            get_logger().warning(f'Instagram permalink fetch failed: {e}')
        return None


# ── Internal exception types ──────────────────────────────────────────


class _UploadError(Exception):
    def __init__(self, error_code: str, message: str = ''):
        self.error_code = error_code
        super().__init__(message)


class _RateLimitError(Exception):
    pass


class _AuthError(Exception):
    def __init__(self, error_code: str = 'IG-AUTH-EXPIRED'):
        self.error_code = error_code
        super().__init__(error_code)
