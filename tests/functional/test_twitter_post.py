"""Functional tests for Twitter — live API calls via TwitterPlatform."""

from __future__ import annotations

import time

import pytest
import tweepy

from tests.functional.conftest import mutating_post_text
from tests.functional.functional_cleanup import (
    ArtifactAlreadyGoneError,
    assert_neutral_live_text,
    finish_mutating_artifact,
    post_tag,
)


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


def _fetch_tweet(creds: dict, tweet_id: str) -> tuple[object | None, list[str]]:
    """Read a published tweet back from Twitter, returning it and its media types.

    ``user_auth=True`` is mandatory and is the entire point of this helper. tweepy's read
    methods default to ``user_auth=False``, which authenticates with an OAuth 2.0 app-only
    bearer token; this client is built from OAuth 1.0a credentials and carries no bearer
    token, so the default produces a 401 that looks exactly like "tweet lookup is not
    available on your access tier". The write methods (``create_tweet``, ``delete_tweet``)
    default to ``user_auth=True``, which is why posting works while a naive read does not.

    Retried briefly: the tweet is live the moment ``create_tweet`` returns, but a live
    network test that flakes on a single cold read is worse than one that waits 8s.
    """
    client = _make_client(creds)
    for attempt in range(5):
        resp = client.get_tweets(
            [tweet_id],
            tweet_fields=['text'],
            expansions=['attachments.media_keys'],
            media_fields=['type'],
            user_auth=True,
        )
        if resp.data:
            return resp.data[0], [m.type for m in (resp.includes or {}).get('media', [])]
        if attempt < 4:
            time.sleep(2)
    return None, []


def _assert_tweet_published(
    creds: dict, tweet_id: str, text: str, *, media: list[str] | None = None
) -> None:
    """Prove the tweet exists on Twitter carrying our tag and media.

    A returned ID and ``result.success`` are not evidence that anything was published —
    they are the adapter reporting on itself. Only reading the artifact back off the
    platform settles it.
    """
    tag = post_tag(text)
    tweet, media_types = _fetch_tweet(creds, tweet_id)

    assert tweet is not None, (
        f'Twitter returned tweet id {tweet_id} but will not serve it back — '
        f'nothing was published under tag {tag}'
    )
    assert tag in tweet.text, (
        f'Tweet {tweet_id} does not carry tag {tag} — this is not the post we just '
        f'created: {tweet.text!r}'
    )

    assert_neutral_live_text('Twitter', tweet.text)

    expected = sorted(media or [])
    assert sorted(media_types) == expected, (
        f'Tweet {tweet_id} (tag {tag}) published media {sorted(media_types)}, expected {expected}'
    )


def _delete_tweet(creds: dict, tweet_id: str) -> None:
    """Delete a tweet by ID, in the outcome vocabulary the shared reporter expects."""
    try:
        _make_client(creds).delete_tweet(tweet_id)
    except tweepy.NotFound as exc:
        raise ArtifactAlreadyGoneError from exc


def _finish_tweet(creds: dict, text: str, tweet_id: str, url: str | None = None) -> None:
    """Delete the tweet, or leave it up and report it, per the run's cleanup policy."""
    finish_mutating_artifact(
        'Twitter',
        text,
        url=url,
        delete=lambda: _delete_tweet(creds, tweet_id),
    )


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
    """Text-only posting via TwitterPlatform."""

    def test_text_post(self, twitter_credentials):
        from src.platforms.twitter import TwitterPlatform

        text = mutating_post_text()

        platform = TwitterPlatform(_make_auth(twitter_credentials))
        result = platform.post(text)

        assert result.success, f'Text post failed: {result.error_code} — {result.error_message}'
        assert result.platform == 'Twitter'
        tweet_id = result.raw_response.get('id')
        assert tweet_id
        # Unconditional: a guarded URL assertion cannot fail when post_url is None,
        # which is precisely the regression worth catching — the Results dialog then
        # has no link to offer the user. Facebook Page video posts shipped in exactly
        # that state, and no test caught it; the artifact reporter did, by printing
        # 'URL: none reported'.
        assert result.post_url, 'no post_url returned — Results would have no link'
        assert 'twitter.com/' in result.post_url or 'x.com/' in result.post_url

        _assert_tweet_published(twitter_credentials, tweet_id, text)
        _finish_tweet(twitter_credentials, text, tweet_id, result.post_url)


@pytest.mark.functional
@pytest.mark.mutating
class TestTwitterImagePost:
    """Image upload and posting via TwitterPlatform."""

    def test_single_image_post(self, twitter_credentials, sample_jpeg):
        from src.platforms.twitter import TwitterPlatform

        caption = mutating_post_text()

        platform = TwitterPlatform(_make_auth(twitter_credentials))
        result = platform.post(caption, media_paths=[sample_jpeg])

        assert result.success, f'Image post failed: {result.error_code} — {result.error_message}'
        tweet_id = result.raw_response.get('id')
        assert tweet_id

        _assert_tweet_published(twitter_credentials, tweet_id, caption, media=['photo'])
        _finish_tweet(twitter_credentials, caption, tweet_id, result.post_url)

    def test_png_image_post(self, twitter_credentials, sample_png):
        from src.platforms.twitter import TwitterPlatform

        caption = mutating_post_text()

        platform = TwitterPlatform(_make_auth(twitter_credentials))
        result = platform.post(caption, media_paths=[sample_png])

        assert result.success, f'PNG post failed: {result.error_code} — {result.error_message}'
        tweet_id = result.raw_response.get('id')
        assert tweet_id

        _assert_tweet_published(twitter_credentials, tweet_id, caption, media=['photo'])
        _finish_tweet(twitter_credentials, caption, tweet_id, result.post_url)

    def test_multiple_images_post(self, twitter_credentials, sample_jpeg, sample_png):
        from src.platforms.twitter import TwitterPlatform

        caption = mutating_post_text()

        platform = TwitterPlatform(_make_auth(twitter_credentials))
        result = platform.post(caption, media_paths=[sample_jpeg, sample_png])

        assert result.success, (
            f'Multi-image post failed: {result.error_code} — {result.error_message}'
        )
        tweet_id = result.raw_response.get('id')
        assert tweet_id

        _assert_tweet_published(twitter_credentials, tweet_id, caption, media=['photo', 'photo'])
        _finish_tweet(twitter_credentials, caption, tweet_id, result.post_url)


@pytest.mark.functional
@pytest.mark.mutating
class TestTwitterVideoPost:
    """Video upload and posting via TwitterPlatform."""

    def test_video_post(self, twitter_credentials, sample_video):
        from src.platforms.twitter import TwitterPlatform

        caption = mutating_post_text()

        platform = TwitterPlatform(_make_auth(twitter_credentials))
        result = platform.post(caption, media_paths=[sample_video])

        assert result.success, f'Video post failed: {result.error_code} — {result.error_message}'
        tweet_id = result.raw_response.get('id')
        assert tweet_id

        _assert_tweet_published(twitter_credentials, tweet_id, caption, media=['video'])
        _finish_tweet(twitter_credentials, caption, tweet_id, result.post_url)
