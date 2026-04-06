from pathlib import Path

from src.core.auth_manager import AuthManager


def test_auth_manager_requires_username(tmp_path, monkeypatch):
    monkeypatch.setattr('src.core.auth_manager.get_auth_dir', lambda: tmp_path)
    monkeypatch.setattr(AuthManager, '_find_dev_auth_dir', lambda self: None)
    manager = AuthManager()

    manager.save_twitter_auth('k', 's', 't', 'ts')
    assert manager.get_twitter_auth() is not None
    assert manager.has_twitter_auth() is False

    manager.save_twitter_auth('k', 's', 't', 'ts', username='user')
    assert manager.has_twitter_auth() is True

    manager.save_bluesky_auth('user.bsky.social', 'pw')
    assert manager.has_bluesky_auth() is True

    manager.save_bluesky_auth_alt('alt.bsky.social', 'pw2')
    assert manager.has_bluesky_auth_alt() is True

    manager.clear_bluesky_auth_alt()
    assert manager.has_bluesky_auth_alt() is False


def test_auth_manager_reads_dev_auth(tmp_path, monkeypatch):
    twitter_path = tmp_path / 'twitter_auth.json'
    twitter_path.write_text(
        '{"api_key":"k","api_secret":"s","access_token":"t","access_token_secret":"ts","username":"u"}'
    )
    monkeypatch.setattr('src.core.auth_manager.get_auth_dir', lambda: Path('/missing'))
    monkeypatch.setattr(AuthManager, '_find_dev_auth_dir', lambda self: tmp_path)

    manager = AuthManager()
    data = manager.get_twitter_auth()
    assert data is not None
    assert data.get('username') == 'u'


def _make_auth(tmp_path, monkeypatch) -> AuthManager:
    monkeypatch.setattr('src.core.auth_manager.get_auth_dir', lambda: tmp_path)
    monkeypatch.setattr(AuthManager, '_find_dev_auth_dir', lambda self: None)
    return AuthManager()


def test_meta_threads_app_credentials_round_trip(tmp_path, monkeypatch):
    manager = _make_auth(tmp_path, monkeypatch)

    assert manager.has_meta_threads_app_credentials() is False
    manager.save_meta_threads_app_credentials('th_id', 'th_secret')
    assert manager.has_meta_threads_app_credentials() is True
    creds = manager.get_meta_threads_app_credentials()
    assert creds == {'app_id': 'th_id', 'app_secret': 'th_secret'}


def test_meta_instagram_app_credentials_independent_of_threads(tmp_path, monkeypatch):
    manager = _make_auth(tmp_path, monkeypatch)

    manager.save_meta_instagram_app_credentials('ig_id', 'ig_secret')
    manager.save_meta_threads_app_credentials('th_id', 'th_secret')

    ig = manager.get_meta_instagram_app_credentials()
    th = manager.get_meta_threads_app_credentials()
    assert ig is not None and ig['app_id'] == 'ig_id'
    assert th is not None and th['app_id'] == 'th_id'
    # Confirm stored in separate files
    assert (tmp_path / 'meta_instagram_app_auth.json').exists()
    assert (tmp_path / 'meta_threads_app_auth.json').exists()


def test_meta_facebook_app_credentials_round_trip(tmp_path, monkeypatch):
    manager = _make_auth(tmp_path, monkeypatch)

    assert manager.get_meta_facebook_app_credentials() is None
    manager.save_meta_facebook_app_credentials('fb_id', 'fb_secret')
    creds = manager.get_meta_facebook_app_credentials()
    assert creds is not None and creds['app_id'] == 'fb_id'
    assert manager.has_meta_facebook_app_credentials() is True


def test_twitter_oauth2_credentials_independent_of_oauth1(tmp_path, monkeypatch):
    manager = _make_auth(tmp_path, monkeypatch)

    manager.save_twitter_app_credentials('key1', 'secret1')
    manager.save_twitter_oauth2_app_credentials('cid', 'csecret')

    oauth1 = manager.get_twitter_app_credentials()
    oauth2 = manager.get_twitter_oauth2_app_credentials()
    assert oauth1 is not None and oauth1['api_key'] == 'key1'
    assert oauth2 is not None and oauth2['client_id'] == 'cid'
    assert (tmp_path / 'twitter_app_auth.json').exists()
    assert (tmp_path / 'twitter_oauth2_app_auth.json').exists()


def test_aws_media_staging_credentials_round_trip(tmp_path, monkeypatch):
    manager = _make_auth(tmp_path, monkeypatch)

    assert manager.has_aws_media_staging_credentials() is False
    manager.save_aws_media_staging_credentials('AKID', 'secret', 'us-west-2', 'my-bucket')
    creds = manager.get_aws_media_staging_credentials()
    assert creds is not None
    assert creds['access_key_id'] == 'AKID'
    assert creds['media_staging_bucket'] == 'my-bucket'
    assert creds['region'] == 'us-west-2'
    assert manager.has_aws_media_staging_credentials() is True


def test_meta_oauth_redirect_uri_defaults_to_relay_url(tmp_path, monkeypatch):
    manager = _make_auth(tmp_path, monkeypatch)
    uri = manager.get_meta_oauth_redirect_uri()
    assert uri == 'https://galefling.jasmer.tools/oauth/callback'


def test_meta_oauth_redirect_uri_round_trip(tmp_path, monkeypatch):
    manager = _make_auth(tmp_path, monkeypatch)
    manager.save_meta_oauth_redirect_uri('https://example.com/oauth/callback')
    assert manager.get_meta_oauth_redirect_uri() == 'https://example.com/oauth/callback'


def test_meta_oauth_redirect_uri_stored_in_separate_file(tmp_path, monkeypatch):
    manager = _make_auth(tmp_path, monkeypatch)
    manager.save_meta_oauth_redirect_uri('https://example.com/oauth/callback')
    assert (tmp_path / 'meta_oauth_settings.json').exists()
