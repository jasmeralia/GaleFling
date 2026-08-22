"""Tests for settings dialog persistence."""

from __future__ import annotations

import json
import sqlite3

import pytest

from src.core.auth_manager import AuthManager
from src.core.config_manager import ConfigManager
from src.gui.settings_dialog import SettingsDialog
from src.utils.constants import PLATFORM_SPECS_MAP, AccountConfig


@pytest.fixture(autouse=True)
def _isolate_autostart(monkeypatch):
    monkeypatch.setattr('src.gui.settings_dialog.set_autostart', lambda *_a, **_k: None)


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


def _write_cookie_db(path, rows: list[tuple]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            'CREATE TABLE IF NOT EXISTS cookies ('
            'host_key TEXT, '
            'name TEXT, '
            'path TEXT, '
            'value TEXT, '
            'encrypted_value BLOB, '
            'expires_utc INTEGER, '
            'is_secure INTEGER, '
            'is_httponly INTEGER, '
            'samesite INTEGER, '
            'creation_utc INTEGER, '
            'last_access_utc INTEGER'
            ')'
        )
        cursor.executemany(
            'INSERT INTO cookies (host_key, name, path, value, encrypted_value, '
            'expires_utc, is_secure, is_httponly, samesite, creation_utc, last_access_utc) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            rows,
        )
        conn.commit()


def test_settings_dialog_saves_config_and_auth(qtbot, tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)
    auth.save_account_credentials('twitter_1', {'access_token': 't', 'access_token_secret': 'ts'})
    monkeypatch.setattr('src.gui.settings_dialog.QMessageBox.information', lambda *_a, **_k: 0)

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    dialog._auto_update_cb.setChecked(False)
    dialog._prerelease_update_cb.setChecked(True)
    dialog._auto_save_cb.setChecked(False)
    dialog._webview_compatibility_cb.setChecked(True)
    dialog._preview_workers_spin.setValue(3)
    dialog._debug_cb.setChecked(True)
    dialog._log_upload_cb.setChecked(False)
    dialog._endpoint_edit.setText('https://example.com/logs')
    dialog._autostart_cb.setChecked(True)
    dialog._autostart_mode_combo.setCurrentIndex(dialog._autostart_mode_combo.findData('window'))

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
    assert config.webview_compatibility_mode is True
    assert config.preview_worker_count == 3
    assert config.debug_mode is True
    assert config.log_upload_enabled is False
    assert config.log_upload_endpoint == 'https://example.com/logs'
    assert config.autostart_enabled is True
    assert config.autostart_launch_mode == 'window'

    twitter_app = json.loads((tmp_path / 'auth' / 'twitter_app_auth.json').read_text())
    assert twitter_app['api_key'] == 'k'
    assert auth.get_account('twitter_1').profile_name == 'tester'

    bluesky_auth = json.loads((tmp_path / 'auth' / 'bluesky_auth.json').read_text())
    assert bluesky_auth['identifier'] == 'user.bsky.social'
    bluesky_alt = json.loads((tmp_path / 'auth' / 'bluesky_auth_alt.json').read_text())
    assert bluesky_alt['identifier'] == 'alt.bsky.social'


def test_autostart_launch_mode_stays_configurable_while_disabled(qtbot, tmp_path, monkeypatch):
    dialog = SettingsDialog(
        _make_config(tmp_path, monkeypatch),
        _make_auth(tmp_path, monkeypatch),
    )
    qtbot.addWidget(dialog)

    dialog._autostart_cb.setChecked(False)

    assert dialog._autostart_mode_combo.isEnabled()


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


def test_settings_dialog_default_size_increased(qtbot, tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    assert dialog.minimumWidth() >= 760
    assert dialog.minimumHeight() >= 680


def test_settings_dialog_logout_clears_auth(qtbot, tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)
    auth.save_bluesky_auth_alt('alt.bsky.social', 'pw')

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    assert (tmp_path / 'auth' / 'bluesky_auth_alt.json').exists()

    dialog._logout_bluesky_alt()

    assert not (tmp_path / 'auth' / 'bluesky_auth_alt.json').exists()


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

    dialog._webview_profile_edits['fetlife_1'].setText('fetlifeuser')

    dialog._save_and_close()

    assert auth.get_account('fetlife_1').profile_name == 'fetlifeuser'


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


def test_settings_dialog_has_grouped_sidebar_sections(qtbot, tmp_path, monkeypatch):
    """Settings dialog should group app and platform sections in its sidebar."""
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    sidebar_names = [
        dialog._settings_sidebar.item(i).text() for i in range(dialog._settings_sidebar.count())
    ]

    # Advanced trails every account section under its own "More" header — not
    # grouped with General under "App" — so browsing accounts never scrolls
    # past it first.
    assert sidebar_names[:2] == ['App', 'General']
    assert sidebar_names[2:8] == [
        'Accounts',
        'Twitter',
        'Bluesky',
        'Facebook Page',
        'Instagram',
        'Threads',
    ]
    assert 'Meta' not in sidebar_names  # split into its own per-platform pages
    assert sidebar_names.count('Instagram') == 1  # not duplicated by the webview-platform loop
    # Snapchat, OnlyFans, and Fansly are all unavailable (paused), so none gets a section.
    assert 'Snapchat' not in sidebar_names
    assert 'OnlyFans' not in sidebar_names
    assert 'Fansly' not in sidebar_names
    assert sidebar_names[8:] == ['FetLife', 'More', 'Advanced']
    for row in (1, 3, 4, 5, 6, 7, 8, 10):
        assert not dialog._settings_sidebar.item(row).icon().isNull()


def test_settings_dialog_builds_webview_cookie_export_data(qtbot, tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)
    auth.add_account(
        AccountConfig(platform_id='snapchat', account_id='snapchat_1', profile_name='snap-user')
    )
    monkeypatch.setattr('src.gui.settings_dialog.get_app_data_dir', lambda: tmp_path)

    cookie_db = tmp_path / 'webprofiles' / 'snapchat_1' / 'Cookies'
    _write_cookie_db(
        cookie_db,
        [
            ('.snapchat.com', 'ssid', '/', 'abc', b'\x00\x01', 0, 1, 1, 0, 1, 2),
            ('.other.com', 'other', '/', 'zzz', b'', 0, 0, 0, 0, 1, 2),
        ],
    )

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)
    data = dialog._build_webview_cookie_export_data('snapchat', PLATFORM_SPECS_MAP['snapchat'])

    assert data['platform_id'] == 'snapchat'
    assert data['platform_name'] == 'Snapchat'
    account_1 = next(a for a in data['accounts'] if a['account_id'] == 'snapchat_1')
    assert account_1['cookie_db_exists'] is True
    assert account_1['cookie_count'] == 1
    assert account_1['cookies'][0]['host_key'] == '.snapchat.com'
    assert account_1['profile_name'] == 'snap-user'


def test_settings_dialog_export_webview_cookies_no_db_shows_notice(qtbot, tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)
    monkeypatch.setattr('src.gui.settings_dialog.get_app_data_dir', lambda: tmp_path)

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)
    calls = []
    monkeypatch.setattr(
        'src.gui.settings_dialog.QMessageBox.information',
        lambda *_args: calls.append(True),
    )

    dialog._export_webview_cookies('fetlife', PLATFORM_SPECS_MAP['fetlife'])

    assert calls


def test_settings_dialog_webview_sections_show_login_and_reset_buttons(
    qtbot, tmp_path, monkeypatch
):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)
    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    from PyQt6.QtWidgets import QPushButton

    open_buttons = [
        btn for btn in dialog.findChildren(QPushButton) if btn.text() == 'Open Login Window'
    ]
    reset_buttons = [
        btn for btn in dialog.findChildren(QPushButton) if btn.text() == 'Reset Session Cookies'
    ]
    import_buttons = [
        btn
        for btn in dialog.findChildren(QPushButton)
        if btn.text() == 'Import Session from auth.json...'
    ]
    # FetLife has 1 account and is the only available webview platform; Snapchat,
    # OnlyFans, and Fansly are all unavailable (paused) and contribute no section.
    # OnlyFans would offer no login button even if it did, since its login form
    # rejects embedded browsers; it would get a session-import button instead.
    assert len(open_buttons) == 1
    assert len(reset_buttons) == 1
    assert len(import_buttons) == 0


def test_settings_dialog_open_webview_login_window(qtbot, tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)
    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)
    dialog._webview_profile_edits['fetlife_1'].setText('fetlife-user')

    calls = {}

    class DummyLoginDialog:
        def __init__(self, platform, platform_name, parent=None):
            calls['platform_name'] = platform_name
            calls['account_id'] = platform.account_id

        def exec(self):
            calls['opened'] = True
            return 0

        def deleteLater(self):  # noqa: N802
            pass

    monkeypatch.setattr('src.gui.setup_wizard.WebViewLoginDialog', DummyLoginDialog)

    dialog._open_webview_login_window('snapchat', 'snapchat_1')

    assert calls['opened'] is True
    assert calls['platform_name'] == 'Snapchat'
    assert calls['account_id'] == 'snapchat_1'


def test_settings_dialog_meta_sidebar_sections_exist(qtbot, tmp_path, monkeypatch):
    """Settings dialog must include separate Facebook Page, Instagram, and Threads pages."""
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    from PyQt6.QtWidgets import QGroupBox, QScrollArea

    sidebar_names = [
        dialog._settings_sidebar.item(i).text() for i in range(dialog._settings_sidebar.count())
    ]
    for provider, display_name in (
        ('meta_facebook_page', 'Facebook Page'),
        ('meta_instagram', 'Instagram'),
        ('meta_threads', 'Threads'),
    ):
        assert display_name in sidebar_names

        page_item = next(
            dialog._settings_sidebar.item(i)
            for i in range(dialog._settings_sidebar.count())
            if dialog._settings_sidebar.item(i).text() == display_name
        )
        dialog._settings_sidebar.setCurrentItem(page_item)
        current_page = dialog._settings_stack.currentWidget()
        assert isinstance(current_page, QScrollArea)
        assert dialog._meta_provider_groups[provider] in current_page.findChildren(QGroupBox)


def test_settings_dialog_meta_section_renders_threads_section(qtbot, tmp_path, monkeypatch):
    """Meta settings must render a Threads provider section."""
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    from PyQt6.QtWidgets import QLabel

    labels = dialog.findChildren(QLabel)
    label_texts = [lbl.text() for lbl in labels]
    assert any('Threads' in t for t in label_texts), 'Meta section should contain a Threads label'


def test_settings_dialog_meta_section_renders_facebook_page_section(qtbot, tmp_path, monkeypatch):
    """Meta settings must render a Facebook Page provider section."""
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    from PyQt6.QtWidgets import QLabel

    labels = dialog.findChildren(QLabel)
    label_texts = [lbl.text() for lbl in labels]
    assert any('Facebook' in t for t in label_texts), (
        'Meta section should contain a Facebook Page label'
    )


def test_settings_dialog_meta_relay_uri_synced_across_pages_and_saved(qtbot, tmp_path, monkeypatch):
    """Editing the shared OAuth relay URI on one Meta page updates the others too."""
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    edits = dialog._meta_oauth_redirect_uri_edits
    assert set(edits) == {'meta_facebook_page', 'meta_instagram', 'meta_threads'}

    edits['meta_instagram'].setText('https://example.test/oauth/callback')
    for provider, edit in edits.items():
        assert edit.text() == 'https://example.test/oauth/callback', provider

    dialog._save_and_close()
    assert auth.get_meta_oauth_redirect_uri() == 'https://example.test/oauth/callback'


def test_settings_dialog_meta_app_credentials_load_and_save(qtbot, tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)
    auth.save_meta_threads_app_credentials('saved_th', 'saved_secret')
    monkeypatch.setattr('src.gui.settings_dialog.QMessageBox.information', lambda *_a, **_k: 0)

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    assert dialog._meta_app_credential_edits['meta_threads']['app_id'].text() == 'saved_th'
    assert dialog._meta_app_credential_edits['meta_threads']['app_secret'].text() == 'saved_secret'

    dialog._meta_app_credential_edits['meta_instagram']['app_id'].setText('ig_id')
    dialog._meta_app_credential_edits['meta_instagram']['app_secret'].setText('ig_secret')
    dialog._save_and_close()

    ig = auth.get_meta_instagram_app_credentials()
    th = auth.get_meta_threads_app_credentials()
    assert ig == {'app_id': 'ig_id', 'app_secret': 'ig_secret'}
    assert th == {'app_id': 'saved_th', 'app_secret': 'saved_secret'}


def test_settings_dialog_smtp_display_after_import(qtbot, tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)
    auth.save_smtp_credentials('smtp.gmail.com', 587, 'galefling@rin-city.com', 'app-password')

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    assert dialog._smtp_host_label.text() == 'smtp.gmail.com'
    assert dialog._smtp_port_label.text() == '587'
    assert dialog._smtp_username_label.text() == 'galefling@rin-city.com'
    assert dialog._smtp_app_password_label.text() != 'app-password'
    assert dialog._smtp_app_password_label.text().endswith('word')  # masked, last 4 chars visible


def test_settings_dialog_smtp_not_configured_shows_placeholder(qtbot, tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    assert dialog._smtp_host_label.text() == '(not configured)'
    assert dialog._smtp_username_label.text() == '(not configured)'
    assert dialog._smtp_app_password_label.text() == '(not configured)'


def test_settings_dialog_notification_email_load_and_save(qtbot, tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)
    config.notification_email = 'rin@example.com'

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    assert dialog._notification_email_edit.text() == 'rin@example.com'

    dialog._notification_email_edit.setText('jas@example.com')
    dialog._save_and_close()

    assert config.notification_email == 'jas@example.com'


def test_settings_dialog_test_smtp_connection_requires_notification_email(
    qtbot, tmp_path, monkeypatch
):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)
    auth.save_smtp_credentials('smtp.gmail.com', 587, 'galefling@rin-city.com', 'app-pw')
    warnings = []
    monkeypatch.setattr(
        'src.gui.settings_dialog.QMessageBox.warning',
        lambda *args, **_kwargs: warnings.append(args),
    )
    called = []
    monkeypatch.setattr(
        'src.gui.settings_dialog.check_smtp_connection',
        lambda **kwargs: called.append(kwargs),
    )

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)
    dialog._notification_email_edit.setText('')

    dialog._test_smtp_connection()

    assert not called
    assert warnings


def test_settings_dialog_test_smtp_connection_success(qtbot, tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)
    auth.save_smtp_credentials('smtp.gmail.com', 587, 'galefling@rin-city.com', 'app-pw')
    info_calls = []
    monkeypatch.setattr(
        'src.gui.settings_dialog.QMessageBox.information',
        lambda *args, **_kwargs: info_calls.append(args),
    )
    test_calls = []

    def _fake_check(**kwargs):
        test_calls.append(kwargs)
        return True, ''

    monkeypatch.setattr('src.gui.settings_dialog.check_smtp_connection', _fake_check)

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)
    dialog._notification_email_edit.setText('rin@example.com')

    dialog._test_smtp_connection()

    assert len(test_calls) == 1
    assert test_calls[0]['recipient'] == 'rin@example.com'
    assert test_calls[0]['host'] == 'smtp.gmail.com'
    assert info_calls


def test_settings_dialog_meta_app_credentials_clear_one_provider(qtbot, tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)
    auth.save_meta_threads_app_credentials('th_id', 'th_secret')
    auth.save_meta_instagram_app_credentials('ig_id', 'ig_secret')
    monkeypatch.setattr(
        'src.gui.settings_dialog.QMessageBox.question',
        lambda *_args, **_kwargs: 16384,  # QMessageBox.Yes
    )

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    dialog._clear_meta_app_credentials('meta_instagram', 'Instagram')

    assert auth.has_meta_instagram_app_credentials() is False
    assert auth.has_meta_threads_app_credentials() is True
    assert dialog._meta_app_credential_edits['meta_instagram']['app_id'].text() == ''
    assert dialog._meta_app_credential_edits['meta_instagram']['app_secret'].text() == ''


def test_settings_dialog_meta_connect_allows_second_account_with_clear_ux(
    qtbot, tmp_path, monkeypatch
):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)
    auth.save_meta_threads_app_credentials('th_id', 'th_secret')
    auth.add_account(
        AccountConfig(
            platform_id='meta_threads',
            account_id='meta_threads_1',
            profile_name='Primary',
        )
    )

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    from PyQt6.QtWidgets import QLabel, QPushButton

    group = dialog._meta_provider_groups['meta_threads']
    connect_btns = [
        btn for btn in group.findChildren(QPushButton) if btn.text().startswith('Connect')
    ]
    assert len(connect_btns) == 1
    assert connect_btns[0].text() == 'Connect Another Threads Account'
    assert connect_btns[0].isEnabled()

    hint_texts = [label.text() for label in group.findChildren(QLabel)]
    assert any('1 of 2 accounts connected' in text for text in hint_texts)
    assert any('Account 1: Primary' in text for text in hint_texts)


def test_settings_dialog_meta_connect_disabled_when_single_account_slot_full(
    qtbot, tmp_path, monkeypatch
):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)
    auth.save_meta_facebook_app_credentials('fb_id', 'fb_secret')
    auth.add_account(
        AccountConfig(
            platform_id='meta_facebook_page',
            account_id='meta_facebook_page_1',
            profile_name='Page Owner',
        )
    )

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    from PyQt6.QtWidgets import QPushButton

    group = dialog._meta_provider_groups['meta_facebook_page']
    connect_btns = [
        btn for btn in group.findChildren(QPushButton) if btn.text().startswith('Connect')
    ]
    assert len(connect_btns) == 1
    assert connect_btns[0].text() == 'Connect Facebook Page Account'
    assert not connect_btns[0].isEnabled()


def test_settings_dialog_meta_instagram_test_connection(qtbot, tmp_path, monkeypatch):
    from unittest.mock import patch

    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)
    auth.save_account_credentials(
        'meta_instagram_1',
        {'access_token': 'tok', 'user_id': '123', 'provider': 'meta_instagram'},
    )
    auth.add_account(
        AccountConfig(
            platform_id='meta_instagram',
            account_id='meta_instagram_1',
            profile_name='iguser',
        )
    )

    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    messages: list[tuple] = []
    monkeypatch.setattr(
        'src.gui.settings_dialog.QMessageBox.information',
        lambda *args, **_kwargs: messages.append(args),
    )

    with patch('src.platforms.meta_instagram.requests.get') as mock_get:
        mock_response = mock_get.return_value
        mock_response.status_code = 200
        mock_response.json.return_value = {'username': 'iguser'}
        dialog._test_meta_account_connection('meta_instagram_1', 'meta_instagram')

    assert messages
    assert messages[0][1] == 'Connection OK'


def test_settings_dialog_reset_webview_session_cookies(qtbot, tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    auth = _make_auth(tmp_path, monkeypatch)
    monkeypatch.setattr('src.gui.settings_dialog.get_app_data_dir', lambda: tmp_path)
    dialog = SettingsDialog(config, auth)
    qtbot.addWidget(dialog)

    profile_dir = tmp_path / 'webprofiles' / 'fetlife_1'
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / 'Cookies').write_bytes(b'data')

    monkeypatch.setattr(
        'src.gui.settings_dialog.QMessageBox.question',
        lambda *_args, **_kwargs: 16384,  # QMessageBox.Yes
    )

    info_calls = []
    monkeypatch.setattr(
        'src.gui.settings_dialog.QMessageBox.information',
        lambda *_args, **_kwargs: info_calls.append(True),
    )

    dialog._reset_webview_session('fetlife', 'fetlife_1')

    assert not profile_dir.exists()
    assert info_calls
