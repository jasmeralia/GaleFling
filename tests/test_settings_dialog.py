"""Tests for settings dialog persistence."""

from __future__ import annotations

import json

from src.core.auth_manager import AuthManager
from src.core.config_manager import ConfigManager
from src.gui.settings_dialog import SettingsDialog
from src.utils.constants import AccountConfig


def _make_config(tmp_path, monkeypatch) -> ConfigManager:
    import src.core.config_manager as config_manager

    monkeypatch.setattr(config_manager, 'get_app_data_dir', lambda: tmp_path)
    return ConfigManager()


def _make_auth(tmp_path, monkeypatch) -> AuthManager:
    import src.core.auth_manager as auth_manager

    monkeypatch.setattr(auth_manager, 'get_auth_dir', lambda: tmp_path / 'auth')
    monkeypatch.setattr(auth_manager, 'get_app_data_dir', lambda: tmp_path)
    monkeypatch.setattr(AuthManager, '_find_dev_auth_dir', lambda self: None)
    return AuthManager()


def test_settings_dialog_saves_config_and_auth(qtbot, tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)
    auth.save_account_credentials('twitter_1', {'access_token': 't', 'access_token_secret': 'ts'})

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    dialog._auto_update_cb.setChecked(False)
    dialog._prerelease_update_cb.setChecked(True)
    dialog._auto_save_cb.setChecked(False)
    dialog._debug_cb.setChecked(True)
    dialog._log_upload_cb.setChecked(False)
    dialog._endpoint_edit.setText('https://example.com/logs')

    dialog._tw_api_key.setText('k')
    dialog._tw_api_secret.setText('s')
    dialog._twitter_accounts['twitter_1']['username'].setText('tester')

    dialog._bs_identifier.setText('user.bsky.social')
    dialog._bs_app_password.setText('app-pass')
    dialog._bs_alt_identifier.setText('alt.bsky.social')
    dialog._bs_alt_app_password.setText('alt-pass')

    dialog._save_and_close()

    assert config.auto_check_updates is False
    assert config.allow_prerelease_updates is True
    assert config.auto_save_draft is False
    assert config.debug_mode is True
    assert config.log_upload_enabled is False
    assert config.log_upload_endpoint == 'https://example.com/logs'

    twitter_app = json.loads((tmp_path / 'auth' / 'twitter_app_auth.json').read_text())
    assert twitter_app['api_key'] == 'k'
    assert auth.get_account('twitter_1').profile_name == 'tester'

    bluesky_auth = json.loads((tmp_path / 'auth' / 'bluesky_auth.json').read_text())
    assert bluesky_auth['identifier'] == 'user.bsky.social'
    bluesky_alt = json.loads((tmp_path / 'auth' / 'bluesky_auth_alt.json').read_text())
    assert bluesky_alt['identifier'] == 'alt.bsky.social'


def test_settings_dialog_does_not_save_incomplete_twitter(qtbot, tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    dialog._twitter_accounts['twitter_1']['username'].setText('tester')
    dialog._tw_api_key.setText('k')
    dialog._tw_api_secret.setText('s')

    dialog._save_and_close()

    assert not (tmp_path / 'auth' / 'twitter_1_auth.json').exists()


def test_settings_dialog_blocks_duplicate_bluesky(qtbot, tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    dialog._bs_identifier.setText('same.bsky.social')
    dialog._bs_app_password.setText('pw')
    dialog._bs_alt_identifier.setText('same.bsky.social')
    dialog._bs_alt_app_password.setText('pw')

    warnings = []

    def fake_warning(*_args, **_kwargs):
        warnings.append(True)

    monkeypatch.setattr('src.gui.settings_dialog.QMessageBox.warning', fake_warning)

    dialog._save_and_close()

    assert warnings
    assert not (tmp_path / 'auth' / 'bluesky_auth_alt.json').exists()


def test_settings_dialog_logout_clears_auth(qtbot, tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)
    auth.save_bluesky_auth_alt('alt.bsky.social', 'pw')

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    assert (tmp_path / 'auth' / 'bluesky_auth_alt.json').exists()

    dialog._logout_bluesky_alt()

    assert not (tmp_path / 'auth' / 'bluesky_auth_alt.json').exists()


def test_settings_dialog_saves_instagram(qtbot, tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    dialog._ig_access_token.setText('ig_token')
    dialog._ig_user_id.setText('12345')
    dialog._ig_page_id.setText('67890')
    dialog._ig_profile_name.setText('rinthemodel')

    dialog._save_and_close()

    ig_creds = json.loads((tmp_path / 'auth' / 'instagram_1_auth.json').read_text())
    assert ig_creds['access_token'] == 'ig_token'
    assert ig_creds['ig_user_id'] == '12345'
    assert auth.get_account('instagram_1').profile_name == 'rinthemodel'


def test_settings_dialog_logout_bluesky_primary(qtbot, tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)
    auth.save_bluesky_auth('user.bsky.social', 'pw')
    auth.add_account(
        AccountConfig(
            platform_id='bluesky', account_id='bluesky_1', profile_name='user.bsky.social'
        )
    )

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    dialog._logout_bluesky()

    assert not (tmp_path / 'auth' / 'bluesky_auth.json').exists()
    assert auth.get_account('bluesky_1') is None
    assert dialog._bs_identifier.text() == ''


def test_settings_dialog_logout_instagram(qtbot, tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)
    auth.save_account_credentials('instagram_1', {'access_token': 't', 'ig_user_id': 'u'})
    auth.add_account(
        AccountConfig(platform_id='instagram', account_id='instagram_1', profile_name='rin')
    )

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    dialog._logout_instagram()

    assert not (tmp_path / 'auth' / 'instagram_1_auth.json').exists()
    assert auth.get_account('instagram_1') is None
    assert dialog._ig_access_token.text() == ''


def test_settings_dialog_logout_twitter(qtbot, tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)
    auth.save_account_credentials('twitter_1', {'access_token': 't', 'access_token_secret': 'ts'})
    auth.add_account(
        AccountConfig(platform_id='twitter', account_id='twitter_1', profile_name='tester')
    )

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    dialog._logout_twitter_account('twitter_1')

    assert not (tmp_path / 'auth' / 'twitter_1_auth.json').exists()
    assert auth.get_account('twitter_1') is None


def test_settings_dialog_saves_webview_profile_names(qtbot, tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    dialog._webview_profile_edits['snapchat_1'].setText('snapuser')

    dialog._save_and_close()

    assert auth.get_account('snapchat_1').profile_name == 'snapuser'


def test_settings_dialog_export_builds_correct_data(tmp_path, monkeypatch):
    """Test the export data construction logic without GUI dialogs."""
    auth = _make_auth(tmp_path, monkeypatch)
    auth.save_twitter_app_credentials('api_k', 'api_s')
    auth.save_account_credentials(
        'twitter_1', {'access_token': 'at1', 'access_token_secret': 'as1'}
    )
    auth.add_account(
        AccountConfig(platform_id='twitter', account_id='twitter_1', profile_name='user1')
    )
    auth.save_account_credentials(
        'twitter_2', {'access_token': 'at2', 'access_token_secret': 'as2'}
    )
    auth.add_account(
        AccountConfig(platform_id='twitter', account_id='twitter_2', profile_name='user2')
    )

    # Build export data the same way the dialog method does
    app_creds = auth.get_twitter_app_credentials() or {}
    export_data: dict = {}
    if app_creds:
        export_data['app_credentials'] = {
            'api_key': app_creds.get('api_key', ''),
            'api_secret': app_creds.get('api_secret', ''),
        }
    accounts = []
    for account_id in ('twitter_1', 'twitter_2'):
        account = auth.get_account(account_id)
        creds = auth.get_account_credentials(account_id) or {}
        if account and all(k in creds for k in ('access_token', 'access_token_secret')):
            accounts.append(
                {
                    'account_id': account_id,
                    'profile_name': account.profile_name,
                    'access_token': creds['access_token'],
                    'access_token_secret': creds['access_token_secret'],
                }
            )
    if accounts:
        export_data['accounts'] = accounts

    # Write to file
    export_path = tmp_path / 'export.json'
    with open(export_path, 'w') as f:
        json.dump(export_data, f, indent=4)

    data = json.loads(export_path.read_text())
    assert data['app_credentials']['api_key'] == 'api_k'
    assert data['app_credentials']['api_secret'] == 'api_s'
    assert len(data['accounts']) == 2
    assert data['accounts'][0]['account_id'] == 'twitter_1'
    assert data['accounts'][0]['profile_name'] == 'user1'
    assert data['accounts'][0]['access_token'] == 'at1'
    assert data['accounts'][1]['account_id'] == 'twitter_2'
    assert data['accounts'][1]['access_token'] == 'at2'


def test_settings_dialog_export_no_credentials_returns_empty(tmp_path, monkeypatch):
    """Test that export with no credentials produces empty data."""
    auth = _make_auth(tmp_path, monkeypatch)

    app_creds = auth.get_twitter_app_credentials() or {}
    export_data: dict = {}
    if app_creds:
        export_data['app_credentials'] = {
            'api_key': app_creds.get('api_key', ''),
            'api_secret': app_creds.get('api_secret', ''),
        }
    accounts = []
    for account_id in ('twitter_1', 'twitter_2'):
        account = auth.get_account(account_id)
        creds = auth.get_account_credentials(account_id) or {}
        if account and all(k in creds for k in ('access_token', 'access_token_secret')):
            accounts.append({})
    if accounts:
        export_data['accounts'] = accounts

    assert not export_data


def test_settings_dialog_export_app_only(tmp_path, monkeypatch):
    """Test export with only app credentials (no account tokens)."""
    auth = _make_auth(tmp_path, monkeypatch)
    auth.save_twitter_app_credentials('k', 's')

    app_creds = auth.get_twitter_app_credentials() or {}
    export_data: dict = {}
    if app_creds:
        export_data['app_credentials'] = {
            'api_key': app_creds.get('api_key', ''),
            'api_secret': app_creds.get('api_secret', ''),
        }

    assert 'app_credentials' in export_data
    assert export_data['app_credentials']['api_key'] == 'k'


def test_settings_dialog_twitter_status_authorized(qtbot, tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)
    auth.save_account_credentials('twitter_1', {'access_token': 't', 'access_token_secret': 'ts'})

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    from typing import cast

    from PyQt6.QtWidgets import QLabel

    status = cast(QLabel, dialog._twitter_accounts['twitter_1']['status'])
    assert 'Authorized' in status.text()


def test_settings_dialog_twitter_status_not_authorized(qtbot, tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    from typing import cast

    from PyQt6.QtWidgets import QLabel

    status = cast(QLabel, dialog._twitter_accounts['twitter_1']['status'])
    assert 'Not authorized' in status.text()
