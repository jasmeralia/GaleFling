"""Settings dialog for debug mode, updates, and log configuration."""

import json
import shutil
import sqlite3
from datetime import UTC, datetime
from typing import cast

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.auth_manager import AuthManager
from src.core.config_manager import ConfigManager
from src.core.logger import get_logger
from src.gui.setup_wizard import WebViewLoginDialog
from src.platforms.base_webview import BaseWebViewPlatform
from src.platforms.fansly import FanslyPlatform
from src.platforms.fetlife import FetLifePlatform
from src.platforms.onlyfans import OnlyFansPlatform
from src.platforms.snapchat import SnapchatPlatform
from src.platforms.twitter import TwitterPlatform
from src.utils.constants import PLATFORM_SPECS_MAP, AccountConfig
from src.utils.helpers import get_app_data_dir


class SettingsDialog(QDialog):
    """Application settings with tabs for general, per-platform accounts, and debug."""

    _WEBVIEW_COOKIE_DOMAIN_MAP: dict[str, list[str]] = {
        'snapchat': SnapchatPlatform.COOKIE_DOMAINS,
        'onlyfans': OnlyFansPlatform.COOKIE_DOMAINS,
        'fansly': FanslyPlatform.COOKIE_DOMAINS,
        'fetlife': FetLifePlatform.COOKIE_DOMAINS,
    }

    def __init__(self, config: ConfigManager, auth_manager: AuthManager, parent=None):
        super().__init__(parent)
        self._config = config
        self._auth_manager = auth_manager
        self._twitter_pin_handlers: dict[str, object] = {}

        self.setWindowTitle('Settings')
        self.setMinimumSize(760, 680)
        self.resize(900, 760)

        layout = QVBoxLayout(self)

        tabs = QTabWidget()

        # General tab
        general_tab = self._create_general_tab()
        tabs.addTab(general_tab, 'General')

        # Per-platform account tabs
        self._create_twitter_tab(tabs)
        self._create_bluesky_tab(tabs)
        self._create_instagram_tab(tabs)

        self._webview_profile_edits: dict[str, QLineEdit] = {}
        for platform_id, specs in PLATFORM_SPECS_MAP.items():
            if specs.api_type != 'webview':
                continue
            self._create_webview_platform_tab(tabs, platform_id, specs)

        # Advanced tab
        advanced_tab = self._create_advanced_tab()
        tabs.addTab(advanced_tab, 'Advanced')

        layout.addWidget(tabs)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        save_btn = QPushButton('Save')
        save_btn.clicked.connect(self._save_and_close)
        btn_layout.addWidget(save_btn)

        cancel_btn = QPushButton('Cancel')
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def _create_general_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Updates
        updates_group = QGroupBox('Updates')
        updates_layout = QVBoxLayout(updates_group)
        self._auto_update_cb = QCheckBox('Automatically check for updates on startup')
        self._auto_update_cb.setChecked(self._config.auto_check_updates)
        updates_layout.addWidget(self._auto_update_cb)
        self._prerelease_update_cb = QCheckBox('Enable beta updates')
        self._prerelease_update_cb.setChecked(self._config.allow_prerelease_updates)
        updates_layout.addWidget(self._prerelease_update_cb)
        layout.addWidget(updates_group)

        # Drafts
        drafts_group = QGroupBox('Drafts')
        drafts_layout = QVBoxLayout(drafts_group)
        self._auto_save_cb = QCheckBox('Auto-save drafts')
        self._auto_save_cb.setChecked(self._config.auto_save_draft)
        drafts_layout.addWidget(self._auto_save_cb)
        layout.addWidget(drafts_group)

        layout.addStretch()
        return widget

    def _create_twitter_tab(self, tabs: QTabWidget):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        widget = QWidget()
        layout = QVBoxLayout(widget)

        # App Credentials
        tw_app_group = QGroupBox('App Credentials')
        tw_app_layout = QFormLayout(tw_app_group)

        tw_app = (
            self._auth_manager.get_twitter_app_credentials()
            or self._auth_manager.get_twitter_auth()
        )
        self._tw_api_key = QLineEdit(tw_app.get('api_key', '') if tw_app else '')
        self._tw_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        tw_app_layout.addRow('API Key:', self._tw_api_key)

        self._tw_api_secret = QLineEdit(tw_app.get('api_secret', '') if tw_app else '')
        self._tw_api_secret.setEchoMode(QLineEdit.EchoMode.Password)
        tw_app_layout.addRow('API Secret:', self._tw_api_secret)

        layout.addWidget(tw_app_group)

        # Hint
        tw_hint = QLabel(
            '<i>Each account is authorized separately. Before clicking '
            '"Start PIN Flow", make sure you are logged into the correct '
            'Twitter account in your web browser. To add a second account, '
            'log out of the first account in your browser first.</i>'
        )
        tw_hint.setWordWrap(True)
        layout.addWidget(tw_hint)

        # Accounts
        self._twitter_accounts: dict[str, dict[str, QLineEdit | QLabel]] = {}
        for account_id, label in [
            ('twitter_1', 'Account 1'),
            ('twitter_2', 'Account 2'),
        ]:
            account_group = QGroupBox(label)
            account_layout = QFormLayout(account_group)

            account = self._auth_manager.get_account(account_id)
            username = account.profile_name if account else ''

            username_edit = QLineEdit(username)
            username_edit.setPlaceholderText('Required for posting')
            account_layout.addRow('Username:', username_edit)

            pin_edit = QLineEdit()
            pin_edit.setPlaceholderText('Enter PIN from Twitter')
            account_layout.addRow('PIN:', pin_edit)

            btn_row = QHBoxLayout()
            start_btn = QPushButton('Start PIN Flow')
            start_btn.clicked.connect(
                lambda _=False, aid=account_id: self._start_twitter_pin_flow(aid)
            )
            btn_row.addWidget(start_btn)
            complete_btn = QPushButton('Complete PIN')
            complete_btn.clicked.connect(
                lambda _=False, aid=account_id: self._complete_twitter_pin_flow(aid)
            )
            btn_row.addWidget(complete_btn)
            btn_row.addStretch()
            account_layout.addRow('', btn_row)

            status_label = QLabel()
            account_layout.addRow('Status:', status_label)

            logout_btn = QPushButton('Logout')
            logout_btn.clicked.connect(
                lambda _=False, aid=account_id: self._logout_twitter_account(aid)
            )
            account_layout.addRow('', logout_btn)

            self._twitter_accounts[account_id] = {
                'username': username_edit,
                'pin': pin_edit,
                'status': status_label,
            }

            self._update_twitter_status(account_id)
            layout.addWidget(account_group)

        # Export
        export_btn = QPushButton('Export Twitter Credentials')
        export_btn.clicked.connect(self._export_twitter_credentials)
        layout.addWidget(export_btn)

        layout.addStretch()
        scroll.setWidget(widget)
        tabs.addTab(scroll, 'Twitter')

    def _create_bluesky_tab(self, tabs: QTabWidget):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Primary account
        bs_group = QGroupBox('Account 1')
        bs_layout = QFormLayout(bs_group)

        bs_creds = self._auth_manager.get_bluesky_auth()
        self._bs_identifier = QLineEdit(bs_creds.get('identifier', '') if bs_creds else '')
        bs_layout.addRow('Username (handle):', self._bs_identifier)

        self._bs_app_password = QLineEdit(bs_creds.get('app_password', '') if bs_creds else '')
        self._bs_app_password.setEchoMode(QLineEdit.EchoMode.Password)
        bs_layout.addRow('App Password:', self._bs_app_password)

        bs_logout = QPushButton('Logout')
        bs_logout.clicked.connect(self._logout_bluesky)
        bs_layout.addRow('', bs_logout)

        layout.addWidget(bs_group)

        # Alt account
        bs_alt_group = QGroupBox('Account 2')
        bs_alt_layout = QFormLayout(bs_alt_group)

        bs_alt_creds = self._auth_manager.get_bluesky_auth_alt()
        self._bs_alt_identifier = QLineEdit(
            bs_alt_creds.get('identifier', '') if bs_alt_creds else ''
        )
        bs_alt_layout.addRow('Username (handle):', self._bs_alt_identifier)

        self._bs_alt_app_password = QLineEdit(
            bs_alt_creds.get('app_password', '') if bs_alt_creds else ''
        )
        self._bs_alt_app_password.setEchoMode(QLineEdit.EchoMode.Password)
        bs_alt_layout.addRow('App Password:', self._bs_alt_app_password)

        bs_alt_logout = QPushButton('Logout')
        bs_alt_logout.clicked.connect(self._logout_bluesky_alt)
        bs_alt_layout.addRow('', bs_alt_logout)

        layout.addWidget(bs_alt_group)

        layout.addStretch()
        scroll.setWidget(widget)
        tabs.addTab(scroll, 'Bluesky')

    def _create_instagram_tab(self, tabs: QTabWidget):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        widget = QWidget()
        layout = QVBoxLayout(widget)

        ig_group = QGroupBox('Account 1')
        ig_layout = QFormLayout(ig_group)
        ig_layout.addRow(
            QLabel('<i>Requires a Business/Creator account linked to a Facebook Page.</i>'),
            QLabel(),
        )

        ig_creds = self._auth_manager.get_account_credentials('instagram_1')
        self._ig_access_token = QLineEdit(ig_creds.get('access_token', '') if ig_creds else '')
        self._ig_access_token.setEchoMode(QLineEdit.EchoMode.Password)
        ig_layout.addRow('Access Token:', self._ig_access_token)

        self._ig_user_id = QLineEdit(ig_creds.get('ig_user_id', '') if ig_creds else '')
        ig_layout.addRow('IG User ID:', self._ig_user_id)

        self._ig_page_id = QLineEdit(ig_creds.get('page_id', '') if ig_creds else '')
        ig_layout.addRow('Facebook Page ID:', self._ig_page_id)

        self._ig_profile_name = QLineEdit(ig_creds.get('profile_name', '') if ig_creds else '')
        self._ig_profile_name.setPlaceholderText('Display name (e.g. rinthemodel)')
        ig_layout.addRow('Profile Name:', self._ig_profile_name)

        ig_logout = QPushButton('Logout')
        ig_logout.clicked.connect(self._logout_instagram)
        ig_layout.addRow('', ig_logout)

        layout.addWidget(ig_group)

        layout.addStretch()
        scroll.setWidget(widget)
        tabs.addTab(scroll, 'Instagram')

    def _create_webview_platform_tab(self, tabs: QTabWidget, platform_id: str, specs):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        widget = QWidget()
        layout = QVBoxLayout(widget)

        group = QGroupBox('Accounts')
        form = QFormLayout(group)

        form.addRow(
            QLabel(
                '<i>Log in via the embedded browser. Your session cookies are stored locally.</i>'
            ),
            QLabel(),
        )

        for n in range(1, specs.max_accounts + 1):
            account_id = f'{platform_id}_{n}'
            account = self._auth_manager.get_account(account_id)
            profile_name = account.profile_name if account else ''

            suffix = f' (Account {n})' if specs.max_accounts > 1 else ''
            name_edit = QLineEdit(profile_name)
            name_edit.setPlaceholderText(f'Display name{suffix}')
            form.addRow(f'Profile Name{suffix}:', name_edit)
            self._webview_profile_edits[account_id] = name_edit

            actions = QHBoxLayout()
            open_login_btn = QPushButton('Open Login Window')
            open_login_btn.clicked.connect(
                lambda _=False, pid=platform_id, aid=account_id: self._open_webview_login_window(
                    pid, aid
                )
            )
            actions.addWidget(open_login_btn)

            reset_session_btn = QPushButton('Reset Session Cookies')
            reset_session_btn.clicked.connect(
                lambda _=False, pid=platform_id, aid=account_id: self._reset_webview_session(
                    pid, aid
                )
            )
            actions.addWidget(reset_session_btn)
            actions.addStretch()
            form.addRow(f'Session{suffix}:', actions)

        layout.addWidget(group)

        export_btn = QPushButton(f'Export {specs.platform_name} Cookies')
        export_btn.clicked.connect(
            lambda _=False, pid=platform_id, ps=specs: self._export_webview_cookies(pid, ps)
        )
        layout.addWidget(export_btn)

        layout.addStretch()
        scroll.setWidget(widget)
        tabs.addTab(scroll, specs.platform_name)

    def _create_advanced_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # WebView compatibility
        webview_group = QGroupBox('WebView')
        webview_layout = QVBoxLayout(webview_group)
        self._webview_compatibility_cb = QCheckBox(
            'Use compatibility mode (disables GPU acceleration for embedded browsers)'
        )
        self._webview_compatibility_cb.setChecked(self._config.webview_compatibility_mode)
        webview_layout.addWidget(self._webview_compatibility_cb)
        webview_layout.addWidget(
            QLabel(
                '<i>Requires app restart to take effect. May improve stability on some systems.</i>'
            )
        )
        layout.addWidget(webview_group)

        # Debug
        debug_group = QGroupBox('Debug')
        debug_layout = QVBoxLayout(debug_group)
        self._debug_cb = QCheckBox('Enable debug mode (verbose logging)')
        self._debug_cb.setChecked(self._config.debug_mode)
        debug_layout.addWidget(self._debug_cb)
        layout.addWidget(debug_group)

        # Log upload
        log_group = QGroupBox('Log Upload')
        log_layout = QVBoxLayout(log_group)
        self._log_upload_cb = QCheckBox('Enable log upload')
        self._log_upload_cb.setChecked(self._config.log_upload_enabled)
        log_layout.addWidget(self._log_upload_cb)

        endpoint_layout = QHBoxLayout()
        endpoint_layout.addWidget(QLabel('Endpoint:'))
        self._endpoint_edit = QLineEdit(self._config.log_upload_endpoint)
        endpoint_layout.addWidget(self._endpoint_edit)
        log_layout.addLayout(endpoint_layout)

        layout.addWidget(log_group)

        layout.addStretch()
        return widget

    def _save_and_close(self):
        if not self._validate_bluesky_accounts():
            return
        webview_compatibility_before = self._config.webview_compatibility_mode

        # General
        self._config.set('auto_check_updates', self._auto_update_cb.isChecked())
        self._config.set('allow_prerelease_updates', self._prerelease_update_cb.isChecked())
        self._config.set('auto_save_draft', self._auto_save_cb.isChecked())

        # Advanced
        self._config.webview_compatibility_mode = self._webview_compatibility_cb.isChecked()
        self._config.debug_mode = self._debug_cb.isChecked()
        self._config.set('log_upload_enabled', self._log_upload_cb.isChecked())
        self._config.set('log_upload_endpoint', self._endpoint_edit.text())

        # Accounts - Twitter app credentials
        tw_key = self._tw_api_key.text().strip()
        tw_secret = self._tw_api_secret.text().strip()
        if tw_key and tw_secret:
            self._auth_manager.save_twitter_app_credentials(tw_key, tw_secret)

        # Accounts - Twitter profiles (only if credentials exist)
        for account_id, widgets in self._twitter_accounts.items():
            username = widgets['username'].text().strip()
            creds = self._auth_manager.get_account_credentials(account_id) or {}
            if username and all(k in creds for k in ('access_token', 'access_token_secret')):
                self._auth_manager.add_account(
                    AccountConfig(
                        platform_id='twitter',
                        account_id=account_id,
                        profile_name=username,
                    )
                )

        # Accounts - Bluesky
        bs_id = self._bs_identifier.text().strip()
        bs_pw = self._bs_app_password.text().strip()
        if bs_id and bs_pw:
            self._auth_manager.save_bluesky_auth(bs_id, bs_pw)
            self._auth_manager.add_account(
                AccountConfig(
                    platform_id='bluesky',
                    account_id='bluesky_1',
                    profile_name=bs_id,
                )
            )

        # Accounts - Bluesky (Account 2)
        bs_alt_id = self._bs_alt_identifier.text().strip()
        bs_alt_pw = self._bs_alt_app_password.text().strip()
        if bs_alt_id and bs_alt_pw:
            self._auth_manager.save_bluesky_auth_alt(bs_alt_id, bs_alt_pw)
            self._auth_manager.add_account(
                AccountConfig(
                    platform_id='bluesky',
                    account_id='bluesky_alt',
                    profile_name=bs_alt_id,
                )
            )

        # Accounts - Instagram
        ig_token = self._ig_access_token.text().strip()
        ig_uid = self._ig_user_id.text().strip()
        ig_pid = self._ig_page_id.text().strip()
        ig_name = self._ig_profile_name.text().strip()
        if ig_token and ig_uid:
            self._auth_manager.save_account_credentials(
                'instagram_1',
                {
                    'access_token': ig_token,
                    'ig_user_id': ig_uid,
                    'page_id': ig_pid,
                    'profile_name': ig_name,
                },
            )
            self._auth_manager.add_account(
                AccountConfig(
                    platform_id='instagram',
                    account_id='instagram_1',
                    profile_name=ig_name,
                )
            )

        # Accounts - WebView platforms (save profile names)
        for account_id, name_edit in self._webview_profile_edits.items():
            profile_name = name_edit.text().strip()
            if profile_name:
                # Determine platform_id from account_id (e.g. "snapchat_1" -> "snapchat")
                platform_id = account_id.rsplit('_', 1)[0]
                self._auth_manager.add_account(
                    AccountConfig(
                        platform_id=platform_id,
                        account_id=account_id,
                        profile_name=profile_name,
                    )
                )

        self._config.save()
        if webview_compatibility_before != self._config.webview_compatibility_mode:
            QMessageBox.information(
                self,
                'Restart Required',
                'WebView compatibility mode changes will apply after restarting GaleFling.',
            )
        self.accept()

    def _validate_bluesky_accounts(self) -> bool:
        bs_id = self._bs_identifier.text().strip()
        bs_pw = self._bs_app_password.text().strip()
        bs_alt_id = self._bs_alt_identifier.text().strip()
        bs_alt_pw = self._bs_alt_app_password.text().strip()

        if not bs_alt_id and not bs_alt_pw:
            return True
        if not bs_id or not bs_pw:
            return True
        if bs_id.lower() == bs_alt_id.lower() or bs_pw == bs_alt_pw:
            QMessageBox.warning(
                self,
                'Duplicate Account',
                'Bluesky accounts must be different. Please use a different username '
                'and app password for the second account.',
            )
            return False
        return True

    def _update_twitter_status(self, account_id: str):
        widgets = self._twitter_accounts.get(account_id)
        if not widgets:
            return
        status_label = cast(QLabel, widgets['status'])
        creds = self._auth_manager.get_account_credentials(account_id) or {}
        if all(k in creds for k in ('access_token', 'access_token_secret')):
            status_label.setText(
                '<span style="color: #4CAF50; font-weight: bold;">\u2713 Authorized</span>'
            )
        else:
            status_label.setText('Not authorized')

    def _start_twitter_pin_flow(self, account_id: str):
        api_key = self._tw_api_key.text().strip()
        api_secret = self._tw_api_secret.text().strip()
        if not api_key or not api_secret:
            QMessageBox.warning(
                self,
                'Missing Credentials',
                'Enter your Twitter API key and secret before starting PIN flow.',
            )
            return
        try:
            auth_handler, url = TwitterPlatform.start_pin_flow(api_key, api_secret)
        except Exception as exc:
            QMessageBox.warning(self, 'PIN Flow Error', f'Failed to start PIN flow: {exc}')
            return
        self._twitter_pin_handlers[account_id] = auth_handler
        QDesktopServices.openUrl(QUrl(url))
        widgets = self._twitter_accounts.get(account_id)
        if widgets:
            status_label = cast(QLabel, widgets['status'])
            status_label.setText('PIN flow started. Enter PIN to complete.')

    def _complete_twitter_pin_flow(self, account_id: str):
        widgets = self._twitter_accounts.get(account_id)
        if not widgets:
            return
        username_edit = cast(QLineEdit, widgets['username'])
        pin_edit = cast(QLineEdit, widgets['pin'])
        username = username_edit.text().strip()
        pin = pin_edit.text().strip()
        if not username:
            QMessageBox.warning(self, 'Missing Username', 'Please enter a username first.')
            return
        if not pin:
            QMessageBox.warning(self, 'Missing PIN', 'Please enter the PIN from Twitter.')
            return
        auth_handler = self._twitter_pin_handlers.get(account_id)
        if not auth_handler:
            QMessageBox.warning(
                self,
                'PIN Flow Not Started',
                'Click "Start PIN Flow" first to generate a PIN.',
            )
            return
        try:
            access_token, access_secret = TwitterPlatform.complete_pin_flow(auth_handler, pin)
        except Exception as exc:
            QMessageBox.warning(self, 'PIN Flow Error', f'Failed to complete PIN flow: {exc}')
            return

        self._auth_manager.save_account_credentials(
            account_id,
            {
                'access_token': access_token,
                'access_token_secret': access_secret,
            },
        )
        self._auth_manager.add_account(
            AccountConfig(
                platform_id='twitter',
                account_id=account_id,
                profile_name=username,
            )
        )
        pin_edit.clear()
        self._update_twitter_status(account_id)

    def _logout_twitter_account(self, account_id: str):
        self._auth_manager.clear_account_credentials(account_id)
        self._auth_manager.remove_account(account_id)
        widgets = self._twitter_accounts.get(account_id)
        if not widgets:
            return
        username_edit = cast(QLineEdit, widgets['username'])
        pin_edit = cast(QLineEdit, widgets['pin'])
        username_edit.clear()
        pin_edit.clear()
        self._update_twitter_status(account_id)

    def _export_twitter_credentials(self) -> None:
        get_logger().info('User selected Settings > Export Twitter Credentials')
        app_creds = self._auth_manager.get_twitter_app_credentials() or {}
        export_data: dict = {}
        if app_creds:
            export_data['app_credentials'] = {
                'api_key': app_creds.get('api_key', ''),
                'api_secret': app_creds.get('api_secret', ''),
            }
        accounts = []
        for account_id in ('twitter_1', 'twitter_2'):
            account = self._auth_manager.get_account(account_id)
            creds = self._auth_manager.get_account_credentials(account_id) or {}
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

        if not export_data:
            QMessageBox.information(
                self,
                'No Credentials',
                'No Twitter credentials are configured to export.',
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            'Export Twitter Credentials',
            'twitter_credentials.json',
            'JSON Files (*.json)',
        )
        if not path:
            return
        try:
            with open(path, 'w') as f:
                json.dump(export_data, f, indent=4)
            QMessageBox.information(
                self,
                'Export Successful',
                f'Twitter credentials exported to:\n{path}',
            )
        except OSError as e:
            QMessageBox.warning(
                self,
                'Export Failed',
                f'Failed to write file: {e}',
            )

    def _read_webview_cookies(
        self, cookie_db_path, cookie_domains: list[str]
    ) -> tuple[list[dict], str | None]:
        if not cookie_db_path.exists():
            return [], None
        try:
            with sqlite3.connect(cookie_db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('PRAGMA table_info(cookies)')
                available_columns = {str(row[1]) for row in cursor.fetchall()}
                if not available_columns:
                    return [], 'Cookies table not available.'

                preferred_columns = [
                    'host_key',
                    'name',
                    'path',
                    'value',
                    'encrypted_value',
                    'expires_utc',
                    'is_secure',
                    'is_httponly',
                    'samesite',
                    'creation_utc',
                    'last_access_utc',
                ]
                selected_columns = [c for c in preferred_columns if c in available_columns]
                if not selected_columns:
                    return [], 'No readable cookie columns found.'

                query = f'SELECT {", ".join(selected_columns)} FROM cookies'
                params: tuple[str, ...] = ()
                if cookie_domains and 'host_key' in available_columns:
                    where_parts = ['host_key LIKE ?'] * len(cookie_domains)
                    query += f' WHERE {" OR ".join(where_parts)}'
                    params = tuple(f'%{domain}' for domain in cookie_domains)
                if 'host_key' in available_columns and 'name' in available_columns:
                    query += ' ORDER BY host_key, name'

                rows = cursor.execute(query, params).fetchall()
                cookies: list[dict] = []
                for row in rows:
                    item = {}
                    for idx, key in enumerate(selected_columns):
                        value = row[idx]
                        if isinstance(value, bytes):
                            item[key] = value.hex()
                        else:
                            item[key] = value
                    cookies.append(item)
                return cookies, None
        except sqlite3.Error as exc:
            return [], f'Failed to read cookie database: {exc}'

    def _build_webview_cookie_export_data(self, platform_id: str, specs) -> dict:
        domains = self._WEBVIEW_COOKIE_DOMAIN_MAP.get(platform_id, [])
        accounts = []
        for n in range(1, specs.max_accounts + 1):
            account_id = f'{platform_id}_{n}'
            account = self._auth_manager.get_account(account_id)
            profile_name = account.profile_name if account else ''
            cookie_db_path = get_app_data_dir() / 'webprofiles' / account_id / 'Cookies'
            cookies, warning = self._read_webview_cookies(cookie_db_path, domains)
            account_data = {
                'account_id': account_id,
                'profile_name': profile_name,
                'cookie_db_path': str(cookie_db_path),
                'cookie_db_exists': cookie_db_path.exists(),
                'cookie_domains': domains,
                'cookie_count': len(cookies),
                'cookies': cookies,
            }
            if warning:
                account_data['warning'] = warning
            accounts.append(account_data)
        return {
            'platform_id': platform_id,
            'platform_name': specs.platform_name,
            'generated_at_utc': datetime.now(UTC).isoformat(),
            'accounts': accounts,
        }

    def _export_webview_cookies(self, platform_id: str, specs):
        get_logger().info(f'User selected Settings > Export {specs.platform_name} Cookies')
        export_data = self._build_webview_cookie_export_data(platform_id, specs)
        if not any(
            account_data.get('cookie_db_exists') or account_data.get('cookie_count', 0) > 0
            for account_data in export_data['accounts']
        ):
            QMessageBox.information(
                self,
                'No Cookies Found',
                f'No {specs.platform_name} cookie database files were found to export.',
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            f'Export {specs.platform_name} Cookies',
            f'{platform_id}_cookies.json',
            'JSON Files (*.json)',
        )
        if not path:
            return
        try:
            with open(path, 'w') as f:
                json.dump(export_data, f, indent=2)
            QMessageBox.information(
                self,
                'Export Successful',
                f'{specs.platform_name} cookies exported to:\n{path}',
            )
        except OSError as e:
            QMessageBox.warning(
                self,
                'Export Failed',
                f'Failed to write file: {e}',
            )

    def _logout_bluesky(self):
        self._auth_manager.clear_bluesky_auth()
        self._auth_manager.remove_account('bluesky_1')
        self._bs_identifier.clear()
        self._bs_app_password.clear()

    def _logout_bluesky_alt(self):
        self._auth_manager.clear_bluesky_auth_alt()
        self._auth_manager.remove_account('bluesky_alt')
        self._bs_alt_identifier.clear()
        self._bs_alt_app_password.clear()

    def _logout_instagram(self):
        self._auth_manager.clear_account_credentials('instagram_1')
        self._auth_manager.remove_account('instagram_1')
        self._ig_access_token.clear()
        self._ig_user_id.clear()
        self._ig_page_id.clear()
        self._ig_profile_name.clear()

    def _create_webview_platform(
        self, platform_id: str, account_id: str
    ) -> BaseWebViewPlatform | None:
        profile_edit = self._webview_profile_edits.get(account_id)
        profile_name = profile_edit.text().strip() if profile_edit else ''
        account = self._auth_manager.get_account(account_id)
        if not profile_name and account:
            profile_name = account.profile_name
        if platform_id == 'snapchat':
            return SnapchatPlatform(account_id=account_id, profile_name=profile_name)
        if platform_id == 'onlyfans':
            return OnlyFansPlatform(account_id=account_id, profile_name=profile_name)
        if platform_id == 'fansly':
            return FanslyPlatform(account_id=account_id, profile_name=profile_name)
        if platform_id == 'fetlife':
            return FetLifePlatform(account_id=account_id, profile_name=profile_name)
        return None

    def _open_webview_login_window(self, platform_id: str, account_id: str):
        specs = PLATFORM_SPECS_MAP.get(platform_id)
        if specs is None:
            QMessageBox.warning(self, 'Unsupported Platform', 'This platform is not supported.')
            return
        platform = self._create_webview_platform(platform_id, account_id)
        if platform is None:
            QMessageBox.warning(self, 'Unsupported Platform', 'This platform is not supported.')
            return

        get_logger().info(
            f'User selected Settings > {specs.platform_name} > Open Login Window',
            extra={'platform_id': platform_id, 'account_id': account_id},
        )
        dialog = WebViewLoginDialog(platform, specs.platform_name, self)
        dialog.exec()

    def _reset_webview_session(self, platform_id: str, account_id: str):
        specs = PLATFORM_SPECS_MAP.get(platform_id)
        if specs is None:
            return
        reply = QMessageBox.question(
            self,
            'Reset Session Cookies',
            (
                f'Remove stored {specs.platform_name} session cookies for {account_id}?\n\n'
                'You will need to log in again.'
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        profile_path = get_app_data_dir() / 'webprofiles' / account_id
        get_logger().info(
            f'User selected Settings > {specs.platform_name} > Reset Session Cookies',
            extra={'platform_id': platform_id, 'account_id': account_id},
        )
        if not profile_path.exists():
            QMessageBox.information(
                self,
                'No Session Found',
                f'No stored session data found for {account_id}.',
            )
            return
        try:
            shutil.rmtree(profile_path)
            QMessageBox.information(
                self,
                'Session Reset',
                f'{specs.platform_name} session data cleared for {account_id}.',
            )
        except OSError as exc:
            QMessageBox.warning(
                self,
                'Reset Failed',
                f'Failed to clear session data: {exc}',
            )
