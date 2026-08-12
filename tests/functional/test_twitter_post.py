"""Functional tests for Twitter — live API calls via TwitterPlatform."""

from __future__ import annotations

import contextlib
import uuid

import pytest
import tweepy


def _make_auth(creds: dict):
    """Build a minimal AuthManager stand-in from raw credential dict."""

    class _Auth:
        def get_twitter_app_credentials(self):
            return None

        def get_twitter_auth(self):
            return {
                'api_key': creds['TWITTER_API_KEY'],
                'api_secret': creds['TWITTER_API_SECRET'],
                'access_token': creds['TWITTER_ACCESS_TOKEN'],
                'access_token_secret': creds['TWITTER_ACCESS_TOKEN_SECRET'],
            }

        def get_account_credentials(self, account_id):
            return None

    return _Auth()


def _make_client(creds: dict) -> tweepy.Client:
    return tweepy.Client(
        consumer_key=creds['TWITTER_API_KEY'],
        consumer_secret=creds['TWITTER_API_SECRET'],
        access_token=creds['TWITTER_ACCESS_TOKEN'],
        access_token_secret=creds['TWITTER_ACCESS_TOKEN_SECRET'],
    )


def _delete_tweet(creds: dict, tweet_id: str) -> None:
    """Best-effort deletion of a tweet by ID."""
    if not tweet_id:
        return
    with contextlib.suppress(Exception):
        _make_client(creds).delete_tweet(tweet_id)


@pytest.mark.functional
@pytest.mark.non_mutating
class TestTwitterConnection:
    """Auth and connection tests — run first to fail fast on bad credentials."""

    def test_authenticate(self, twitter_credentials):
        from src.platforms.twitter import TwitterPlatform

        platform = TwitterPlatform(_make_auth(twitter_credentials))
        ok, err = platform.authenticate()
        assert ok, f'authenticate() failed with error: {err}'
        assert err is None

    def test_connection(self, twitter_credentials):
        from src.platforms.twitter import TwitterPlatform

        platform = TwitterPlatform(_make_auth(twitter_credentials))
        ok, err = platform.test_connection()
        assert ok, f'test_connection() failed with error: {err}'
        assert err is None

    def test_connection_returns_username(self, twitter_credentials):
        """Profile fetch: v2 API must return a username for the token."""
        me = _make_client(twitter_credentials).get_me()
        assert me and me.data
        assert me.data.username

    def test_v1_api_verify(self, twitter_credentials):
        """v1.1 verify_credentials must succeed (media uploads use v1.1)."""
        auth = tweepy.OAuth1UserHandler(
            twitter_credentials['TWITTER_API_KEY'],
            twitter_credentials['TWITTER_API_SECRET'],
            twitter_credentials['TWITTER_ACCESS_TOKEN'],
            twitter_credentials['TWITTER_ACCESS_TOKEN_SECRET'],
        )
        user = tweepy.API(auth).verify_credentials()
        assert user.screen_name

    def test_connection_bad_token(self):
        from src.platforms.twitter import TwitterPlatform

        class _BadAuth:
            def get_twitter_app_credentials(self):
                return None

            def get_twitter_auth(self):
                return {
                    'api_key': 'INVALID',
                    'api_secret': 'INVALID',
                    'access_token': 'INVALID',
                    'access_token_secret': 'INVALID',
                }

            def get_account_credentials(self, account_id):
                return None

        platform = TwitterPlatform(_BadAuth())
        ok, err = platform.test_connection()
        assert not ok
        assert err in ('TW-AUTH-EXPIRED', 'TW-AUTH-INVALID')


@pytest.mark.functional
@pytest.mark.non_mutating
class TestTwitterValidation:
    """Pre-post rejection without creating a live tweet."""

    def test_character_limit_enforcement(self, twitter_credentials):
        """Posts exceeding 280 characters must fail before a tweet is created."""
        from src.platforms.twitter import TwitterPlatform

        platform = TwitterPlatform(_make_auth(twitter_credentials))
        platform.authenticate()
        result = platform.post('A' * 281)

        assert not result.success
        assert result.error_code == 'POST-TEXT-TOO-LONG'


@pytest.mark.functional
@pytest.mark.mutating
class TestTwitterTextPost:
    """Text-only posting and deletion via TwitterPlatform."""

    def test_text_post_and_delete(self, twitter_credentials):
        from src.platforms.twitter import TwitterPlatform

        tag = uuid.uuid4().hex[:8]
        text = f'GaleFling functional test {tag} — safe to delete'

        platform = TwitterPlatform(_make_auth(twitter_credentials))
        result = platform.post(text)

        assert result.success, f'Text post failed: {result.error_code} — {result.error_message}'
        assert result.platform == 'Twitter'
        tweet_id = result.raw_response.get('id')
        assert tweet_id
        if result.post_url:
            assert 'twitter.com/' in result.post_url or 'x.com/' in result.post_url

        _delete_tweet(twitter_credentials, tweet_id)


@pytest.mark.functional
@pytest.mark.mutating
class TestTwitterImagePost:
    """Image upload and posting via TwitterPlatform."""

    def test_single_image_post(self, twitter_credentials, sample_jpeg):
        from src.platforms.twitter import TwitterPlatform

        tag = uuid.uuid4().hex[:8]
        caption = f'GaleFling image test {tag} — safe to delete'

        platform = TwitterPlatform(_make_auth(twitter_credentials))
        result = platform.post(caption, media_paths=[sample_jpeg])

        assert result.success, f'Image post failed: {result.error_code} — {result.error_message}'
        tweet_id = result.raw_response.get('id')
        assert tweet_id

        _delete_tweet(twitter_credentials, tweet_id)

    def test_png_image_post(self, twitter_credentials, sample_png):
        from src.platforms.twitter import TwitterPlatform

        tag = uuid.uuid4().hex[:8]
        caption = f'GaleFling PNG test {tag} — safe to delete'

        platform = TwitterPlatform(_make_auth(twitter_credentials))
        result = platform.post(caption, media_paths=[sample_png])

        assert result.success, f'PNG post failed: {result.error_code} — {result.error_message}'
        tweet_id = result.raw_response.get('id')
        assert tweet_id

        _delete_tweet(twitter_credentials, tweet_id)

    def test_multiple_images_post(self, twitter_credentials, sample_jpeg, sample_png):
        from src.platforms.twitter import TwitterPlatform

        tag = uuid.uuid4().hex[:8]
        caption = f'GaleFling multi-image test {tag} — safe to delete'

        platform = TwitterPlatform(_make_auth(twitter_credentials))
        result = platform.post(caption, media_paths=[sample_jpeg, sample_png])

        assert result.success, (
            f'Multi-image post failed: {result.error_code} — {result.error_message}'
        )
        tweet_id = result.raw_response.get('id')
        assert tweet_id

        _delete_tweet(twitter_credentials, tweet_id)


@pytest.mark.functional
@pytest.mark.mutating
class TestTwitterVideoPost:
    """Video upload and posting via TwitterPlatform."""

    def test_video_post(self, twitter_credentials, sample_video):
        from src.platforms.twitter import TwitterPlatform

        tag = uuid.uuid4().hex[:8]
        caption = f'GaleFling video test {tag} — safe to delete'

        platform = TwitterPlatform(_make_auth(twitter_credentials))
        result = platform.post(caption, media_paths=[sample_video])

        assert result.success, f'Video post failed: {result.error_code} — {result.error_message}'
        tweet_id = result.raw_response.get('id')
        assert tweet_id

        _delete_tweet(twitter_credentials, tweet_id)
