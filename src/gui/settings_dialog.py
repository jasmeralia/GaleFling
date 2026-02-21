"""Settings dialog for debug mode, updates, and log configuration."""

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
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
from src.utils.constants import PLATFORM_SPECS_MAP, AccountConfig


class SettingsDialog(QDialog):
    """Application settings with tabs for general, auth, and debug."""

    def __init__(self, config: ConfigManager, auth_manager: AuthManager, parent=None):
        super().__init__(parent)
        self._config = config
        self._auth_manager = auth_manager

        self.setWindowTitle('Settings')
        self.setMinimumSize(500, 500)

        layout = QVBoxLayout(self)

        tabs = QTabWidget()

        # General tab
        general_tab = self._create_general_tab()
        tabs.addTab(general_tab, 'General')

        # Accounts tab
        accounts_tab = self._create_accounts_tab()
        tabs.addTab(accounts_tab, 'Accounts')

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

    def _create_accounts_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Twitter
        tw_group = QGroupBox('Twitter')
        tw_layout = QFormLayout(tw_group)

        tw_creds = self._auth_manager.get_twitter_auth()
        self._tw_username = QLineEdit(tw_creds.get('username', '') if tw_creds else '')
        self._tw_username.setPlaceholderText('Required for posting')
        tw_layout.addRow('Username:', self._tw_username)

        self._tw_api_key = QLineEdit(tw_creds.get('api_key', '') if tw_creds else '')
        self._tw_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        tw_layout.addRow('API Key:', self._tw_api_key)

        self._tw_api_secret = QLineEdit(tw_creds.get('api_secret', '') if tw_creds else '')
        self._tw_api_secret.setEchoMode(QLineEdit.EchoMode.Password)
        tw_layout.addRow('API Secret:', self._tw_api_secret)

        self._tw_access_token = QLineEdit(tw_creds.get('access_token', '') if tw_creds else '')
        self._tw_access_token.setEchoMode(QLineEdit.EchoMode.Password)
        tw_layout.addRow('Access Token:', self._tw_access_token)

        self._tw_access_secret = QLineEdit(
            tw_creds.get('access_token_secret', '') if tw_creds else ''
        )
        self._tw_access_secret.setEchoMode(QLineEdit.EchoMode.Password)
        tw_layout.addRow('Access Token Secret:', self._tw_access_secret)

        tw_logout = QPushButton('Logout')
        tw_logout.clicked.connect(self._logout_twitter)
        tw_layout.addRow('', tw_logout)

        layout.addWidget(tw_group)

        # Bluesky
        bs_group = QGroupBox('Bluesky')
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

        # Bluesky Account 2
        bs_alt_group = QGroupBox('Bluesky (Account 2)')
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

        # Instagram
        ig_group = QGroupBox('Instagram')
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

        # WebView platforms — show configured accounts with login/logout buttons
        self._webview_profile_edits: dict[str, QLineEdit] = {}
        for platform_id, specs in PLATFORM_SPECS_MAP.items():
            if specs.api_type != 'webview':
                continue
            group = QGroupBox(specs.platform_name)
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

            layout.addWidget(group)

        layout.addStretch()
        scroll.setWidget(widget)
        return scroll

    def _create_advanced_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

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
        # General
        self._config.set('auto_check_updates', self._auto_update_cb.isChecked())
        self._config.set('allow_prerelease_updates', self._prerelease_update_cb.isChecked())
        self._config.set('auto_save_draft', self._auto_save_cb.isChecked())

        # Advanced
        self._config.debug_mode = self._debug_cb.isChecked()
        self._config.set('log_upload_enabled', self._log_upload_cb.isChecked())
        self._config.set('log_upload_endpoint', self._endpoint_edit.text())

        # Accounts - Twitter
        tw_key = self._tw_api_key.text().strip()
        tw_secret = self._tw_api_secret.text().strip()
        tw_token = self._tw_access_token.text().strip()
        tw_token_secret = self._tw_access_secret.text().strip()
        tw_username = self._tw_username.text().strip()
        if tw_key and tw_secret and tw_token and tw_token_secret and tw_username:
            self._auth_manager.save_twitter_auth(
                tw_key, tw_secret, tw_token, tw_token_secret, username=tw_username
            )

        # Accounts - Bluesky
        bs_id = self._bs_identifier.text().strip()
        bs_pw = self._bs_app_password.text().strip()
        if bs_id and bs_pw:
            self._auth_manager.save_bluesky_auth(bs_id, bs_pw)

        # Accounts - Bluesky (Account 2)
        bs_alt_id = self._bs_alt_identifier.text().strip()
        bs_alt_pw = self._bs_alt_app_password.text().strip()
        if bs_alt_id and bs_alt_pw:
            self._auth_manager.save_bluesky_auth_alt(bs_alt_id, bs_alt_pw)

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

    def _logout_twitter(self):
        self._auth_manager.clear_twitter_auth()
        self._tw_username.clear()
        self._tw_api_key.clear()
        self._tw_api_secret.clear()
        self._tw_access_token.clear()
        self._tw_access_secret.clear()

    def _logout_bluesky(self):
        self._auth_manager.clear_bluesky_auth()
        self._bs_identifier.clear()
        self._bs_app_password.clear()

    def _logout_bluesky_alt(self):
        self._auth_manager.clear_bluesky_auth_alt()
        self._bs_alt_identifier.clear()
        self._bs_alt_app_password.clear()

    def _logout_instagram(self):
        self._auth_manager.clear_account_credentials('instagram_1')
        self._auth_manager.remove_account('instagram_1')
        self._ig_access_token.clear()
        self._ig_user_id.clear()
        self._ig_page_id.clear()
        self._ig_profile_name.clear()
