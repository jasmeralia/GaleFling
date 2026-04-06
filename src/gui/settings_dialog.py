"""Settings dialog for debug mode, updates, and log configuration."""

import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
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
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.auth_manager import AuthManager
from src.core.aws_utils import check_s3_connection
from src.core.config_manager import ConfigManager
from src.core.credential_importer import ImportResult, import_credentials
from src.core.logger import get_logger
from src.gui.setup_wizard import WebViewLoginDialog
from src.platforms.base_webview import BaseWebViewPlatform
from src.platforms.fansly import FanslyPlatform
from src.platforms.fetlife import FetLifePlatform
from src.platforms.onlyfans import OnlyFansPlatform
from src.platforms.snapchat import SnapchatPlatform
from src.platforms.threads import ThreadsPlatform
from src.platforms.twitter import TwitterPlatform
from src.utils.constants import PLATFORM_SPECS_MAP, AccountConfig
from src.utils.helpers import get_app_data_dir


def _mask_credential(value: str, visible_chars: int = 4) -> str:
    """Return ``value`` with all but the last ``visible_chars`` chars replaced with '*'."""
    if not value:
        return ''
    if len(value) <= visible_chars:
        return '*' * len(value)
    return '*' * (len(value) - visible_chars) + value[-visible_chars:]


class SettingsDialog(QDialog):
    """Application settings with tabs for general, per-platform accounts, and debug."""

    _WEBVIEW_COOKIE_DOMAIN_MAP: dict[str, list[str]] = {
        'snapchat': SnapchatPlatform.COOKIE_DOMAINS,
        'onlyfans': OnlyFansPlatform.COOKIE_DOMAINS,
        'fansly': FanslyPlatform.COOKIE_DOMAINS,
        'fetlife': FetLifePlatform.COOKIE_DOMAINS,
        'threads': ThreadsPlatform.COOKIE_DOMAINS,
    }

    def __init__(self, config: ConfigManager, auth_manager: AuthManager, parent=None):
        super().__init__(parent)
        self._config = config
        self._auth_manager = auth_manager
        self._twitter_pin_handlers: dict[str, object] = {}
        # Holds the most recently used login-window platform so its
        # QWebEngineProfile is not GC'd immediately after dialog.exec() returns.
        # Chromium writes cookies asynchronously; releasing the profile too soon
        # can interrupt pending writes.  Cleared when the next login window opens
        # or when this dialog is closed.
        self._pending_login_platform: object = None

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
        self._create_meta_tab(tabs)

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

    # Meta provider config: (provider_id, display_name, max_accounts, account_ids)
    _META_PROVIDERS: list[tuple[str, str, int, list[str]]] = [
        ('meta_threads', 'Threads', 2, ['meta_threads_1', 'meta_threads_2']),
        ('meta_instagram', 'Instagram', 2, ['meta_instagram_1', 'meta_instagram_2']),
        ('meta_facebook_page', 'Facebook Page', 1, ['meta_facebook_page_1']),
    ]

    def _create_meta_tab(self, tabs: QTabWidget) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        widget = QWidget()
        self._meta_tab_widget = widget
        layout = QVBoxLayout(widget)

        # Per-provider sections; populated by _refresh_meta_status
        self._meta_provider_groups: dict[str, QGroupBox] = {}
        for provider, display_name, _max, _ids in self._META_PROVIDERS:
            group = QGroupBox(display_name)
            layout.addWidget(group)
            self._meta_provider_groups[provider] = group

        # OAuth relay URI setting
        relay_group = QGroupBox('OAuth Relay')
        relay_layout = QFormLayout(relay_group)
        relay_layout.addRow(
            QLabel(
                '<i>HTTPS redirect URI registered in each Meta app dashboard. '
                'All three platforms share the same relay URL.</i>'
            ),
            QLabel(),
        )
        self._meta_oauth_redirect_uri_edit = QLineEdit(
            self._auth_manager.get_meta_oauth_redirect_uri()
        )
        self._meta_oauth_redirect_uri_edit.setPlaceholderText(
            'https://galefling.jasmer.tools/oauth/callback'
        )
        relay_layout.addRow('OAuth Redirect URI:', self._meta_oauth_redirect_uri_edit)
        layout.addWidget(relay_group)

        layout.addStretch()
        scroll.setWidget(widget)
        tabs.addTab(scroll, 'Meta')
        self._refresh_meta_status()

    def _refresh_meta_status(self) -> None:
        """Rebuild the Meta tab provider sections from current auth state."""
        app_cred_fns = {
            'meta_threads': self._auth_manager.has_meta_threads_app_credentials,
            'meta_instagram': self._auth_manager.has_meta_instagram_app_credentials,
            'meta_facebook_page': self._auth_manager.has_meta_facebook_app_credentials,
        }
        get_app_cred_fns = {
            'meta_threads': self._auth_manager.get_meta_threads_app_credentials,
            'meta_instagram': self._auth_manager.get_meta_instagram_app_credentials,
            'meta_facebook_page': self._auth_manager.get_meta_facebook_app_credentials,
        }

        for provider, display_name, _max_accounts, candidate_ids in self._META_PROVIDERS:
            group = self._meta_provider_groups[provider]
            # Clear existing layout contents
            old_layout = group.layout()
            if old_layout is not None:
                while old_layout.count():
                    item = old_layout.takeAt(0)
                    if item is not None:
                        w = item.widget()
                        if w is not None:
                            w.deleteLater()
            group_layout = (
                QVBoxLayout(group) if old_layout is None else cast(QVBoxLayout, old_layout)
            )

            has_app_creds = app_cred_fns[provider]()
            cred_status = (
                'App credentials: configured'
                if has_app_creds
                else 'App credentials: missing — import via Settings → Advanced'
            )
            cred_label = QLabel(f'<i>{cred_status}</i>')
            group_layout.addWidget(cred_label)

            connected_accounts = self._auth_manager.get_accounts_for_platform(provider)

            for account in connected_accounts:
                row_widget = QWidget()
                row = QHBoxLayout(row_widget)
                row.setContentsMargins(0, 0, 0, 0)
                creds = self._auth_manager.get_account_credentials(account.account_id)
                name = account.profile_name or account.account_id
                expires_note = ''
                if creds:
                    expires_at = creds.get('expires_at') or creds.get('user_token_expires_at')
                    if expires_at:
                        expires_note = f' — expires {expires_at[:10]}'
                row.addWidget(QLabel(f'{name}{expires_note}'))
                row.addStretch()
                disconnect_btn = QPushButton('Disconnect')
                disconnect_btn.setProperty('account_id', account.account_id)
                disconnect_btn.clicked.connect(
                    lambda checked, aid=account.account_id: self._disconnect_meta_account(aid)
                )
                row.addWidget(disconnect_btn)
                group_layout.addWidget(row_widget)

            if not connected_accounts:
                group_layout.addWidget(QLabel('<i>No accounts connected.</i>'))

            # Connect button — pick first unused candidate ID
            used_ids = {a.account_id for a in connected_accounts}
            next_id = next((cid for cid in candidate_ids if cid not in used_ids), None)
            can_connect = has_app_creds and next_id is not None
            connect_btn = QPushButton(f'Connect {display_name} Account')
            connect_btn.setEnabled(can_connect)
            connect_btn.clicked.connect(
                lambda checked, p=provider, aid=next_id, gcf=get_app_cred_fns[provider]: (
                    self._launch_meta_connect(p, aid, gcf()) if aid is not None else None
                )
            )
            group_layout.addWidget(connect_btn)

    def _launch_meta_connect(self, provider: str, account_id: str, app_creds: dict) -> None:
        from src.core.meta_oauth import MetaOAuthFlow
        from src.gui.meta_connect_dialog import MetaConnectDialog

        get_logger().info(f'User selected Settings > Meta > Connect {provider}')
        flow = MetaOAuthFlow(provider, app_creds['app_id'], app_creds['app_secret'])
        dlg = MetaConnectDialog(provider, flow, account_id, self._auth_manager, parent=self)
        dlg.exec()
        self._refresh_meta_status()

    def _disconnect_meta_account(self, account_id: str) -> None:
        get_logger().info(f'User selected Settings > Meta > Disconnect {account_id}')
        self._auth_manager.remove_account(account_id)
        self._auth_manager.clear_account_credentials(account_id)
        self._refresh_meta_status()

    def _refresh_aws_display(self) -> None:
        """Reload AWS credential display widgets from stored credentials."""
        aws_creds = self._auth_manager.get_aws_media_staging_credentials()
        raw_key_id = aws_creds.get('access_key_id', '') if aws_creds else ''
        masked = _mask_credential(raw_key_id)
        self._aws_key_id_label.setText(masked if masked else '(not configured)')
        self._aws_region_label.setText(
            aws_creds.get('region', 'us-west-2') if aws_creds else 'us-west-2'
        )
        self._aws_bucket_edit.setText(
            aws_creds.get('media_staging_bucket', '') if aws_creds else ''
        )

    def _import_credentials_from_json(self) -> None:
        get_logger().info('User selected Settings > Import Credentials from JSON')
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            'Import Credentials',
            '',
            'JSON Files (*.json);;All Files (*)',
        )
        if not path_str:
            return

        result: ImportResult = import_credentials(Path(path_str), self._auth_manager)

        if result.errors:
            QMessageBox.warning(
                self,
                'Import Failed',
                'Credential import failed:\n' + '\n'.join(result.errors),
            )
            return

        lines: list[str] = []
        if result.imported:
            lines.append('Imported: ' + ', '.join(result.imported))
        if result.skipped:
            lines.append('Skipped (incomplete): ' + ', '.join(result.skipped))

        if not result.imported:
            QMessageBox.information(
                self,
                'Nothing Imported',
                'No complete credential sections were found in the file.\n'
                + ('\n'.join(lines) if lines else ''),
            )
            return

        QMessageBox.information(
            self,
            'Import Successful',
            'Credentials imported successfully.\n\n' + '\n'.join(lines),
        )
        self._refresh_meta_status()
        self._refresh_aws_display()

    def _test_s3_connection(self) -> None:
        get_logger().info('User selected Settings > Test S3 Connection')
        aws_creds = self._auth_manager.get_aws_media_staging_credentials()
        if not aws_creds:
            QMessageBox.warning(
                self, 'No Credentials', 'AWS credentials have not been imported yet.'
            )
            return

        bucket = self._aws_bucket_edit.text().strip() or aws_creds.get('media_staging_bucket', '')
        if not bucket:
            QMessageBox.warning(self, 'No Bucket', 'S3 bucket name is not configured.')
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            ok, msg = check_s3_connection(
                access_key_id=aws_creds['access_key_id'],
                secret_access_key=aws_creds['secret_access_key'],
                region=aws_creds.get('region', 'us-west-2'),
                bucket=bucket,
            )
        finally:
            QApplication.restoreOverrideCursor()

        if ok:
            QMessageBox.information(self, 'S3 Connection OK', 'S3 connection test passed.')
        else:
            QMessageBox.warning(self, 'S3 Connection Failed', f'S3 connection test failed:\n{msg}')

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

        # Remote debugging
        self._remote_debug_cb = QCheckBox('Enable remote debugging (Chrome DevTools Protocol)')
        remote_debug_port_layout = QHBoxLayout()
        remote_debug_port_layout.addWidget(QLabel('Port:'))
        self._remote_debug_port_spin = QSpinBox()
        self._remote_debug_port_spin.setRange(1024, 65535)
        self._remote_debug_port_spin.setValue(9222)
        self._remote_debug_port_spin.setFixedWidth(80)
        remote_debug_port_layout.addWidget(self._remote_debug_port_spin)
        remote_debug_port_layout.addStretch()
        webview_layout.addWidget(self._remote_debug_cb)
        webview_layout.addLayout(remote_debug_port_layout)
        webview_layout.addWidget(
            QLabel(
                '<i>Session only — not saved to config. Connect via '
                'chrome://inspect or DevTools at the configured port.</i>'
            )
        )

        # Pre-populate from config
        self._remote_debug_cb.setChecked(self._config.remote_debug_enabled)
        self._remote_debug_port_spin.setValue(self._config.remote_debug_port)

        layout.addWidget(webview_group)

        preview_group = QGroupBox('Preview')
        preview_layout = QFormLayout(preview_group)
        self._preview_workers_spin = QSpinBox()
        self._preview_workers_spin.setRange(1, 4)
        self._preview_workers_spin.setValue(self._config.preview_worker_count)
        self._preview_workers_spin.setToolTip(
            'Maximum number of parallel media preview processing workers.'
        )
        preview_layout.addRow('Preview workers:', self._preview_workers_spin)
        layout.addWidget(preview_group)

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

        # Export test config
        export_group = QGroupBox('Functional Tests')
        export_layout = QVBoxLayout(export_group)
        export_layout.addWidget(
            QLabel('<i>Export all configured credentials as a .env file for functional tests.</i>')
        )
        export_test_btn = QPushButton('Export Test Config')
        export_test_btn.clicked.connect(self._export_test_config)
        export_layout.addWidget(export_test_btn)
        layout.addWidget(export_group)

        # Credential import
        import_group = QGroupBox('Credential Import')
        import_layout = QVBoxLayout(import_group)
        import_layout.addWidget(
            QLabel(
                '<i>Import app-level credentials for Meta (Threads/Instagram/Facebook), '
                'Twitter OAuth 2.0, and AWS from a JSON file provided by your administrator. '
                'The file is not modified or deleted by GaleFling after import.</i>'
            )
        )
        import_btn = QPushButton('Import Credentials from JSON\u2026')
        import_btn.clicked.connect(self._import_credentials_from_json)
        import_layout.addWidget(import_btn)
        layout.addWidget(import_group)

        # AWS media staging
        aws_group = QGroupBox('AWS Media Staging')
        aws_layout = QFormLayout(aws_group)

        aws_creds = self._auth_manager.get_aws_media_staging_credentials()
        raw_key_id = aws_creds.get('access_key_id', '') if aws_creds else ''
        masked_key_id = _mask_credential(raw_key_id)
        self._aws_key_id_label = QLabel(masked_key_id if masked_key_id else '(not configured)')
        aws_layout.addRow('Access Key ID:', self._aws_key_id_label)

        self._aws_region_label = QLabel(
            aws_creds.get('region', 'us-west-2') if aws_creds else 'us-west-2'
        )
        aws_layout.addRow('Region:', self._aws_region_label)

        self._aws_bucket_edit = QLineEdit(
            aws_creds.get('media_staging_bucket', '') if aws_creds else ''
        )
        self._aws_bucket_edit.setPlaceholderText('galefling-media-staging-\u2026')
        aws_layout.addRow('S3 Bucket Name:', self._aws_bucket_edit)

        test_s3_btn = QPushButton('Test S3 Connection')
        test_s3_btn.clicked.connect(self._test_s3_connection)
        aws_layout.addRow('', test_s3_btn)

        layout.addWidget(aws_group)

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
        self._config.preview_worker_count = self._preview_workers_spin.value()
        self._config.debug_mode = self._debug_cb.isChecked()
        self._config.set('log_upload_enabled', self._log_upload_cb.isChecked())
        self._config.set('log_upload_endpoint', self._endpoint_edit.text())

        # Remote debugging
        remote_debug_changed = (
            self._remote_debug_cb.isChecked() != self._config.remote_debug_enabled
            or self._remote_debug_port_spin.value() != self._config.remote_debug_port
        )
        self._config.remote_debug_enabled = self._remote_debug_cb.isChecked()
        self._config.remote_debug_port = self._remote_debug_port_spin.value()

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

        # Meta — OAuth relay redirect URI
        meta_relay_uri = self._meta_oauth_redirect_uri_edit.text().strip()
        if meta_relay_uri:
            self._auth_manager.save_meta_oauth_redirect_uri(meta_relay_uri)

        # AWS — update bucket name if the user edited it directly
        aws_bucket_text = self._aws_bucket_edit.text().strip()
        if aws_bucket_text:
            existing_aws = self._auth_manager.get_aws_media_staging_credentials()
            if existing_aws and existing_aws.get('media_staging_bucket') != aws_bucket_text:
                self._auth_manager.save_aws_media_staging_credentials(
                    existing_aws['access_key_id'],
                    existing_aws['secret_access_key'],
                    existing_aws.get('region', 'us-west-2'),
                    aws_bucket_text,
                )

        self._config.save()
        if webview_compatibility_before != self._config.webview_compatibility_mode:
            QMessageBox.information(
                self,
                'Restart Required',
                'WebView compatibility mode changes will apply after restarting GaleFling.',
            )
        if remote_debug_changed:
            QMessageBox.information(
                self,
                'Restart Required',
                'Remote debugging changes will apply after restarting GaleFling.',
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

    def _export_test_config(self) -> None:
        get_logger().info('User selected Settings > Export Test Config')
        lines: list[str] = []

        # Twitter
        app_creds = self._auth_manager.get_twitter_app_credentials() or {}
        tw_creds = self._auth_manager.get_account_credentials('twitter_1') or {}
        api_key = app_creds.get('api_key', '')
        api_secret = app_creds.get('api_secret', '')
        access_token = tw_creds.get('access_token', '')
        access_token_secret = tw_creds.get('access_token_secret', '')
        if api_key or access_token:
            lines.append('# Twitter (OAuth 1.0a)')
            lines.append(f'TWITTER_API_KEY={api_key}')
            lines.append(f'TWITTER_API_SECRET={api_secret}')
            lines.append(f'TWITTER_ACCESS_TOKEN={access_token}')
            lines.append(f'TWITTER_ACCESS_TOKEN_SECRET={access_token_secret}')
            lines.append('')

        # Bluesky
        bs_creds = self._auth_manager.get_bluesky_auth() or {}
        if bs_creds.get('identifier'):
            lines.append('# Bluesky')
            lines.append(f'BLUESKY_IDENTIFIER={bs_creds.get("identifier", "")}')
            lines.append(f'BLUESKY_APP_PASSWORD={bs_creds.get("app_password", "")}')
            lines.append('')

        # Instagram
        ig_creds = self._auth_manager.get_account_credentials('instagram_1') or {}
        if ig_creds.get('access_token'):
            lines.append('# Instagram (Graph API)')
            lines.append(f'INSTAGRAM_ACCESS_TOKEN={ig_creds.get("access_token", "")}')
            lines.append(f'INSTAGRAM_BUSINESS_ACCOUNT_ID={ig_creds.get("account_id", "")}')
            lines.append(f'INSTAGRAM_PAGE_ID={ig_creds.get("page_id", "")}')
            lines.append('')

        # Meta app credentials
        for meta_display, get_fn, prefix in [
            ('Threads', self._auth_manager.get_meta_threads_app_credentials, 'META_THREADS'),
            ('Instagram', self._auth_manager.get_meta_instagram_app_credentials, 'META_INSTAGRAM'),
            ('Facebook', self._auth_manager.get_meta_facebook_app_credentials, 'META_FACEBOOK'),
        ]:
            meta_creds = get_fn()
            if meta_creds:
                lines.append(f'# Meta {meta_display} app credentials')
                lines.append(f'{prefix}_APP_ID={meta_creds.get("app_id", "")}')
                lines.append(f'{prefix}_APP_SECRET={meta_creds.get("app_secret", "")}')
                lines.append('')

        # Meta OAuth relay URI
        lines.append('# Meta OAuth relay redirect URI')
        lines.append(f'META_OAUTH_REDIRECT_URI={self._auth_manager.get_meta_oauth_redirect_uri()}')
        lines.append('')

        # Twitter OAuth 2.0
        tw_oauth2 = self._auth_manager.get_twitter_oauth2_app_credentials()
        if tw_oauth2:
            lines.append('# Twitter OAuth 2.0 app credentials')
            lines.append(f'TWITTER_CLIENT_ID={tw_oauth2.get("client_id", "")}')
            lines.append(f'TWITTER_CLIENT_SECRET={tw_oauth2.get("client_secret", "")}')
            lines.append('')

        # AWS media staging
        aws_creds = self._auth_manager.get_aws_media_staging_credentials()
        if aws_creds:
            lines.append('# AWS media staging')
            lines.append(f'AWS_MEDIA_STAGING_ACCESS_KEY_ID={aws_creds.get("access_key_id", "")}')
            lines.append(
                f'AWS_MEDIA_STAGING_SECRET_ACCESS_KEY={aws_creds.get("secret_access_key", "")}'
            )
            lines.append(f'AWS_MEDIA_STAGING_REGION={aws_creds.get("region", "us-west-2")}')
            lines.append(f'AWS_MEDIA_STAGING_BUCKET={aws_creds.get("media_staging_bucket", "")}')
            lines.append('')

        # WebView platforms — data directory
        data_dir = str(get_app_data_dir())
        lines.append('# WebView platforms — GaleFling data directory')
        lines.append(f'GALEFLING_DATA_DIR={data_dir}')
        lines.append('')

        if len(lines) <= 3:
            QMessageBox.information(
                self,
                'No Credentials',
                'No credentials are configured to export.',
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            'Export Test Config',
            '.env',
            'Environment Files (*.env);;All Files (*)',
        )
        if not path:
            return
        try:
            with open(path, 'w') as f:
                f.write('\n'.join(lines))
            QMessageBox.information(
                self,
                'Export Successful',
                f'Test configuration exported to:\n{path}',
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
        if platform_id == 'threads':
            return ThreadsPlatform(account_id=account_id, profile_name=profile_name)
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
        self._pending_login_platform = None  # release any previous platform first
        dialog = WebViewLoginDialog(platform, specs.platform_name, self)
        dialog.exec()
        # Schedule the dialog (and its QWebEngineView/Page) for deletion via the
        # Qt event loop.  Direct deletion or relying on parent-child GC bypasses
        # Chromium's CrBrowserMain teardown sequence, leaving stale VSync services
        # alive against the profile.  deleteLater() lets the event loop process
        # WebContents destruction before the profile is reused by the next dialog.
        dialog.deleteLater()
        # Keep platform alive so its QWebEngineProfile is not GC'd before
        # Chromium's background cookie writer flushes the session to disk.
        self._pending_login_platform = platform

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
            # Also evict the in-memory profile so the next login window
            # starts with a fresh Chromium context rather than a stale one.
            BaseWebViewPlatform._evict_profile(account_id)
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
