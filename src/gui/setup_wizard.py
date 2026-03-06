"""First-run setup wizard for credential configuration."""

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QPalette
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from src.core.auth_manager import AuthManager
from src.core.logger import get_logger
from src.platforms.base_webview import BaseWebViewPlatform
from src.platforms.bluesky import BlueskyPlatform
from src.platforms.fansly import FanslyPlatform
from src.platforms.fetlife import FetLifePlatform
from src.platforms.onlyfans import OnlyFansPlatform
from src.platforms.snapchat import SnapchatPlatform
from src.platforms.twitter import TwitterPlatform
from src.utils.constants import AccountConfig


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


class InstagramSetupPage(QWizardPage):
    """Instagram Graph API credentials setup."""

    def __init__(self, auth_manager: AuthManager, parent=None):
        super().__init__(parent)
        self._auth_manager = auth_manager
        self.setAutoFillBackground(True)

        self.setTitle('Setup - Instagram')
        self.setSubTitle('Instagram Graph API (requires Business/Creator account)')

        layout = QVBoxLayout(self)

        info = QLabel(
            'Instagram posting requires a <b>Business</b> or <b>Creator</b> account '
            'linked to a Facebook Page. You will need:<br>'
            '<ul>'
            '<li>A long-lived access token from the Graph API</li>'
            '<li>Your Instagram User ID</li>'
            '<li>Your linked Facebook Page ID</li>'
            '</ul>'
            "<i>Skip this step if you don't have an Instagram Business account.</i>"
        )
        info.setOpenExternalLinks(True)
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addSpacing(8)

        form = QFormLayout()

        self._profile_name = QLineEdit()
        self._profile_name.setPlaceholderText('e.g. rinthemodel')
        form.addRow('Profile Name:', self._profile_name)

        self._access_token = QLineEdit()
        self._access_token.setEchoMode(QLineEdit.EchoMode.Password)
        self._access_token.setPlaceholderText('Long-lived access token')
        form.addRow('Access Token:', self._access_token)

        self._ig_user_id = QLineEdit()
        self._ig_user_id.setPlaceholderText('e.g. 17841400000')
        form.addRow('IG User ID:', self._ig_user_id)

        self._page_id = QLineEdit()
        self._page_id.setPlaceholderText('e.g. 100000000000')
        form.addRow('Facebook Page ID:', self._page_id)

        layout.addLayout(form)
        layout.addStretch()

        # Pre-fill
        existing = self._auth_manager.get_account_credentials('instagram_1')
        if existing:
            self._profile_name.setText(existing.get('profile_name', ''))
            self._access_token.setText(existing.get('access_token', ''))
            self._ig_user_id.setText(existing.get('ig_user_id', ''))
            self._page_id.setText(existing.get('page_id', ''))

    def validatePage(self) -> bool:  # noqa: N802
        token = self._access_token.text().strip()
        uid = self._ig_user_id.text().strip()
        page_id = self._page_id.text().strip()
        name = self._profile_name.text().strip()

        if token and uid:
            self._auth_manager.save_account_credentials(
                'instagram_1',
                {
                    'access_token': token,
                    'ig_user_id': uid,
                    'page_id': page_id,
                    'profile_name': name,
                },
            )
            self._auth_manager.add_account(
                AccountConfig(
                    platform_id='instagram',
                    account_id='instagram_1',
                    profile_name=name,
                )
            )
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
        self.setAutoFillBackground(True)

        self.setTitle(f'Setup - {platform_name}')
        self.setSubTitle(f'{platform_name} Account')

        layout = QVBoxLayout(self)

        info = QLabel(
            f'{platform_name} uses an <b>embedded browser</b> for posting. '
            f'You can log in now to save your session cookies, or skip and '
            f'log in later when you post.<br><br>'
            f'Enter a profile name below so you can identify this account, '
            f'or leave blank to skip.'
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addSpacing(8)

        form = QFormLayout()
        self._profile_name = QLineEdit()
        self._profile_name.setPlaceholderText(f'{platform_name} username')
        form.addRow('Profile Name:', self._profile_name)
        layout.addLayout(form)
        layout.addSpacing(8)

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
        dialog = WebViewLoginDialog(platform, self._platform_name, self)
        dialog.exec()
        self._update_login_status()
        if dialog.login_detected and self._profile_name.text().strip():
            wizard = self.wizard()
            if wizard:
                wizard.next()

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
        info = QLabel(
            'Log in to your account below. This window will close automatically '
            'once login is detected. Your session cookies are stored locally for '
            'future posts.'
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        view = self._platform.create_webview(self)
        layout.addWidget(view, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._platform.navigate_to_composer()

        # Poll for successful login via cookie detection
        self._login_timer = QTimer(self)
        self._login_timer.setInterval(2000)
        self._login_timer.timeout.connect(self._check_login)
        self._login_timer.start()

    def _check_login(self):
        """Check if the user has successfully logged in."""
        if self._platform.has_valid_session():
            self._login_timer.stop()
            self.login_detected = True
            self.accept()

    def closeEvent(self, event):  # noqa: N802
        self._login_timer.stop()
        event.accept()


class SetupWizard(QWizard):
    """First-run setup wizard."""

    def __init__(self, auth_manager: AuthManager, theme_mode: str = 'system', parent=None):
        super().__init__(parent)
        logger = get_logger()
        logger.info('Setup wizard init starting')
        self.setWindowTitle('GaleFling - Setup')
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setMinimumSize(600, 500)
        self._theme_mode = theme_mode
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setAutoFillBackground(True)

        logger.info('Setup wizard adding pages')
        self.addPage(WelcomePage())
        self.addPage(TwitterSetupPage(auth_manager))
        self.addPage(BlueskySetupPage(auth_manager))
        self.addPage(InstagramSetupPage(auth_manager))

        # WebView platforms
        for platform_id, platform_name, account_id in [
            ('snapchat', 'Snapchat', 'snapchat_1'),
            ('onlyfans', 'OnlyFans', 'onlyfans_1'),
            ('fansly', 'Fansly', 'fansly_1'),
            ('fetlife', 'FetLife', 'fetlife_1'),
        ]:
            self.addPage(
                WebViewPlatformSetupPage(
                    auth_manager,
                    platform_id,
                    platform_name,
                    account_id,
                )
            )

        self.setButtonText(QWizard.WizardButton.FinishButton, 'Finish')
        logger.info('Setup wizard init complete')
