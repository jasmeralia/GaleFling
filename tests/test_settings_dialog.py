"""Tests for settings dialog persistence."""

from __future__ import annotations

import json

from src.core.auth_manager import AuthManager
from src.core.config_manager import ConfigManager
from src.gui.settings_dialog import SettingsDialog


def _make_config(tmp_path, monkeypatch) -> ConfigManager:
    import src.core.config_manager as config_manager

    monkeypatch.setattr(config_manager, 'get_app_data_dir', lambda: tmp_path)
    return ConfigManager()


def _make_auth(tmp_path, monkeypatch) -> AuthManager:
    import src.core.auth_manager as auth_manager

    monkeypatch.setattr(auth_manager, 'get_auth_dir', lambda: tmp_path / 'auth')
    return AuthManager()


def test_settings_dialog_saves_config_and_auth(qtbot, tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    dialog._auto_update_cb.setChecked(False)
    dialog._prerelease_update_cb.setChecked(True)
    dialog._auto_save_cb.setChecked(False)
    dialog._debug_cb.setChecked(True)
    dialog._log_upload_cb.setChecked(False)
    dialog._endpoint_edit.setText('https://example.com/logs')

    dialog._tw_username.setText('tester')
    dialog._tw_api_key.setText('k')
    dialog._tw_api_secret.setText('s')
    dialog._tw_access_token.setText('t')
    dialog._tw_access_secret.setText('ts')

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

    twitter_auth = json.loads((tmp_path / 'auth' / 'twitter_auth.json').read_text())
    assert twitter_auth['username'] == 'tester'

    bluesky_auth = json.loads((tmp_path / 'auth' / 'bluesky_auth.json').read_text())
    assert bluesky_auth['identifier'] == 'user.bsky.social'
    bluesky_alt = json.loads((tmp_path / 'auth' / 'bluesky_auth_alt.json').read_text())
    assert bluesky_alt['identifier'] == 'alt.bsky.social'


def test_settings_dialog_does_not_save_incomplete_twitter(qtbot, tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    dialog._tw_username.setText('')
    dialog._tw_api_key.setText('k')
    dialog._tw_api_secret.setText('s')
    dialog._tw_access_token.setText('t')
    dialog._tw_access_secret.setText('ts')

    dialog._save_and_close()

    assert not (tmp_path / 'auth' / 'twitter_auth.json').exists()


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
