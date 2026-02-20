"""Settings dialog for debug mode, updates, and log configuration."""

from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.auth_manager import AuthManager
from src.core.config_manager import ConfigManager


class SettingsDialog(QDialog):
    """Application settings with tabs for general, auth, and debug."""

    def __init__(self, config: ConfigManager, auth_manager: AuthManager, parent=None):
        super().__init__(parent)
        self._config = config
        self._auth_manager = auth_manager

        self.setWindowTitle('Settings')
        self.setMinimumSize(500, 450)

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
        self._tw_api_key.setEchoMode(QLineEdit.Password)
        tw_layout.addRow('API Key:', self._tw_api_key)

        self._tw_api_secret = QLineEdit(tw_creds.get('api_secret', '') if tw_creds else '')
        self._tw_api_secret.setEchoMode(QLineEdit.Password)
        tw_layout.addRow('API Secret:', self._tw_api_secret)

        self._tw_access_token = QLineEdit(tw_creds.get('access_token', '') if tw_creds else '')
        self._tw_access_token.setEchoMode(QLineEdit.Password)
        tw_layout.addRow('Access Token:', self._tw_access_token)

        self._tw_access_secret = QLineEdit(
            tw_creds.get('access_token_secret', '') if tw_creds else ''
        )
        self._tw_access_secret.setEchoMode(QLineEdit.Password)
        tw_layout.addRow('Access Token Secret:', self._tw_access_secret)

        layout.addWidget(tw_group)

        # Bluesky
        bs_group = QGroupBox('Bluesky')
        bs_layout = QFormLayout(bs_group)

        bs_creds = self._auth_manager.get_bluesky_auth()
        self._bs_identifier = QLineEdit(bs_creds.get('identifier', '') if bs_creds else '')
        bs_layout.addRow('Username (handle):', self._bs_identifier)

        self._bs_app_password = QLineEdit(bs_creds.get('app_password', '') if bs_creds else '')
        self._bs_app_password.setEchoMode(QLineEdit.Password)
        bs_layout.addRow('App Password:', self._bs_app_password)

        layout.addWidget(bs_group)

        layout.addStretch()
        return widget

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

        self._config.save()
        self.accept()
