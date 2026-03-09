"""Tests for platform client behavior with mocked APIs."""

from __future__ import annotations

from types import SimpleNamespace

from src.platforms.bluesky import BlueskyPlatform
from src.platforms.twitter import TwitterPlatform


class _FakeAuth:
    def __init__(self, twitter=None, bluesky=None):
        self._twitter = twitter
        self._bluesky = bluesky

    def get_twitter_auth(self):
        return self._twitter

    def get_twitter_app_credentials(self):
        if self._twitter:
            return {'api_key': self._twitter['api_key'], 'api_secret': self._twitter['api_secret']}
        return None

    def get_account_credentials(self, account_id):
        return None

    def get_bluesky_auth(self):
        return self._bluesky


class _FakeOAuth:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class _FakeTwitterAPI:
    def __init__(self, auth):
        self.auth = auth

    def media_upload(self, filename):
        return SimpleNamespace(media_id='media123')


class _FakeTwitterClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self._me = SimpleNamespace(data=SimpleNamespace(username='tester'))

    def get_me(self):
        return self._me

    def create_tweet(self, text, media_ids=None):
        return SimpleNamespace(data={'id': 'tweet123'})


class _UnauthorizedError(Exception):
    pass


class _TooManyRequestsError(Exception):
    pass


class _ForbiddenError(Exception):
    pass


def test_twitter_post_success(monkeypatch, tmp_path):
    import src.platforms.twitter as twitter_mod

    fake_tweepy = SimpleNamespace(
        OAuth1UserHandler=_FakeOAuth,
        API=_FakeTwitterAPI,
        Client=_FakeTwitterClient,
        Unauthorized=_UnauthorizedError,
        TooManyRequests=_TooManyRequestsError,
        Forbidden=_ForbiddenError,
    )
    monkeypatch.setattr(twitter_mod, 'tweepy', fake_tweepy)

    auth = _FakeAuth(
        twitter={
            'api_key': 'k',
            'api_secret': 's',
            'access_token': 't',
            'access_token_secret': 'ts',
            'username': 'tester',
        }
    )
    platform = TwitterPlatform(auth)

    image_path = tmp_path / 'image.png'
    image_path.write_bytes(b'data')

    result = platform.post('Hello', media_paths=[image_path])

    assert result.success
    assert result.post_url == 'https://twitter.com/tester/status/tweet123'


def test_twitter_post_multiple_media(monkeypatch, tmp_path):
    import src.platforms.twitter as twitter_mod

    class _RecordingAPI(_FakeTwitterAPI):
        def __init__(self, auth):
            super().__init__(auth)
            self.uploaded = []

        def media_upload(self, filename):
            self.uploaded.append(filename)
            return SimpleNamespace(media_id=f'media{len(self.uploaded)}')

    class _RecordingClient(_FakeTwitterClient):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.last_media_ids = None

        def create_tweet(self, text, media_ids=None):
            self.last_media_ids = media_ids
            return super().create_tweet(text, media_ids)

    fake_tweepy = SimpleNamespace(
        OAuth1UserHandler=_FakeOAuth,
        API=_RecordingAPI,
        Client=_RecordingClient,
        Unauthorized=_UnauthorizedError,
        TooManyRequests=_TooManyRequestsError,
        Forbidden=_ForbiddenError,
    )
    monkeypatch.setattr(twitter_mod, 'tweepy', fake_tweepy)

    auth = _FakeAuth(
        twitter={
            'api_key': 'k',
            'api_secret': 's',
            'access_token': 't',
            'access_token_secret': 'ts',
            'username': 'tester',
        }
    )
    platform = TwitterPlatform(auth)

    image1 = tmp_path / 'image1.png'
    image2 = tmp_path / 'image2.png'
    image1.write_bytes(b'data1')
    image2.write_bytes(b'data2')

    result = platform.post('Hello', media_paths=[image1, image2])

    assert result.success
    assert platform._api_v1.uploaded == [str(image1), str(image2)]
    assert platform._client.last_media_ids == ['media1', 'media2']


def test_twitter_test_connection_unauthorized(monkeypatch):
    import src.platforms.twitter as twitter_mod

    class _BadClient(_FakeTwitterClient):
        def get_me(self):
            raise _UnauthorizedError('nope')

    fake_tweepy = SimpleNamespace(
        OAuth1UserHandler=_FakeOAuth,
        API=_FakeTwitterAPI,
        Client=_BadClient,
        Unauthorized=_UnauthorizedError,
        TooManyRequests=_TooManyRequestsError,
        Forbidden=_ForbiddenError,
    )
    monkeypatch.setattr(twitter_mod, 'tweepy', fake_tweepy)

    auth = _FakeAuth(
        twitter={
            'api_key': 'k',
            'api_secret': 's',
            'access_token': 't',
            'access_token_secret': 'ts',
            'username': 'tester',
        }
    )
    platform = TwitterPlatform(auth)

    success, error = platform.test_connection()

    assert not success
    assert error == 'TW-AUTH-EXPIRED'


class _FakeBskyClient:
    def __init__(self, base_url=None):
        self.base_url = base_url
        self.me = SimpleNamespace(did='did:plc:123', handle='user.bsky.social')
        self.com = SimpleNamespace(
            atproto=SimpleNamespace(repo=SimpleNamespace(create_record=self._create_record))
        )

    def login(self, identifier, app_password):
        self._login = (identifier, app_password)

    def get_profile(self, did):
        return SimpleNamespace(handle='user.bsky.social')

    def upload_blob(self, img_data):
        return SimpleNamespace(blob='blobdata')

    def _create_record(self, data):
        return SimpleNamespace(uri='at://did/app.bsky.feed.post/abc123', cid='cid123')


class _FailingBskyClient(_FakeBskyClient):
    def upload_blob(self, img_data):
        raise RuntimeError('upload failed')


def test_bluesky_post_success(monkeypatch, tmp_path):
    import src.platforms.bluesky as bluesky_mod

    monkeypatch.setattr(bluesky_mod, 'BskyClient', _FakeBskyClient)

    auth = _FakeAuth(
        bluesky={
            'identifier': 'user.bsky.social',
            'app_password': 'pw',
            'service': 'https://bsky.social',
        }
    )
    platform = BlueskyPlatform(auth)

    image_path = tmp_path / 'image.png'
    image_path.write_bytes(b'data')

    result = platform.post('Hello', media_paths=[image_path])

    assert result.success
    assert result.post_url.endswith('/post/abc123')


def test_bluesky_post_multiple_media(monkeypatch, tmp_path):
    import src.platforms.bluesky as bluesky_mod

    class _RecordingBskyClient(_FakeBskyClient):
        def __init__(self, base_url=None):
            super().__init__(base_url)
            self.uploaded_blobs = []
            self.last_create_record_data = None
            self.com = SimpleNamespace(
                atproto=SimpleNamespace(
                    repo=SimpleNamespace(create_record=self._recording_create_record)
                )
            )

        def upload_blob(self, img_data):
            self.uploaded_blobs.append(img_data)
            return SimpleNamespace(blob=f'blob{len(self.uploaded_blobs)}')

        def _recording_create_record(self, data):
            self.last_create_record_data = data
            return SimpleNamespace(uri='at://did/app.bsky.feed.post/abc123', cid='cid123')

    monkeypatch.setattr(bluesky_mod, 'BskyClient', _RecordingBskyClient)

    auth = _FakeAuth(
        bluesky={
            'identifier': 'user.bsky.social',
            'app_password': 'pw',
            'service': 'https://bsky.social',
        }
    )
    platform = BlueskyPlatform(auth)

    image1 = tmp_path / 'image1.png'
    image2 = tmp_path / 'image2.png'
    image1.write_bytes(b'data1')
    image2.write_bytes(b'data2')

    result = platform.post('Hello', media_paths=[image1, image2])

    assert result.success
    assert len(platform._client.uploaded_blobs) == 2
    embed_images = platform._client.last_create_record_data['record']['embed']['images']
    assert len(embed_images) == 2
    assert embed_images[0]['image'] == 'blob1'
    assert embed_images[1]['image'] == 'blob2'


def test_bluesky_image_upload_failure(monkeypatch, tmp_path):
    import src.platforms.bluesky as bluesky_mod

    monkeypatch.setattr(bluesky_mod, 'BskyClient', _FailingBskyClient)

    auth = _FakeAuth(
        bluesky={
            'identifier': 'user.bsky.social',
            'app_password': 'pw',
            'service': 'https://bsky.social',
        }
    )
    platform = BlueskyPlatform(auth)

    image_path = tmp_path / 'image.png'
    image_path.write_bytes(b'data')

    result = platform.post('Hello', media_paths=[image_path])

    assert not result.success
    assert result.error_code == 'IMG-UPLOAD-FAILED'


# ── Additional Twitter tests ──────────────────────────────────────


def test_twitter_authenticate_missing_creds(monkeypatch):
    import src.platforms.twitter as twitter_mod

    fake_tweepy = SimpleNamespace(
        OAuth1UserHandler=_FakeOAuth,
        API=_FakeTwitterAPI,
        Client=_FakeTwitterClient,
        Unauthorized=_UnauthorizedError,
        TooManyRequests=_TooManyRequestsError,
        Forbidden=_ForbiddenError,
    )
    monkeypatch.setattr(twitter_mod, 'tweepy', fake_tweepy)

    auth = _FakeAuth()
    platform = TwitterPlatform(auth)

    success, error = platform.authenticate()
    assert not success
    assert error == 'AUTH-MISSING'


def test_twitter_post_no_auth(monkeypatch):
    import src.platforms.twitter as twitter_mod

    fake_tweepy = SimpleNamespace(
        OAuth1UserHandler=_FakeOAuth,
        API=_FakeTwitterAPI,
        Client=_FakeTwitterClient,
        Unauthorized=_UnauthorizedError,
        TooManyRequests=_TooManyRequestsError,
        Forbidden=_ForbiddenError,
    )
    monkeypatch.setattr(twitter_mod, 'tweepy', fake_tweepy)

    auth = _FakeAuth()
    platform = TwitterPlatform(auth)

    result = platform.post('Hello')
    assert not result.success
    assert result.error_code == 'AUTH-MISSING'


def test_twitter_post_text_only(monkeypatch):
    import src.platforms.twitter as twitter_mod

    fake_tweepy = SimpleNamespace(
        OAuth1UserHandler=_FakeOAuth,
        API=_FakeTwitterAPI,
        Client=_FakeTwitterClient,
        Unauthorized=_UnauthorizedError,
        TooManyRequests=_TooManyRequestsError,
        Forbidden=_ForbiddenError,
    )
    monkeypatch.setattr(twitter_mod, 'tweepy', fake_tweepy)

    auth = _FakeAuth(
        twitter={
            'api_key': 'k',
            'api_secret': 's',
            'access_token': 't',
            'access_token_secret': 'ts',
        }
    )
    platform = TwitterPlatform(auth)

    result = platform.post('Text only tweet')
    assert result.success
    assert 'tweet123' in result.post_url


def test_twitter_post_rate_limited(monkeypatch):
    import src.platforms.twitter as twitter_mod

    class _RateLimitedClient(_FakeTwitterClient):
        def create_tweet(self, text, media_ids=None):
            raise _TooManyRequestsError('rate limit')

    fake_tweepy = SimpleNamespace(
        OAuth1UserHandler=_FakeOAuth,
        API=_FakeTwitterAPI,
        Client=_RateLimitedClient,
        Unauthorized=_UnauthorizedError,
        TooManyRequests=_TooManyRequestsError,
        Forbidden=_ForbiddenError,
    )
    monkeypatch.setattr(twitter_mod, 'tweepy', fake_tweepy)

    auth = _FakeAuth(
        twitter={
            'api_key': 'k',
            'api_secret': 's',
            'access_token': 't',
            'access_token_secret': 'ts',
        }
    )
    platform = TwitterPlatform(auth)

    result = platform.post('Hello')
    assert not result.success
    assert result.error_code == 'TW-RATE-LIMIT'


def test_twitter_post_duplicate(monkeypatch):
    import src.platforms.twitter as twitter_mod

    class _DuplicateClient(_FakeTwitterClient):
        def create_tweet(self, text, media_ids=None):
            raise _ForbiddenError('Status is a duplicate.')

    fake_tweepy = SimpleNamespace(
        OAuth1UserHandler=_FakeOAuth,
        API=_FakeTwitterAPI,
        Client=_DuplicateClient,
        Unauthorized=_UnauthorizedError,
        TooManyRequests=_TooManyRequestsError,
        Forbidden=_ForbiddenError,
    )
    monkeypatch.setattr(twitter_mod, 'tweepy', fake_tweepy)

    auth = _FakeAuth(
        twitter={
            'api_key': 'k',
            'api_secret': 's',
            'access_token': 't',
            'access_token_secret': 'ts',
        }
    )
    platform = TwitterPlatform(auth)

    result = platform.post('Hello')
    assert not result.success
    assert result.error_code == 'POST-DUPLICATE'


def test_twitter_post_unauthorized(monkeypatch):
    import src.platforms.twitter as twitter_mod

    class _UnauthorizedClient(_FakeTwitterClient):
        def create_tweet(self, text, media_ids=None):
            raise _UnauthorizedError('expired')

    fake_tweepy = SimpleNamespace(
        OAuth1UserHandler=_FakeOAuth,
        API=_FakeTwitterAPI,
        Client=_UnauthorizedClient,
        Unauthorized=_UnauthorizedError,
        TooManyRequests=_TooManyRequestsError,
        Forbidden=_ForbiddenError,
    )
    monkeypatch.setattr(twitter_mod, 'tweepy', fake_tweepy)

    auth = _FakeAuth(
        twitter={
            'api_key': 'k',
            'api_secret': 's',
            'access_token': 't',
            'access_token_secret': 'ts',
        }
    )
    platform = TwitterPlatform(auth)

    result = platform.post('Hello')
    assert not result.success
    assert result.error_code == 'TW-AUTH-EXPIRED'


def test_twitter_post_media_rate_limited(monkeypatch, tmp_path):
    import src.platforms.twitter as twitter_mod

    class _RateLimitedAPI(_FakeTwitterAPI):
        def media_upload(self, filename):
            raise _TooManyRequestsError('rate limit')

    fake_tweepy = SimpleNamespace(
        OAuth1UserHandler=_FakeOAuth,
        API=_RateLimitedAPI,
        Client=_FakeTwitterClient,
        Unauthorized=_UnauthorizedError,
        TooManyRequests=_TooManyRequestsError,
        Forbidden=_ForbiddenError,
    )
    monkeypatch.setattr(twitter_mod, 'tweepy', fake_tweepy)

    auth = _FakeAuth(
        twitter={
            'api_key': 'k',
            'api_secret': 's',
            'access_token': 't',
            'access_token_secret': 'ts',
        }
    )
    platform = TwitterPlatform(auth)

    image_path = tmp_path / 'image.png'
    image_path.write_bytes(b'data')

    result = platform.post('Hello', media_paths=[image_path])
    assert not result.success
    assert result.error_code == 'TW-RATE-LIMIT'


def test_twitter_test_connection_rate_limited(monkeypatch):
    import src.platforms.twitter as twitter_mod

    class _RateLimitedClient(_FakeTwitterClient):
        def get_me(self):
            raise _TooManyRequestsError('rate limit')

    fake_tweepy = SimpleNamespace(
        OAuth1UserHandler=_FakeOAuth,
        API=_FakeTwitterAPI,
        Client=_RateLimitedClient,
        Unauthorized=_UnauthorizedError,
        TooManyRequests=_TooManyRequestsError,
        Forbidden=_ForbiddenError,
    )
    monkeypatch.setattr(twitter_mod, 'tweepy', fake_tweepy)

    auth = _FakeAuth(
        twitter={
            'api_key': 'k',
            'api_secret': 's',
            'access_token': 't',
            'access_token_secret': 'ts',
        }
    )
    platform = TwitterPlatform(auth)

    success, error = platform.test_connection()
    assert not success
    assert error == 'TW-RATE-LIMIT'


def test_twitter_test_connection_success(monkeypatch):
    import src.platforms.twitter as twitter_mod

    fake_tweepy = SimpleNamespace(
        OAuth1UserHandler=_FakeOAuth,
        API=_FakeTwitterAPI,
        Client=_FakeTwitterClient,
        Unauthorized=_UnauthorizedError,
        TooManyRequests=_TooManyRequestsError,
        Forbidden=_ForbiddenError,
    )
    monkeypatch.setattr(twitter_mod, 'tweepy', fake_tweepy)

    auth = _FakeAuth(
        twitter={
            'api_key': 'k',
            'api_secret': 's',
            'access_token': 't',
            'access_token_secret': 'ts',
        }
    )
    platform = TwitterPlatform(auth)

    success, error = platform.test_connection()
    assert success
    assert error is None


def test_twitter_platform_name():
    auth = _FakeAuth()
    platform = TwitterPlatform(auth, profile_name='myuser')
    assert platform.get_platform_name() == 'Twitter (myuser)'


def test_twitter_platform_name_no_profile():
    auth = _FakeAuth()
    platform = TwitterPlatform(auth)
    assert platform.get_platform_name() == 'Twitter'


def test_twitter_get_specs():
    auth = _FakeAuth()
    platform = TwitterPlatform(auth)
    specs = platform.get_specs()
    assert specs.platform_name == 'Twitter'
    assert specs.max_text_length == 280


# ── Additional Bluesky tests ──────────────────────────────────────


def test_bluesky_authenticate_missing_creds(monkeypatch):
    import src.platforms.bluesky as bluesky_mod

    monkeypatch.setattr(bluesky_mod, 'BskyClient', _FakeBskyClient)

    auth = _FakeAuth()
    platform = BlueskyPlatform(auth)

    success, error = platform.authenticate()
    assert not success
    assert error == 'AUTH-MISSING'


def test_bluesky_authenticate_invalid(monkeypatch):
    import src.platforms.bluesky as bluesky_mod

    class _BadBskyClient(_FakeBskyClient):
        def login(self, identifier, app_password):
            raise RuntimeError('Invalid authentication credentials')

    monkeypatch.setattr(bluesky_mod, 'BskyClient', _BadBskyClient)

    auth = _FakeAuth(bluesky={'identifier': 'user.bsky.social', 'app_password': 'pw'})
    platform = BlueskyPlatform(auth)

    success, error = platform.authenticate()
    assert not success
    assert error == 'BS-AUTH-INVALID'


def test_bluesky_authenticate_expired(monkeypatch):
    import src.platforms.bluesky as bluesky_mod

    class _ExpiredBskyClient(_FakeBskyClient):
        def login(self, identifier, app_password):
            raise RuntimeError('Token expired')

    monkeypatch.setattr(bluesky_mod, 'BskyClient', _ExpiredBskyClient)

    auth = _FakeAuth(bluesky={'identifier': 'user.bsky.social', 'app_password': 'pw'})
    platform = BlueskyPlatform(auth)

    success, error = platform.authenticate()
    assert not success
    assert error == 'BS-AUTH-EXPIRED'


def test_bluesky_test_connection_success(monkeypatch):
    import src.platforms.bluesky as bluesky_mod

    monkeypatch.setattr(bluesky_mod, 'BskyClient', _FakeBskyClient)

    auth = _FakeAuth(bluesky={'identifier': 'user.bsky.social', 'app_password': 'pw'})
    platform = BlueskyPlatform(auth)

    success, error = platform.test_connection()
    assert success
    assert error is None


def test_bluesky_test_connection_failure(monkeypatch):
    import src.platforms.bluesky as bluesky_mod

    class _FailProfileClient(_FakeBskyClient):
        def get_profile(self, did):
            raise RuntimeError('profile fetch failed')

    monkeypatch.setattr(bluesky_mod, 'BskyClient', _FailProfileClient)

    auth = _FakeAuth(bluesky={'identifier': 'user.bsky.social', 'app_password': 'pw'})
    platform = BlueskyPlatform(auth)

    success, error = platform.test_connection()
    assert not success
    assert error == 'BS-AUTH-INVALID'


def test_bluesky_post_text_only(monkeypatch):
    import src.platforms.bluesky as bluesky_mod

    monkeypatch.setattr(bluesky_mod, 'BskyClient', _FakeBskyClient)

    auth = _FakeAuth(bluesky={'identifier': 'user.bsky.social', 'app_password': 'pw'})
    platform = BlueskyPlatform(auth)

    result = platform.post('Text only')
    assert result.success
    assert result.post_url.endswith('/post/abc123')


def test_bluesky_post_with_url_in_text(monkeypatch):
    import src.platforms.bluesky as bluesky_mod

    monkeypatch.setattr(bluesky_mod, 'BskyClient', _FakeBskyClient)

    auth = _FakeAuth(bluesky={'identifier': 'user.bsky.social', 'app_password': 'pw'})
    platform = BlueskyPlatform(auth)

    result = platform.post('Check out https://example.com')
    assert result.success


def test_bluesky_post_no_auth(monkeypatch):
    import src.platforms.bluesky as bluesky_mod

    monkeypatch.setattr(bluesky_mod, 'BskyClient', _FakeBskyClient)

    auth = _FakeAuth()
    platform = BlueskyPlatform(auth)

    result = platform.post('Hello')
    assert not result.success
    assert result.error_code == 'AUTH-MISSING'


def test_bluesky_post_rate_limit(monkeypatch):
    import src.platforms.bluesky as bluesky_mod

    class _RateLimitClient(_FakeBskyClient):
        def __init__(self, base_url=None):
            super().__init__(base_url)
            self.com = SimpleNamespace(
                atproto=SimpleNamespace(repo=SimpleNamespace(create_record=self._create_record))
            )

        def _create_record(self, data):
            raise RuntimeError('Rate limit exceeded')

    monkeypatch.setattr(bluesky_mod, 'BskyClient', _RateLimitClient)

    auth = _FakeAuth(bluesky={'identifier': 'user.bsky.social', 'app_password': 'pw'})
    platform = BlueskyPlatform(auth)

    result = platform.post('Hello')
    assert not result.success
    assert result.error_code == 'BS-RATE-LIMIT'


def test_bluesky_platform_name_alt():
    auth = _FakeAuth(bluesky={'identifier': 'user.bsky.social', 'app_password': 'pw'})
    platform = BlueskyPlatform(auth, account_key='alt')
    assert platform.get_platform_name() == 'Bluesky (Alt)'


def test_bluesky_platform_name_with_profile():
    auth = _FakeAuth(bluesky={'identifier': 'user.bsky.social', 'app_password': 'pw'})
    platform = BlueskyPlatform(auth, profile_name='myhandle')
    assert platform.get_platform_name() == 'Bluesky (myhandle)'


def test_bluesky_platform_name_default():
    auth = _FakeAuth()
    platform = BlueskyPlatform(auth)
    assert platform.get_platform_name() == 'Bluesky'


def test_bluesky_detect_urls():
    from src.platforms.bluesky import detect_urls

    facets = detect_urls('Check https://example.com and more')
    assert len(facets) == 1
    assert facets[0]['features'][0]['uri'] == 'https://example.com'


def test_bluesky_detect_urls_empty():
    from src.platforms.bluesky import detect_urls

    facets = detect_urls('No URLs here')
    assert facets == []


def test_bluesky_detect_urls_multiple():
    from src.platforms.bluesky import detect_urls

    facets = detect_urls('Visit https://a.com and http://b.com')
    assert len(facets) == 2


def test_bluesky_detect_urls_unicode():
    from src.platforms.bluesky import detect_urls

    text = '\u2728 https://example.com'
    facets = detect_urls(text)
    assert len(facets) == 1
    # Verify byte offsets are correct for UTF-8
    byte_start = facets[0]['index']['byteStart']
    assert byte_start == len('\u2728 '.encode())
