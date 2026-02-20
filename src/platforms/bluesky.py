"""Bluesky platform implementation using atproto."""

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atproto import Client as BskyClient  # type: ignore[import-untyped]

from src.core.auth_manager import AuthManager
from src.core.error_handler import create_error_result
from src.core.logger import get_logger
from src.platforms.base import BasePlatform
from src.utils.constants import BLUESKY_SPECS, PlatformSpecs, PostResult


def detect_urls(text: str) -> list[dict]:
    """Find all HTTP(S) URLs in text and create facet objects.

    CRITICAL: Facets use UTF-8 byte offsets, not character positions!
    """
    url_pattern = (
        r'http[s]?://(?:[a-zA-Z0-9]|[$\-_@.&+]|[!*\\(\\),]|/|'
        r'(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    )

    facets = []
    for match in re.finditer(url_pattern, text):
        byte_start = len(text[: match.start()].encode('utf-8'))
        byte_end = len(text[: match.end()].encode('utf-8'))

        facets.append(
            {
                'index': {
                    'byteStart': byte_start,
                    'byteEnd': byte_end,
                },
                'features': [
                    {
                        '$type': 'app.bsky.richtext.facet#link',
                        'uri': match.group(0),
                    }
                ],
            }
        )

    return facets


class BlueskyPlatform(BasePlatform):
    """Bluesky posting via AT Protocol."""

    def __init__(self, auth_manager: AuthManager, account_key: str = 'primary'):
        self._auth_manager = auth_manager
        self._account_key = account_key
        self._client: Any | None = None

    def get_platform_name(self) -> str:
        return 'Bluesky (Alt)' if self._account_key == 'alt' else 'Bluesky'

    def get_specs(self) -> PlatformSpecs:
        return BLUESKY_SPECS

    def authenticate(self) -> tuple[bool, str | None]:
        creds = (
            self._auth_manager.get_bluesky_auth_alt()
            if self._account_key == 'alt'
            else self._auth_manager.get_bluesky_auth()
        )
        if not creds:
            return False, 'AUTH-MISSING'

        try:
            service = creds.get('service', 'https://bsky.social')
            self._client = BskyClient(base_url=service)
            self._client.login(creds['identifier'], creds['app_password'])
            get_logger().info(f'Bluesky authenticated as {creds["identifier"]}')
            return True, None
        except Exception as e:
            error_str = str(e).lower()
            get_logger().error(f'Bluesky auth failed: {e}')
            if 'invalid' in error_str or 'authentication' in error_str:
                return False, 'BS-AUTH-INVALID'
            if 'expired' in error_str:
                return False, 'BS-AUTH-EXPIRED'
            return False, 'BS-AUTH-INVALID'

    def test_connection(self) -> tuple[bool, str | None]:
        success, error = self.authenticate()
        if not success:
            return False, error
        client = self._client
        if client is None:
            return False, 'BS-AUTH-INVALID'

        try:
            profile = client.get_profile(client.me.did)
            get_logger().info(f'Bluesky connected as @{profile.handle}')
            return True, None
        except Exception as e:
            get_logger().error(f'Bluesky connection test failed: {e}')
            return False, 'BS-AUTH-INVALID'

    def post(self, text: str, image_path: Path | None = None) -> PostResult:
        if not self._client:
            success, error = self.authenticate()
            if not success:
                return create_error_result(error or 'AUTH-MISSING', 'Bluesky')
        client = self._client
        if client is None:
            return create_error_result('BS-AUTH-INVALID', 'Bluesky')

        try:
            facets = detect_urls(text)
            embed: dict[str, object] | None = None
            images: list[dict[str, object]] | None = None

            if image_path:
                try:
                    img_data = image_path.read_bytes()
                    upload = client.upload_blob(img_data)
                    images = [
                        {
                            'alt': '',
                            'image': upload.blob,
                        }
                    ]
                    embed = {
                        '$type': 'app.bsky.embed.images',
                        'images': images,
                    }
                except Exception as e:
                    return create_error_result(
                        'IMG-UPLOAD-FAILED',
                        'Bluesky',
                        exception=e,
                        details={'image_path': str(image_path)},
                    )

            record: dict[str, object] = {
                '$type': 'app.bsky.feed.post',
                'text': text,
                'createdAt': datetime.now(UTC).isoformat(),
            }
            if facets:
                record['facets'] = facets
            if embed:
                record['embed'] = embed

            response = client.com.atproto.repo.create_record(
                data={
                    'repo': client.me.did,
                    'collection': 'app.bsky.feed.post',
                    'record': record,
                }
            )

            # Build post URL
            rkey = response.uri.split('/')[-1]
            handle = client.me.handle
            post_url = f'https://bsky.app/profile/{handle}/post/{rkey}'

            get_logger().info(f'Bluesky post success: {post_url}')
            return PostResult(
                success=True,
                platform='Bluesky',
                post_url=post_url,
                raw_response={'uri': response.uri, 'cid': response.cid},
            )

        except Exception as e:
            error_str = str(e).lower()
            if 'rate' in error_str or 'limit' in error_str:
                return create_error_result('BS-RATE-LIMIT', 'Bluesky', exception=e)
            if 'auth' in error_str or 'expired' in error_str or 'token' in error_str:
                return create_error_result('BS-AUTH-EXPIRED', 'Bluesky', exception=e)
            return create_error_result('POST-FAILED', 'Bluesky', exception=e)
