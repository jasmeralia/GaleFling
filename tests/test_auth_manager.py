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
