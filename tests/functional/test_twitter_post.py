"""Functional tests for Twitter — real API calls against a test account."""

import uuid

import pytest
import tweepy


@pytest.mark.functional
class TestTwitterConnection:
    """Auth and connection tests — run first to fail fast on bad credentials."""

    def _make_client(self, twitter_credentials):
        return tweepy.Client(
            consumer_key=twitter_credentials['TWITTER_API_KEY'],
            consumer_secret=twitter_credentials['TWITTER_API_SECRET'],
            access_token=twitter_credentials['TWITTER_ACCESS_TOKEN'],
            access_token_secret=twitter_credentials['TWITTER_ACCESS_TOKEN_SECRET'],
        )

    def _make_api_v1(self, twitter_credentials):
        auth = tweepy.OAuth1UserHandler(
            twitter_credentials['TWITTER_API_KEY'],
            twitter_credentials['TWITTER_API_SECRET'],
            twitter_credentials['TWITTER_ACCESS_TOKEN'],
            twitter_credentials['TWITTER_ACCESS_TOKEN_SECRET'],
        )
        return tweepy.API(auth)

    def test_authenticate(self, twitter_credentials):
        """Verify OAuth 1.0a credentials are accepted."""
        client = self._make_client(twitter_credentials)
        me = client.get_me()
        assert me and me.data
        assert me.data.username

    def test_v1_api_verify(self, twitter_credentials):
        """Verify the v1.1 API auth handler works (needed for media uploads)."""
        api = self._make_api_v1(twitter_credentials)
        user = api.verify_credentials()
        assert user.screen_name


@pytest.mark.functional
class TestTwitterTextPost:
    """Text-only posting and deletion."""

    def test_text_post_and_delete(self, twitter_credentials):
        """Create a text tweet, verify it has an ID, then delete it."""
        client = tweepy.Client(
            consumer_key=twitter_credentials['TWITTER_API_KEY'],
            consumer_secret=twitter_credentials['TWITTER_API_SECRET'],
            access_token=twitter_credentials['TWITTER_ACCESS_TOKEN'],
            access_token_secret=twitter_credentials['TWITTER_ACCESS_TOKEN_SECRET'],
        )
        tag = uuid.uuid4().hex[:8]
        text = f'GaleFling functional test {tag} — safe to delete'

        response = client.create_tweet(text=text)
        assert response and response.data
        tweet_id = response.data['id']
        assert tweet_id

        # Cleanup
        client.delete_tweet(tweet_id)

    def test_character_limit_enforcement(self, twitter_credentials):
        """Verify the API rejects posts exceeding 280 characters."""
        client = tweepy.Client(
            consumer_key=twitter_credentials['TWITTER_API_KEY'],
            consumer_secret=twitter_credentials['TWITTER_API_SECRET'],
            access_token=twitter_credentials['TWITTER_ACCESS_TOKEN'],
            access_token_secret=twitter_credentials['TWITTER_ACCESS_TOKEN_SECRET'],
        )
        text = 'A' * 281
        posted = False
        try:
            client.create_tweet(text=text)
            posted = True
        except Exception:
            pass
        assert not posted, 'Expected Twitter to reject post exceeding 280 characters'


@pytest.mark.functional
class TestTwitterImagePost:
    """Image upload and posting."""

    def test_single_image_post(self, twitter_credentials, sample_jpeg):
        """Upload an image via v1.1 API, attach to a tweet, then delete."""
        auth = tweepy.OAuth1UserHandler(
            twitter_credentials['TWITTER_API_KEY'],
            twitter_credentials['TWITTER_API_SECRET'],
            twitter_credentials['TWITTER_ACCESS_TOKEN'],
            twitter_credentials['TWITTER_ACCESS_TOKEN_SECRET'],
        )
        api_v1 = tweepy.API(auth)
        client = tweepy.Client(
            consumer_key=twitter_credentials['TWITTER_API_KEY'],
            consumer_secret=twitter_credentials['TWITTER_API_SECRET'],
            access_token=twitter_credentials['TWITTER_ACCESS_TOKEN'],
            access_token_secret=twitter_credentials['TWITTER_ACCESS_TOKEN_SECRET'],
        )

        tag = uuid.uuid4().hex[:8]
        media = api_v1.media_upload(filename=str(sample_jpeg))
        assert media.media_id

        response = client.create_tweet(
            text=f'GaleFling image test {tag} — safe to delete',
            media_ids=[media.media_id],
        )
        assert response and response.data
        tweet_id = response.data['id']

        # Cleanup
        client.delete_tweet(tweet_id)

    def test_multiple_images_post(self, twitter_credentials, sample_jpeg, sample_png):
        """Upload two images and attach them to a single tweet, then delete."""
        auth = tweepy.OAuth1UserHandler(
            twitter_credentials['TWITTER_API_KEY'],
            twitter_credentials['TWITTER_API_SECRET'],
            twitter_credentials['TWITTER_ACCESS_TOKEN'],
            twitter_credentials['TWITTER_ACCESS_TOKEN_SECRET'],
        )
        api_v1 = tweepy.API(auth)
        client = tweepy.Client(
            consumer_key=twitter_credentials['TWITTER_API_KEY'],
            consumer_secret=twitter_credentials['TWITTER_API_SECRET'],
            access_token=twitter_credentials['TWITTER_ACCESS_TOKEN'],
            access_token_secret=twitter_credentials['TWITTER_ACCESS_TOKEN_SECRET'],
        )

        tag = uuid.uuid4().hex[:8]
        media_ids = []
        for path in [sample_jpeg, sample_png]:
            media = api_v1.media_upload(filename=str(path))
            media_ids.append(media.media_id)

        response = client.create_tweet(
            text=f'GaleFling multi-image test {tag} — safe to delete',
            media_ids=media_ids,
        )
        assert response and response.data
        tweet_id = response.data['id']

        # Cleanup
        client.delete_tweet(tweet_id)


@pytest.mark.functional
class TestTwitterVideoPost:
    """Video upload and posting."""

    def test_video_post(self, twitter_credentials, sample_video):
        """Upload a short video via chunked upload, tweet it, then delete."""
        auth = tweepy.OAuth1UserHandler(
            twitter_credentials['TWITTER_API_KEY'],
            twitter_credentials['TWITTER_API_SECRET'],
            twitter_credentials['TWITTER_ACCESS_TOKEN'],
            twitter_credentials['TWITTER_ACCESS_TOKEN_SECRET'],
        )
        api_v1 = tweepy.API(auth)
        client = tweepy.Client(
            consumer_key=twitter_credentials['TWITTER_API_KEY'],
            consumer_secret=twitter_credentials['TWITTER_API_SECRET'],
            access_token=twitter_credentials['TWITTER_ACCESS_TOKEN'],
            access_token_secret=twitter_credentials['TWITTER_ACCESS_TOKEN_SECRET'],
        )

        tag = uuid.uuid4().hex[:8]
        media = api_v1.media_upload(
            filename=str(sample_video),
            media_category='tweet_video',
        )
        assert media.media_id

        response = client.create_tweet(
            text=f'GaleFling video test {tag} — safe to delete',
            media_ids=[media.media_id],
        )
        assert response and response.data
        tweet_id = response.data['id']

        # Cleanup
        client.delete_tweet(tweet_id)
