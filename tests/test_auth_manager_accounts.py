"""Tests for Phase 1 account-based auth manager API."""

import pytest

from src.core.auth_manager import AuthManager
from src.utils.constants import AccountConfig


@pytest.fixture
def fresh_auth_dir(tmp_path, request):
    """Create a fresh auth directory for each test."""
    auth_dir = tmp_path / f'auth_{request.node.name}'
    auth_dir.mkdir(parents=True, exist_ok=True)
    return auth_dir


def test_add_and_get_accounts(fresh_auth_dir, monkeypatch):
    """Test adding and retrieving accounts."""
    monkeypatch.setattr('src.core.auth_manager.get_auth_dir', lambda: fresh_auth_dir)
    monkeypatch.setattr('src.core.auth_manager.get_app_data_dir', lambda: fresh_auth_dir)
    monkeypatch.setattr(AuthManager, '_find_dev_auth_dir', lambda self: None)
    manager = AuthManager()

    # Add accounts
    twitter_account = AccountConfig(
        platform_id='twitter',
        account_id='twitter_1',
        profile_name='testuser',
    )
    bluesky_account = AccountConfig(
        platform_id='bluesky',
        account_id='bluesky_1',
        profile_name='test.bsky.social',
    )

    manager.add_account(twitter_account)
    manager.add_account(bluesky_account)

    # Retrieve all accounts
    accounts = manager.get_accounts()
    assert len(accounts) == 2
    assert any(a.account_id == 'twitter_1' for a in accounts)
    assert any(a.account_id == 'bluesky_1' for a in accounts)


def test_get_account_by_id(fresh_auth_dir, monkeypatch):
    """Test retrieving a specific account by ID."""
    monkeypatch.setattr('src.core.auth_manager.get_auth_dir', lambda: fresh_auth_dir)
    monkeypatch.setattr('src.core.auth_manager.get_app_data_dir', lambda: fresh_auth_dir)
    monkeypatch.setattr(AuthManager, '_find_dev_auth_dir', lambda self: None)
    manager = AuthManager()

    account = AccountConfig(
        platform_id='instagram',
        account_id='instagram_1',
        profile_name='testuser',
    )
    manager.add_account(account)

    retrieved = manager.get_account('instagram_1')
    assert retrieved is not None
    assert retrieved.account_id == 'instagram_1'
    assert retrieved.profile_name == 'testuser'

    # Non-existent account
    assert manager.get_account('nonexistent') is None


def test_remove_account(fresh_auth_dir, monkeypatch):
    """Test removing an account."""
    monkeypatch.setattr('src.core.auth_manager.get_auth_dir', lambda: fresh_auth_dir)
    monkeypatch.setattr('src.core.auth_manager.get_app_data_dir', lambda: fresh_auth_dir)
    monkeypatch.setattr(AuthManager, '_find_dev_auth_dir', lambda self: None)
    manager = AuthManager()

    account = AccountConfig(
        platform_id='snapchat',
        account_id='snapchat_1',
        profile_name='snap_user',
    )
    manager.add_account(account)
    assert manager.get_account('snapchat_1') is not None

    manager.remove_account('snapchat_1')
    assert manager.get_account('snapchat_1') is None


def test_get_accounts_for_platform(fresh_auth_dir, monkeypatch):
    """Test retrieving all accounts for a specific platform."""
    monkeypatch.setattr('src.core.auth_manager.get_auth_dir', lambda: fresh_auth_dir)
    monkeypatch.setattr('src.core.auth_manager.get_app_data_dir', lambda: fresh_auth_dir)
    monkeypatch.setattr(AuthManager, '_find_dev_auth_dir', lambda self: None)
    manager = AuthManager()

    twitter1 = AccountConfig(
        platform_id='twitter',
        account_id='twitter_1',
        profile_name='user1',
    )
    twitter2 = AccountConfig(
        platform_id='twitter',
        account_id='twitter_2',
        profile_name='user2',
    )
    bluesky1 = AccountConfig(
        platform_id='bluesky',
        account_id='bluesky_1',
        profile_name='user.bsky.social',
    )

    manager.add_account(twitter1)
    manager.add_account(twitter2)
    manager.add_account(bluesky1)

    twitter_accounts = manager.get_accounts_for_platform('twitter')
    assert len(twitter_accounts) == 2
    assert all(a.platform_id == 'twitter' for a in twitter_accounts)

    bluesky_accounts = manager.get_accounts_for_platform('bluesky')
    assert len(bluesky_accounts) == 1


def test_save_and_get_account_credentials(fresh_auth_dir, monkeypatch):
    """Test saving and retrieving account credentials."""
    monkeypatch.setattr('src.core.auth_manager.get_auth_dir', lambda: fresh_auth_dir)
    monkeypatch.setattr('src.core.auth_manager.get_app_data_dir', lambda: fresh_auth_dir)
    monkeypatch.setattr(AuthManager, '_find_dev_auth_dir', lambda self: None)
    manager = AuthManager()

    # Save credentials
    creds = {
        'access_token': 'token123',
        'ig_user_id': 'user456',
        'page_id': 'page789',
    }
    manager.save_account_credentials('instagram_1', creds)

    # Retrieve credentials
    retrieved = manager.get_account_credentials('instagram_1')
    assert retrieved is not None
    assert retrieved['access_token'] == 'token123'
    assert retrieved['ig_user_id'] == 'user456'


def test_clear_account_credentials(fresh_auth_dir, monkeypatch):
    """Test clearing account credentials."""
    monkeypatch.setattr('src.core.auth_manager.get_auth_dir', lambda: fresh_auth_dir)
    monkeypatch.setattr('src.core.auth_manager.get_app_data_dir', lambda: fresh_auth_dir)
    monkeypatch.setattr(AuthManager, '_find_dev_auth_dir', lambda self: None)
    manager = AuthManager()

    creds = {'access_token': 'token'}
    manager.save_account_credentials('onlyfans_1', creds)
    assert manager.get_account_credentials('onlyfans_1') is not None

    manager.clear_account_credentials('onlyfans_1')
    assert manager.get_account_credentials('onlyfans_1') is None


def test_accounts_persisted_to_file(fresh_auth_dir, monkeypatch):
    """Test that accounts are persisted to accounts_config.json."""
    monkeypatch.setattr('src.core.auth_manager.get_auth_dir', lambda: fresh_auth_dir)
    monkeypatch.setattr('src.core.auth_manager.get_app_data_dir', lambda: fresh_auth_dir)
    monkeypatch.setattr(AuthManager, '_find_dev_auth_dir', lambda self: None)
    manager = AuthManager()

    account = AccountConfig(
        platform_id='fetlife',
        account_id='fetlife_1',
        profile_name='fetuser',
    )
    manager.add_account(account)

    # Create a new manager instance to test persistence
    manager2 = AuthManager()
    accounts = manager2.get_accounts()
    assert len(accounts) == 1
    assert accounts[0].account_id == 'fetlife_1'


def test_set_account_enabled_persists(fresh_auth_dir, monkeypatch):
    """Test toggling account enabled state persists to accounts_config.json."""
    monkeypatch.setattr('src.core.auth_manager.get_auth_dir', lambda: fresh_auth_dir)
    monkeypatch.setattr('src.core.auth_manager.get_app_data_dir', lambda: fresh_auth_dir)
    monkeypatch.setattr(AuthManager, '_find_dev_auth_dir', lambda self: None)
    manager = AuthManager()

    account = AccountConfig(
        platform_id='fetlife',
        account_id='fetlife_1',
        profile_name='fetuser',
    )
    manager.add_account(account)
    assert manager.set_account_enabled('fetlife_1', False) is True
    assert manager.set_account_enabled('missing_1', False) is False

    manager2 = AuthManager()
    reloaded = manager2.get_account('fetlife_1')
    assert reloaded is not None
    assert reloaded.enabled is False
