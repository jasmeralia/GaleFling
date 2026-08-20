"""First-run setup wizard for credential configuration."""

import contextlib
import json
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QPalette, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from src.core.auth_manager import AuthManager
from src.core.credential_importer import import_credentials
from src.core.logger import get_logger
from src.gui.icon_utils import tinted_pixmap
from src.platforms.base_webview import BaseWebViewPlatform
from src.platforms.bluesky import BlueskyPlatform
from src.platforms.fansly import FanslyPlatform
from src.platforms.fetlife import FetLifePlatform
from src.platforms.onlyfans import OnlyFansPlatform
from src.platforms.snapchat import SnapchatPlatform
from src.platforms.twitter import TwitterPlatform
from src.utils import tokens
from src.utils.constants import PLATFORM_SPECS_MAP, AccountConfig

_CHECK_SVG_PATH = (
    Path(__file__).resolve().parent.parent / 'resources' / 'icons' / 'ui' / 'check.svg'
)

_WEBVIEW_PLATFORM_DEFS: list[tuple[str, str, str]] = [
    ('snapchat', 'Snapchat', 'snapchat_1'),
    ('onlyfans', 'OnlyFans', 'onlyfans_1'),
    ('fansly', 'Fansly', 'fansly_1'),
    ('fetlife', 'FetLife', 'fetlife_1'),
]

_FIXED_WIZARD_STEP_LABELS: list[str] = [
    'Welcome',
    'Credentials',
    'Twitter',
    'Bluesky',
    'Meta',
]


def _available_webview_platform_defs() -> list[tuple[str, str, str]]:
    """Return WebView platform tuples using the same availability filter as SetupWizard."""
    available: list[tuple[str, str, str]] = []
    for platform_id, platform_name, account_id in _WEBVIEW_PLATFORM_DEFS:
        wizard_specs = PLATFORM_SPECS_MAP.get(platform_id)
        if wizard_specs is not None and not wizard_specs.available:
            continue
        available.append((platform_id, platform_name, account_id))
    return available


def _load_check_pixmap(size: int = 16) -> QPixmap | None:
    """Load the done-step check icon, tinted SUCCESS, with graceful fallback."""
    return tinted_pixmap(_CHECK_SVG_PATH, tokens.SUCCESS, size)


class _StepRailItem(QWidget):
    """One step indicator (dot/check) with a short label."""

    def __init__(self, label: str, check_pixmap: QPixmap | None, parent=None):
        super().__init__(parent)
        self._check_pixmap = check_pixmap
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._indicator = QLabel()
        self._indicator.setFixedSize(20, 20)
        self._indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._indicator, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._label = QLabel(label)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setWordWrap(True)
        self._label.setMaximumWidth(72)
        layout.addWidget(self._label, alignment=Qt.AlignmentFlag.AlignHCenter)

    def apply_state(self, state: str) -> None:
        if state == 'done':
            if self._check_pixmap is not None and not self._check_pixmap.isNull():
                self._indicator.setText('')
                self._indicator.setPixmap(self._check_pixmap)
                self._indicator.setStyleSheet('background: transparent; border: none;')
            else:
                self._indicator.setPixmap(QPixmap())
                self._indicator.setText('\u2713')
                self._indicator.setStyleSheet(
                    f'color: {tokens.SUCCESS}; font-size: 14px; font-weight: bold; '
                    'background: transparent; border: none;'
                )
            self._label.setStyleSheet(
                f'color: {tokens.SUCCESS}; font-size: 10px; font-weight: 600;'
            )
        elif state == 'current':
            self._indicator.setPixmap(QPixmap())
            self._indicator.setText('')
            self._indicator.setStyleSheet(
                f'background-color: {tokens.ACCENT}; border: 2px solid {tokens.ACCENT}; '
                'border-radius: 10px;'
            )
            self._label.setStyleSheet(f'color: {tokens.ACCENT}; font-size: 10px; font-weight: 600;')
        else:
            self._indicator.setPixmap(QPixmap())
            self._indicator.setText('')
            self._indicator.setStyleSheet(
                f'background-color: {tokens.SURFACE_RAISED}; border: 2px solid {tokens.BORDER}; '
                'border-radius: 10px;'
            )
            self._label.setStyleSheet(f'color: {tokens.TEXT_MUTED}; font-size: 10px;')


class _StepRail(QWidget):
    """Horizontal progress rail showing setup wizard steps."""

    def __init__(self, steps: list[tuple[str, int]], parent=None):
        super().__init__(parent)
        self._steps = steps
        self._current_page_id = steps[0][1] if steps else -1
        self._visited_page_ids: set[int] = set()
        self._check_pixmap = _load_check_pixmap()
        self._step_items: list[_StepRailItem] = []
        self._connectors: list[QFrame] = []

        outer = QHBoxLayout(self)
        outer.setContentsMargins(16, 8, 16, 4)
        outer.setSpacing(0)

        for index, (label, _page_id) in enumerate(steps):
            if index > 0:
                connector = QFrame()
                connector.setFixedHeight(2)
                connector.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Fixed,
                )
                self._connectors.append(connector)
                outer.addWidget(connector, stretch=1)

            item = _StepRailItem(label, self._check_pixmap, self)
            self._step_items.append(item)
            outer.addWidget(item, stretch=0)

        self.setFixedHeight(56)
        self.set_progress(self._current_page_id, self._visited_page_ids)

    def set_progress(self, current_page_id: int, visited_page_ids: set[int]) -> None:
        self._current_page_id = current_page_id
        self._visited_page_ids = set(visited_page_ids)
        current_index = self._index_for_page_id(current_page_id)
        for index, item in enumerate(self._step_items):
            if index < current_index:
                item.apply_state('done')
            elif index == current_index:
                item.apply_state('current')
            else:
                item.apply_state('pending')
        for index, connector in enumerate(self._connectors):
            line_color = tokens.ACCENT if index < current_index else tokens.BORDER
            connector.setStyleSheet(f'background-color: {line_color}; border: none;')

    def _index_for_page_id(self, page_id: int) -> int:
        for index, (_label, step_page_id) in enumerate(self._steps):
            if step_page_id == page_id:
                return index
        return 0


class WelcomePage(QWizardPage):
    """Welcome page introducing the setup process."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle('Welcome to GaleFling!')
        self.setAutoFillBackground(True)

        layout = QVBoxLayout(self)
        layout.addSpacing(20)

        intro = QLabel(
            "Let's get you set up to post to your social media accounts!\n\n"
            "We'll walk through each platform step by step.\n"
            'Credentials are stored securely on your computer.\n\n'
            "You can skip any platform you don't use."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet('font-size: 13px; line-height: 1.5;')
        layout.addWidget(intro)
        layout.addStretch()


class CredentialImportPage(QWizardPage):
    """Import app-level credentials (Meta, Twitter, AWS) from a JSON file.

    This page is optional — clicking Next without importing is fine.
    Importing here seeds the subsequent platform pages with the app credentials
    they need before the user tries to connect accounts.
    """

    def __init__(self, auth_manager: AuthManager, parent=None):
        super().__init__(parent)
        self._auth_manager = auth_manager
        self.setAutoFillBackground(True)

        self.setTitle('Setup - App Credentials')
        self.setSubTitle('Import platform app credentials before connecting accounts')

        layout = QVBoxLayout(self)

        info = QLabel(
            'GaleFling requires app-level credentials for Meta (Threads, Instagram, Facebook), '
            'Twitter, and AWS media staging. These are provided as a JSON file by your '
            'administrator.<br><br>'
            '<i>If you have a credentials JSON file, import it now so the platform '
            'pages that follow can use it. You can also import later via '
            'Settings → Advanced → Import Credentials from JSON.</i>'
        )
        info.setWordWrap(True)
        info.setOpenExternalLinks(True)
        layout.addWidget(info)
        layout.addSpacing(12)

        import_btn = QPushButton('Import Credentials from JSON…')
        import_btn.clicked.connect(self._import_credentials)
        layout.addWidget(import_btn)

        self._status_label = QLabel('')
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        layout.addStretch()

    def _import_credentials(self) -> None:
        get_logger().info('User selected Setup Wizard > Import Credentials from JSON')
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            'Import Credentials',
            '',
            'JSON Files (*.json);;All Files (*)',
        )
        if not path_str:
            return

        result = import_credentials(Path(path_str), self._auth_manager)

        if result.errors:
            self._status_label.setText(
                '<span style="color:red;">Import failed: ' + '; '.join(result.errors) + '</span>'
            )
            return

        lines: list[str] = []
        if result.imported:
            lines.append('Imported: ' + ', '.join(result.imported))
        if result.skipped:
            lines.append('Skipped (incomplete): ' + ', '.join(result.skipped))

        if not result.imported:
            self._status_label.setText(
                '<span style="color:orange;">No complete credential sections found.</span>'
                + ('<br>' + '<br>'.join(lines) if lines else '')
            )
            return

        self._status_label.setText(
            '<span style="color:green;">Credentials imported.</span><br>' + '<br>'.join(lines)
        )

    def validatePage(self) -> bool:  # noqa: N802
        return True


class TwitterSetupPage(QWizardPage):
    """Twitter API credentials setup (PIN flow)."""

    def __init__(self, auth_manager: AuthManager, parent=None):
        super().__init__(parent)
        self._auth_manager = auth_manager
        self._pin_handlers: dict[str, object] = {}
        self.setAutoFillBackground(True)

        self.setTitle('Setup - Twitter')
        self.setSubTitle('Twitter API Credentials (PIN Flow)')

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._api_key = QLineEdit()
        self._api_key.setPlaceholderText('Enter your API key')
        form.addRow('API Key:', self._api_key)

        self._api_secret = QLineEdit()
        self._api_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_secret.setPlaceholderText('Enter your API secret')
        form.addRow('API Secret:', self._api_secret)

        layout.addLayout(form)
        layout.addSpacing(10)

        hint = QLabel(
            '<i>Each account is authorized separately. Before clicking '
            '"Start PIN Flow", make sure you are logged into the correct '
            'Twitter account in your web browser. To add a second account, '
            'log out of the first account in your browser first.</i>'
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addSpacing(6)

        self._twitter_accounts: dict[str, dict[str, QLineEdit | QLabel]] = {}
        for account_id, label in [
            ('twitter_1', 'Twitter Account 1'),
            ('twitter_2', 'Twitter Account 2'),
        ]:
            layout.addWidget(QLabel(f'<b>{label}</b>'))

            account_form = QFormLayout()
            username_edit = QLineEdit()
            username_edit.setPlaceholderText('Required for posting')
            account_form.addRow('Username:', username_edit)

            pin_edit = QLineEdit()
            pin_edit.setPlaceholderText('Enter PIN from Twitter')
            account_form.addRow('PIN:', pin_edit)

            btn_row = QHBoxLayout()
            start_btn = QPushButton('Start PIN Flow')
            start_btn.clicked.connect(lambda _=False, aid=account_id: self._start_pin_flow(aid))
            btn_row.addWidget(start_btn)
            complete_btn = QPushButton('Complete PIN')
            complete_btn.clicked.connect(
                lambda _=False, aid=account_id: self._complete_pin_flow(aid)
            )
            btn_row.addWidget(complete_btn)
            btn_row.addStretch()
            account_form.addRow('', btn_row)

            status_label = QLabel()
            account_form.addRow('Status:', status_label)

            layout.addLayout(account_form)
            layout.addSpacing(8)

            self._twitter_accounts[account_id] = {
                'username': username_edit,
                'pin': pin_edit,
                'status': status_label,
            }

        layout.addStretch()

        # Pre-fill if credentials exist
        existing_app = (
            self._auth_manager.get_twitter_app_credentials()
            or self._auth_manager.get_twitter_auth()
        )
        if existing_app:
            self._api_key.setText(existing_app.get('api_key', ''))
            self._api_secret.setText(existing_app.get('api_secret', ''))
        for account_id, widgets in self._twitter_accounts.items():
            account = self._auth_manager.get_account(account_id)
            if account:
                widgets['username'].setText(account.profile_name)
            self._update_status(account_id)

    def _update_status(self, account_id: str):
        widgets = self._twitter_accounts.get(account_id)
        if not widgets:
            return
        creds = self._auth_manager.get_account_credentials(account_id) or {}
        if all(k in creds for k in ('access_token', 'access_token_secret')):
            widgets['status'].setText(
                '<span style="color: #4CAF50; font-weight: bold;">\u2713 Authorized</span>'
            )
        else:
            widgets['status'].setText('Not authorized')

    def _start_pin_flow(self, account_id: str):
        api_key = self._api_key.text().strip()
        api_secret = self._api_secret.text().strip()
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
        self._pin_handlers[account_id] = auth_handler
        QDesktopServices.openUrl(QUrl(url))
        widgets = self._twitter_accounts.get(account_id)
        if widgets:
            widgets['status'].setText('PIN flow started. Enter PIN to complete.')

    def _complete_pin_flow(self, account_id: str):
        widgets = self._twitter_accounts.get(account_id)
        if not widgets:
            return
        username = widgets['username'].text().strip()
        pin = widgets['pin'].text().strip()
        if not username:
            QMessageBox.warning(self, 'Missing Username', 'Please enter a username first.')
            return
        if not pin:
            QMessageBox.warning(self, 'Missing PIN', 'Please enter the PIN from Twitter.')
            return
        auth_handler = self._pin_handlers.get(account_id)
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

        self._auth_manager.save_twitter_app_credentials(
            self._api_key.text().strip(),
            self._api_secret.text().strip(),
        )
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
        widgets['pin'].clear()
        self._update_status(account_id)

    def validatePage(self) -> bool:  # noqa: N802
        api_key = self._api_key.text().strip()
        api_secret = self._api_secret.text().strip()
        if api_key and api_secret:
            self._auth_manager.save_twitter_app_credentials(api_key, api_secret)
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
        return True


class BlueskySetupPage(QWizardPage):
    """Bluesky account setup."""

    def __init__(self, auth_manager: AuthManager, parent=None):
        super().__init__(parent)
        self._auth_manager = auth_manager
        self.setAutoFillBackground(True)

        self.setTitle('Setup - Bluesky')
        self.setSubTitle('Bluesky Account')

        layout = QVBoxLayout(self)
        form = QFormLayout()

        info = QLabel(
            'Bluesky uses <b>app passwords</b> so you do not share your main password. '
            'Create one at '
            '<a href="https://bsky.app/settings/app-passwords">bsky.app/settings/app-passwords</a> '
            'and copy the generated token here. '
            'Do <b>not</b> enable the checkbox for access to DMs. '
            'App passwords cannot delete your account or change your main login password.<br><br>'
            'Your username (handle) is shown on your Bluesky settings page '
            '(<a href="https://bsky.app/settings">bsky.app/settings</a>) and looks like '
            '<i>name.bsky.social</i>.'
        )
        info.setOpenExternalLinks(True)
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addSpacing(8)

        self._identifier = QLineEdit()
        self._identifier.setPlaceholderText('yourname.bsky.social')
        form.addRow('Username (handle):', self._identifier)

        hint = QLabel('Example: yourname.bsky.social')
        muted = self.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text).name()
        hint.setStyleSheet(f'color: {muted}; font-size: 11px;')
        form.addRow('', hint)

        self._app_password = QLineEdit()
        self._app_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._app_password.setPlaceholderText('xxxx-xxxx-xxxx-xxxx')
        form.addRow('App Password:', self._app_password)

        pw_hint = QLabel('Format: xxxx-xxxx-xxxx-xxxx')
        pw_hint.setStyleSheet(f'color: {muted}; font-size: 11px;')
        form.addRow('', pw_hint)

        form.addRow(QLabel('<b>Second Bluesky account (optional)</b>'), QLabel(''))

        self._identifier_alt = QLineEdit()
        self._identifier_alt.setPlaceholderText('secondname.bsky.social')
        form.addRow('Username (handle):', self._identifier_alt)

        hint_alt = QLabel('Example: secondname.bsky.social')
        hint_alt.setStyleSheet(f'color: {muted}; font-size: 11px;')
        form.addRow('', hint_alt)

        self._app_password_alt = QLineEdit()
        self._app_password_alt.setEchoMode(QLineEdit.EchoMode.Password)
        self._app_password_alt.setPlaceholderText('xxxx-xxxx-xxxx-xxxx')
        form.addRow('App Password:', self._app_password_alt)

        pw_hint_alt = QLabel('Format: xxxx-xxxx-xxxx-xxxx')
        pw_hint_alt.setStyleSheet(f'color: {muted}; font-size: 11px;')
        form.addRow('', pw_hint_alt)

        layout.addLayout(form)
        layout.addSpacing(10)

        btn_row = QHBoxLayout()
        test_btn = QPushButton('Test Account 1')
        test_btn.setStyleSheet(
            'QPushButton { background-color: #4CAF50; color: white; '
            'font-weight: bold; font-size: 12px; padding: 4px 12px; '
            'border-radius: 4px; }'
            'QPushButton:hover { background-color: #45a049; }'
            'QPushButton:disabled { background-color: #ccc; color: #888; }'
        )
        test_btn.clicked.connect(self._test_connection)
        btn_row.addWidget(test_btn)
        test_alt_btn = QPushButton('Test Account 2')
        test_alt_btn.setStyleSheet(
            'QPushButton { background-color: #4CAF50; color: white; '
            'font-weight: bold; font-size: 12px; padding: 4px 12px; '
            'border-radius: 4px; }'
            'QPushButton:hover { background-color: #45a049; }'
            'QPushButton:disabled { background-color: #ccc; color: #888; }'
        )
        test_alt_btn.clicked.connect(self._test_connection_alt)
        btn_row.addWidget(test_alt_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._status_label = QLabel()
        layout.addWidget(self._status_label)
        self._status_label_alt = QLabel()
        layout.addWidget(self._status_label_alt)
        layout.addStretch()

        # Pre-fill
        existing = self._auth_manager.get_bluesky_auth()
        if existing:
            self._identifier.setText(existing.get('identifier', ''))
            self._app_password.setText(existing.get('app_password', ''))
        existing_alt = self._auth_manager.get_bluesky_auth_alt()
        if existing_alt:
            self._identifier_alt.setText(existing_alt.get('identifier', ''))
            self._app_password_alt.setText(existing_alt.get('app_password', ''))

    def _test_connection(self):
        self._save_creds()
        platform = BlueskyPlatform(self._auth_manager)
        success, error = platform.test_connection()

        if success:
            self._status_label.setText(
                '<span style="color: #4CAF50; font-weight: bold;">'
                '\u2713 Connected successfully!</span>'
            )
        else:
            self._status_label.setText(
                f'<span style="color: #F44336;">\u274c Connection failed: {error}</span>'
            )

    def _test_connection_alt(self):
        self._save_creds()
        platform = BlueskyPlatform(self._auth_manager, account_key='alt')
        success, error = platform.test_connection()

        if success:
            self._status_label_alt.setText(
                '<span style="color: #4CAF50; font-weight: bold;">'
                '\u2713 Connected successfully!</span>'
            )
        else:
            self._status_label_alt.setText(
                f'<span style="color: #F44336;">\u274c Connection failed: {error}</span>'
            )

    def _save_creds(self):
        identifier = self._identifier.text().strip()
        password = self._app_password.text().strip()
        if identifier and password:
            self._auth_manager.save_bluesky_auth(identifier, password)
        identifier_alt = self._identifier_alt.text().strip()
        password_alt = self._app_password_alt.text().strip()
        if identifier_alt and password_alt:
            self._auth_manager.save_bluesky_auth_alt(identifier_alt, password_alt)

    def _validate_unique_accounts(self) -> bool:
        identifier = self._identifier.text().strip()
        password = self._app_password.text().strip()
        identifier_alt = self._identifier_alt.text().strip()
        password_alt = self._app_password_alt.text().strip()
        if not identifier_alt and not password_alt:
            return True
        if not identifier or not password:
            return True
        if identifier.lower() == identifier_alt.lower() or password == password_alt:
            QMessageBox.warning(
                self,
                'Duplicate Account',
                'Bluesky accounts must be different. Please use a different username '
                'and app password for the second account.',
            )
            return False
        return True

    def validatePage(self) -> bool:  # noqa: N802
        if not self._validate_unique_accounts():
            return False
        self._save_creds()
        identifier = self._identifier.text().strip()
        password = self._app_password.text().strip()
        if identifier and password:
            self._auth_manager.add_account(
                AccountConfig(
                    platform_id='bluesky',
                    account_id='bluesky_1',
                    profile_name=identifier,
                )
            )
        identifier_alt = self._identifier_alt.text().strip()
        password_alt = self._app_password_alt.text().strip()
        if identifier_alt and password_alt:
            self._auth_manager.add_account(
                AccountConfig(
                    platform_id='bluesky',
                    account_id='bluesky_alt',
                    profile_name=identifier_alt,
                )
            )
        return True


class MetaApiSetupPage(QWizardPage):
    """Meta API accounts setup page (Threads, Instagram, and Facebook Page).

    Allows connecting up to two Threads accounts, up to two Instagram accounts,
    and one Facebook Page account via the MetaConnectDialog OAuth flow. Requires
    app credentials to have been imported first via Settings → Advanced →
    Import Credentials from JSON.
    """

    # (provider_id, display_name, account_id)
    _ACCOUNT_DEFS = [
        ('meta_threads', 'Threads Account 1', 'meta_threads_1'),
        ('meta_threads', 'Threads Account 2', 'meta_threads_2'),
        ('meta_instagram', 'Instagram Account 1', 'meta_instagram_1'),
        ('meta_instagram', 'Instagram Account 2', 'meta_instagram_2'),
        ('meta_facebook_page', 'Facebook Page', 'meta_facebook_page_1'),
    ]

    def __init__(self, auth_manager: AuthManager, parent=None):
        super().__init__(parent)
        self._auth_manager = auth_manager
        self.setAutoFillBackground(True)

        self.setTitle('Setup - Meta (Threads, Instagram & Facebook Page)')
        self.setSubTitle('Connect Threads, Instagram, and Facebook Page accounts via Meta OAuth')

        layout = QVBoxLayout(self)

        info = QLabel(
            '<b>Threads</b>, <b>Instagram</b>, and <b>Facebook Page</b> posting require '
            'Meta app credentials.<br>'
            'Import them via <i>Settings → Advanced → Import Credentials from JSON</i>.<br>'
            'Once imported, use the buttons below to connect accounts.<br><br>'
            '<i>You can skip this step and connect accounts later from Settings → Meta.</i>'
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addSpacing(8)

        self._account_widgets: dict[str, dict] = {}

        for provider_id, display_name, account_id in self._ACCOUNT_DEFS:
            row_widget = QWidget()
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)

            label = QLabel(f'<b>{display_name}:</b>')
            label.setMinimumWidth(180)
            row.addWidget(label)

            status_label = QLabel('Not connected')
            row.addWidget(status_label)
            row.addStretch()

            connect_btn = QPushButton('Connect')
            connect_btn.clicked.connect(
                lambda _checked, p=provider_id, aid=account_id: self._connect_account(p, aid)
            )
            row.addWidget(connect_btn)

            layout.addWidget(row_widget)
            self._account_widgets[account_id] = {
                'provider_id': provider_id,
                'status_label': status_label,
                'connect_btn': connect_btn,
            }

        layout.addStretch()
        self._refresh_status()

    def _get_app_creds(self, provider_id: str) -> dict | None:
        if provider_id == 'meta_threads':
            return self._auth_manager.get_meta_threads_app_credentials()
        if provider_id == 'meta_instagram':
            return self._auth_manager.get_meta_instagram_app_credentials()
        if provider_id == 'meta_facebook_page':
            return self._auth_manager.get_meta_facebook_app_credentials()
        return None

    def _refresh_status(self) -> None:
        for account_id, widgets in self._account_widgets.items():
            provider_id = widgets['provider_id']
            app_creds = self._get_app_creds(provider_id)
            account = self._auth_manager.get_account(account_id)

            if account:
                name = account.profile_name or account_id
                widgets['status_label'].setText(
                    f'<span style="color: #4CAF50; font-weight: bold;">\u2713 {name}</span>'
                )
                widgets['connect_btn'].setText('Reconnect')
            else:
                widgets['status_label'].setText('Not connected')
                widgets['connect_btn'].setText('Connect')

            widgets['connect_btn'].setEnabled(bool(app_creds))
            if not app_creds:
                widgets['connect_btn'].setToolTip(
                    'Import app credentials first via Settings \u2192 Advanced \u2192 '
                    'Import Credentials from JSON'
                )
            else:
                widgets['connect_btn'].setToolTip('')

    def _connect_account(self, provider_id: str, account_id: str) -> None:
        from src.core.meta_oauth import MetaOAuthFlow
        from src.gui.meta_connect_dialog import MetaConnectDialog

        app_creds = self._get_app_creds(provider_id)
        if not app_creds:
            QMessageBox.warning(
                self,
                'App Credentials Missing',
                'Import Meta app credentials first via\n'
                'Settings \u2192 Advanced \u2192 Import Credentials from JSON.',
            )
            return

        get_logger().info(
            f'User selected Setup Wizard > Meta > Connect {provider_id} ({account_id})'
        )
        flow = MetaOAuthFlow(provider_id, app_creds['app_id'], app_creds['app_secret'])
        dlg = MetaConnectDialog(provider_id, flow, account_id, self._auth_manager, parent=self)
        dlg.exec()
        self._refresh_status()

    def validatePage(self) -> bool:  # noqa: N802
        return True


class WebViewPlatformSetupPage(QWizardPage):
    """Generic setup page for WebView-based platforms.

    The user enters a profile name; login happens when they first post.
    """

    def __init__(
        self,
        auth_manager: AuthManager,
        platform_id: str,
        platform_name: str,
        account_id: str,
        parent=None,
    ):
        super().__init__(parent)
        self._auth_manager = auth_manager
        self._platform_id = platform_id
        self._account_id = account_id
        self._platform_name = platform_name
        self._pending_login_platform: object = None
        self.setAutoFillBackground(True)

        self.setTitle(f'Setup - {platform_name}')
        self.setSubTitle(f'{platform_name} Account')

        layout = QVBoxLayout(self)

        specs = PLATFORM_SPECS_MAP.get(platform_id)
        self._supports_embedded_login = specs is None or specs.supports_embedded_login

        if self._supports_embedded_login:
            info_text = (
                f'{platform_name} uses an <b>embedded browser</b> for posting. '
                f'You can log in now to save your session cookies, or skip and '
                f'log in later when you post.<br><br>'
                f'Enter a profile name below so you can identify this account, '
                f'or leave blank to skip.'
            )
        else:
            info_text = (
                f'{platform_name} uses an <b>embedded browser</b> for posting, but '
                f'blocks logging in from one. Log in with your normal browser, export '
                f'the session to an auth.json file, then import it from '
                f'<b>Settings &gt; {platform_name}</b> after setup.<br><br>'
                f'Enter a profile name below so you can identify this account, '
                f'or leave blank to skip.'
            )
        info = QLabel(info_text)
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addSpacing(8)

        form = QFormLayout()
        self._profile_name = QLineEdit()
        self._profile_name.setPlaceholderText(f'{platform_name} username')
        form.addRow('Profile Name:', self._profile_name)
        layout.addLayout(form)
        layout.addSpacing(8)

        self._login_btn: QPushButton | None = None
        if self._supports_embedded_login:
            login_row = QHBoxLayout()
            self._login_btn = QPushButton('Open Login Window')
            self._login_btn.clicked.connect(self._open_login_window)
            login_row.addWidget(self._login_btn)
            login_row.addStretch()
            layout.addLayout(login_row)

        self._status_label = QLabel('Login not detected')
        layout.addWidget(self._status_label)
        layout.addStretch()

        # Pre-fill
        existing = self._auth_manager.get_account(account_id)
        if existing:
            self._profile_name.setText(existing.profile_name)
        self._update_login_status()

    def _create_platform(self) -> BaseWebViewPlatform | None:
        platform_map = {
            'snapchat': SnapchatPlatform,
            'onlyfans': OnlyFansPlatform,
            'fansly': FanslyPlatform,
            'fetlife': FetLifePlatform,
        }
        platform_cls = platform_map.get(self._platform_id)
        if not platform_cls:
            return None
        profile_name = self._profile_name.text().strip()
        return platform_cls(  # type: ignore[abstract]
            account_id=self._account_id,
            profile_name=profile_name,
        )

    def _update_login_status(self):
        platform = self._create_platform()
        if platform and platform.has_valid_session():
            self._status_label.setText(
                '<span style="color: #4CAF50; font-weight: bold;">\u2713 Login detected</span>'
            )
        else:
            self._status_label.setText('Login not detected')

    def _open_login_window(self):
        name = self._profile_name.text().strip()
        if not name:
            QMessageBox.warning(
                self,
                'Missing Profile Name',
                'Please enter a profile name before logging in.',
            )
            return
        platform = self._create_platform()
        if not platform:
            QMessageBox.warning(
                self,
                'Unsupported Platform',
                'This platform does not support embedded login.',
            )
            return
        self._pending_login_platform = None  # release any previous platform first
        dialog = WebViewLoginDialog(platform, self._platform_name, self)
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
        if dialog.login_detected:
            self._status_label.setText(
                '<span style="color: #4CAF50; font-weight: bold;">\u2713 Login detected</span>'
            )
        else:
            self._status_label.setText('Checking login status...')
            # QWebEngine may flush persistent cookies shortly after dialog close.
            QTimer.singleShot(1200, self._update_login_status)

    def validatePage(self) -> bool:  # noqa: N802
        name = self._profile_name.text().strip()
        if name:
            self._auth_manager.add_account(
                AccountConfig(
                    platform_id=self._platform_id,
                    account_id=self._account_id,
                    profile_name=name,
                )
            )
        return True


class WebViewLoginDialog(QDialog):
    """Dialog that lets users log in via embedded WebView."""

    login_detected = False

    def __init__(self, platform: BaseWebViewPlatform, platform_name: str, parent=None):
        super().__init__(parent)
        self._platform = platform
        self.login_detected = False
        self._cookie_store = None
        self.setWindowTitle(f'Log in to {platform_name}')
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setMinimumSize(900, 700)
        self.showMaximized()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        self._status_banner = QLabel('\u23f3 Waiting for login detection...')
        self._status_banner.setStyleSheet(
            'background-color: #FFF3CD; color: #8A6D3B; font-weight: bold; '
            'padding: 8px; border-radius: 4px;'
        )
        self._status_banner.setWordWrap(True)
        layout.addWidget(self._status_banner)
        info = QLabel(
            'Log in to your account below. The banner above updates when login '
            'is detected. Your session cookies are stored locally for future '
            'posts. Close this window when you are done.'
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self._view = self._platform.create_webview(self)
        layout.addWidget(self._view, stretch=1)
        page = self._view.page() if hasattr(self._view, 'page') else None
        profile = page.profile() if page else None
        if profile is not None:
            self._cookie_store = profile.cookieStore()
            if self._cookie_store is not None:
                self._cookie_store.cookieAdded.connect(self._on_cookie_added)
        if page is not None:
            page.loadFinished.connect(self._on_page_load_finished)

        with contextlib.suppress(AttributeError, TypeError):
            self._view.renderProcessTerminated.connect(self._on_render_crash)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._platform.navigate_to_login()

        # Poll as a fallback; primary detection is cookieAdded and loadFinished.
        self._login_timer = QTimer(self)
        self._login_timer.setInterval(3000)
        self._login_timer.timeout.connect(self._check_login)
        self._login_timer.start()

    def _on_page_load_finished(self, ok: bool):
        """Check for existing session after each page load completes.

        cookieAdded only fires when new cookies arrive — it misses the case where
        the user already has a valid session and the page loads straight to the
        feed/timeline without setting any new cookies.  This handler runs a DOM
        check after every loadFinished so that pre-existing logins are detected.
        """
        if not ok or self.login_detected:
            return
        page = self._view.page() if self._view else None
        if not page:
            return
        current_url = page.url().toString()
        if not current_url or current_url == 'about:blank':
            return
        if self._platform._is_login_redirect_url(current_url):
            return

        selectors = getattr(self._platform, 'SESSION_EXPIRED_SELECTORS', [])
        delay = getattr(self._platform, 'SESSION_EXPIRED_CHECK_DELAY_MS', 0)

        def _do_dom_check():
            if self.login_detected:
                return
            if not selectors:
                self._mark_login_detected()
                return
            combined = json.dumps(', '.join(selectors))
            page.runJavaScript(
                f'!!document.querySelector({combined})',
                lambda found: None if found else self._mark_login_detected(),
            )

        if delay > 0:
            QTimer.singleShot(delay, _do_dom_check)
        else:
            _do_dom_check()

    def _check_login(self):
        """Polling fallback: check session via cookie inspection."""
        if self.login_detected:
            return
        if self._platform.has_valid_session():
            self._mark_login_detected()

    def _on_cookie_added(self, cookie):
        if self.login_detected:
            return
        host_raw = cookie.domain()
        host = (
            host_raw
            if isinstance(host_raw, str)
            else bytes(host_raw).decode('utf-8', errors='ignore')
        )
        cookie_name = bytes(cookie.name()).decode('utf-8', errors='ignore')
        if self._platform.is_session_cookie(host, cookie_name):
            self._mark_login_detected()

    def _mark_login_detected(self):
        self.login_detected = True
        self._status_banner.setText(
            '\u2713 Login detected. You can continue using this browser tab '
            'or click Close when finished.'
        )
        self._status_banner.setStyleSheet(
            'background-color: #E8F5E9; color: #2E7D32; font-weight: bold; '
            'padding: 8px; border-radius: 4px;'
        )
        self._login_timer.stop()

    def _on_render_crash(self, termination_status, exit_code: int):
        """Handle WebView renderer crash — show a clear error in the status banner."""
        self._login_timer.stop()
        self._status_banner.setText(
            '\u26a0\ufe0f The browser crashed while loading this page '
            f'(exit code: {exit_code}). '
            'This can happen on Snapchat when the session has expired and the page '
            'uses unsupported graphics. '
            'Please close this window and re-open the login window to try again.'
        )
        self._status_banner.setStyleSheet(
            'background-color: #FDECEA; color: #B71C1C; font-weight: bold; '
            'padding: 8px; border-radius: 4px;'
        )

    def closeEvent(self, event):  # noqa: N802
        if hasattr(self, '_login_timer'):
            self._login_timer.stop()
        if self._cookie_store is not None:
            with contextlib.suppress(TypeError, RuntimeError):
                self._cookie_store.cookieAdded.disconnect(self._on_cookie_added)
        page = self._view.page() if (self._view and hasattr(self._view, 'page')) else None
        if page is not None:
            with contextlib.suppress(TypeError, RuntimeError):
                page.loadFinished.disconnect(self._on_page_load_finished)
        with contextlib.suppress(AttributeError, TypeError, RuntimeError):
            self._view.renderProcessTerminated.disconnect(self._on_render_crash)
        event.accept()


class SetupWizard(QWizard):
    """First-run setup wizard."""

    def __init__(self, auth_manager: AuthManager, parent=None):
        super().__init__(parent)
        logger = get_logger()
        logger.info('Setup wizard init starting')
        self.setWindowTitle('GaleFling - Setup')
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setMinimumSize(600, 550)
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setAutoFillBackground(True)

        logger.info('Setup wizard adding pages')
        steps: list[tuple[str, int]] = []

        page_id = self.addPage(WelcomePage())
        steps.append((_FIXED_WIZARD_STEP_LABELS[0], page_id))
        page_id = self.addPage(CredentialImportPage(auth_manager))
        steps.append((_FIXED_WIZARD_STEP_LABELS[1], page_id))
        page_id = self.addPage(TwitterSetupPage(auth_manager))
        steps.append((_FIXED_WIZARD_STEP_LABELS[2], page_id))
        page_id = self.addPage(BlueskySetupPage(auth_manager))
        steps.append((_FIXED_WIZARD_STEP_LABELS[3], page_id))
        page_id = self.addPage(MetaApiSetupPage(auth_manager))
        steps.append((_FIXED_WIZARD_STEP_LABELS[4], page_id))

        for platform_id, platform_name, account_id in _available_webview_platform_defs():
            page_id = self.addPage(
                WebViewPlatformSetupPage(
                    auth_manager,
                    platform_id,
                    platform_name,
                    account_id,
                )
            )
            steps.append((platform_name, page_id))

        self._visited_page_ids: set[int] = set()
        self._step_rail = _StepRail(steps, parent=self)

        initial_id = self.currentId()
        self._visited_page_ids.add(initial_id)
        self._install_step_rail_on_page(initial_id)
        self._step_rail.set_progress(initial_id, self._visited_page_ids)
        self.currentIdChanged.connect(self._on_wizard_current_id_changed)

        self.setButtonText(QWizard.WizardButton.FinishButton, 'Finish')
        logger.info('Setup wizard init complete')

    def _install_step_rail_on_page(self, page_id: int) -> None:
        """Reparent the shared progress rail into the current page's own layout.

        QWizardPage layouts are public API (every page here builds its own
        QVBoxLayout as the first line of __init__); inserting a widget into a
        different layout reparents it automatically. This avoids introspecting
        QWizard's internal chrome layout, whose structure isn't public API and
        varies enough between Qt builds that a fixed-cell assumption breaks
        silently (confirmed: it produced a squashed, overlapping rail).
        """
        page = self.page(page_id)
        page_layout = page.layout() if page is not None else None
        if not isinstance(page_layout, QVBoxLayout):
            return
        if page_layout.indexOf(self._step_rail) != 0:
            page_layout.insertWidget(0, self._step_rail)

    def _on_wizard_current_id_changed(self, page_id: int) -> None:
        self._visited_page_ids.add(page_id)
        self._install_step_rail_on_page(page_id)
        self._step_rail.set_progress(page_id, self._visited_page_ids)
