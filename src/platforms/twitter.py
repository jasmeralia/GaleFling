"""Twitter platform implementation using Tweepy."""

from pathlib import Path

import tweepy

from src.core.auth_manager import AuthManager
from src.core.error_handler import create_error_result
from src.core.logger import get_logger
from src.platforms.base import BasePlatform
from src.utils.constants import TWITTER_SPECS, PlatformSpecs, PostResult


class TwitterPlatform(BasePlatform):
    """Twitter posting via Tweepy (OAuth 1.0a + v2 API)."""

    def __init__(self, auth_manager: AuthManager):
        self._auth_manager = auth_manager
        self._client: tweepy.Client | None = None
        self._api_v1: tweepy.API | None = None

    def get_platform_name(self) -> str:
        return "Twitter"

    def get_specs(self) -> PlatformSpecs:
        return TWITTER_SPECS

    def authenticate(self) -> tuple[bool, str | None]:
        creds = self._auth_manager.get_twitter_auth()
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
            get_logger().error(f"Twitter auth failed: {e}")
            return False, 'TW-AUTH-INVALID'

    def test_connection(self) -> tuple[bool, str | None]:
        success, error = self.authenticate()
        if not success:
            return False, error

        try:
            me = self._client.get_me()
            if me and me.data:
                get_logger().info(f"Twitter connected as @{me.data.username}")
                return True, None
            return False, 'TW-AUTH-INVALID'
        except tweepy.Unauthorized:
            return False, 'TW-AUTH-EXPIRED'
        except tweepy.TooManyRequests:
            return False, 'TW-RATE-LIMIT'
        except Exception as e:
            get_logger().error(f"Twitter connection test failed: {e}")
            return False, 'TW-AUTH-INVALID'

    def post(self, text: str, image_path: Path | None = None) -> PostResult:
        if not self._client:
            success, error = self.authenticate()
            if not success:
                return create_error_result(error, 'Twitter')

        media_id = None
        if image_path:
            try:
                media = self._api_v1.media_upload(filename=str(image_path))
                media_id = media.media_id
            except tweepy.TooManyRequests:
                return create_error_result('TW-RATE-LIMIT', 'Twitter')
            except Exception as e:
                return create_error_result('IMG-UPLOAD-FAILED', 'Twitter',
                                           exception=e,
                                           details={'image_path': str(image_path)})

        try:
            media_ids = [media_id] if media_id else None
            response = self._client.create_tweet(text=text, media_ids=media_ids)

            if response and response.data:
                tweet_id = response.data['id']
                # Get username for URL
                me = self._client.get_me()
                username = me.data.username if me and me.data else 'i'
                post_url = f"https://twitter.com/{username}/status/{tweet_id}"

                get_logger().info(f"Twitter post success: {post_url}")
                return PostResult(
                    success=True,
                    platform='Twitter',
                    post_url=post_url,
                    raw_response=dict(response.data),
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
