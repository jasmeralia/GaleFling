"""Twitter platform implementation using Tweepy."""

from pathlib import Path
from typing import Any

import tweepy  # type: ignore[import-untyped]

from src.core.auth_manager import AuthManager
from src.core.error_handler import create_error_result
from src.core.logger import get_logger
from src.platforms.base import BasePlatform
from src.utils.constants import TWITTER_SPECS, PlatformSpecs, PostResult


class TwitterPlatform(BasePlatform):
    """Twitter posting via Tweepy (OAuth 1.0a + v2 API)."""

    def __init__(
        self,
        auth_manager: AuthManager,
        account_id: str = 'twitter_1',
        profile_name: str = '',
    ):
        self._auth_manager = auth_manager
        self._account_id = account_id
        self._profile_name = profile_name
        self._client: Any | None = None
        self._api_v1: Any | None = None

    def get_platform_name(self) -> str:
        if self._profile_name:
            return f'Twitter ({self._profile_name})'
        return 'Twitter'

    def get_specs(self) -> PlatformSpecs:
        return TWITTER_SPECS

    def _get_credentials(self) -> dict[str, str] | None:
        """Load credentials: app creds + per-account tokens."""
        app_creds = self._auth_manager.get_twitter_app_credentials()
        if not app_creds:
            # Fall back to Phase 0 combined format
            return self._auth_manager.get_twitter_auth()

        account_creds = self._auth_manager.get_account_credentials(self._account_id)
        if account_creds and all(
            k in account_creds for k in ('access_token', 'access_token_secret')
        ):
            return {**app_creds, **account_creds}

        # Fall back to Phase 0 format for backward compat
        return self._auth_manager.get_twitter_auth()

    def authenticate(self) -> tuple[bool, str | None]:
        creds = self._get_credentials()
        if not creds:
            return False, 'AUTH-MISSING'

        try:
            auth = tweepy.OAuth1UserHandler(
                creds['api_key'],
                creds['api_secret'],
                creds['access_token'],
                creds['access_token_secret'],
            )
            self._api_v1 = tweepy.API(auth)

            self._client = tweepy.Client(
                consumer_key=creds['api_key'],
                consumer_secret=creds['api_secret'],
                access_token=creds['access_token'],
                access_token_secret=creds['access_token_secret'],
            )
            return True, None
        except Exception as e:
            get_logger().error(f'Twitter auth failed: {e}')
            return False, 'TW-AUTH-INVALID'

    def test_connection(self) -> tuple[bool, str | None]:
        success, error = self.authenticate()
        if not success:
            return False, error
        client = self._client
        if client is None:
            return False, 'TW-AUTH-INVALID'

        try:
            me = client.get_me()
            if me and me.data:
                get_logger().info(f'Twitter connected as @{me.data.username}')
                return True, None
            return False, 'TW-AUTH-INVALID'
        except tweepy.Unauthorized:
            return False, 'TW-AUTH-EXPIRED'
        except tweepy.TooManyRequests:
            return False, 'TW-RATE-LIMIT'
        except Exception as e:
            get_logger().error(f'Twitter connection test failed: {e}')
            return False, 'TW-AUTH-INVALID'

    def post(self, text: str, media_paths: list[Path] | None = None) -> PostResult:
        if not self._client:
            success, error = self.authenticate()
            if not success:
                return create_error_result(error or 'AUTH-MISSING', 'Twitter')
        client = self._client
        api_v1 = self._api_v1
        if client is None or api_v1 is None:
            return create_error_result('TW-AUTH-INVALID', 'Twitter')

        media_ids = None
        if media_paths:
            media_ids = []
            for image_path in media_paths:
                try:
                    media = api_v1.media_upload(filename=str(image_path))
                    media_ids.append(media.media_id)
                except tweepy.TooManyRequests:
                    return create_error_result('TW-RATE-LIMIT', 'Twitter')
                except Exception as e:
                    return create_error_result(
                        'IMG-UPLOAD-FAILED',
                        'Twitter',
                        exception=e,
                        details={'image_path': str(image_path)},
                    )

        try:
            response = client.create_tweet(text=text, media_ids=media_ids)

            if response and response.data:
                tweet_id = response.data['id']
                # Get username for URL
                me = client.get_me()
                username = me.data.username if me and me.data else 'i'
                post_url = f'https://twitter.com/{username}/status/{tweet_id}'

                get_logger().info(f'Twitter post success: {post_url}')
                return PostResult(
                    success=True,
                    platform='Twitter',
                    post_url=post_url,
                    raw_response=dict(response.data),
                    account_id=self._account_id,
                    profile_name=self._profile_name,
                    url_captured=True,
                )
            return create_error_result('POST-FAILED', 'Twitter')

        except tweepy.Unauthorized:
            return create_error_result('TW-AUTH-EXPIRED', 'Twitter')
        except tweepy.TooManyRequests:
            return create_error_result('TW-RATE-LIMIT', 'Twitter')
        except tweepy.Forbidden as e:
            if 'duplicate' in str(e).lower():
                return create_error_result('POST-DUPLICATE', 'Twitter', exception=e)
            return create_error_result('POST-FAILED', 'Twitter', exception=e)
        except Exception as e:
            return create_error_result('POST-FAILED', 'Twitter', exception=e)

    @staticmethod
    def start_pin_flow(api_key: str, api_secret: str) -> tuple[tweepy.OAuth1UserHandler, str]:
        """Start the OAuth PIN flow. Returns (auth_handler, authorization_url)."""
        auth = tweepy.OAuth1UserHandler(api_key, api_secret, callback='oob')
        url = auth.get_authorization_url()
        return auth, url

    @staticmethod
    def complete_pin_flow(auth: tweepy.OAuth1UserHandler, pin: str) -> tuple[str, str]:
        """Complete PIN flow. Returns (access_token, access_token_secret)."""
        auth.get_access_token(verifier=pin)
        return auth.access_token, auth.access_token_secret
