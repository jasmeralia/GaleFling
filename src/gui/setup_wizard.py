"""First-run setup wizard for credential configuration."""

from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import (
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
from src.platforms.bluesky import BlueskyPlatform
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
    """Twitter API credentials setup."""

    def __init__(self, auth_manager: AuthManager, parent=None):
        super().__init__(parent)
        self._auth_manager = auth_manager
        self._connection_tested = False
        self.setAutoFillBackground(True)

        self.setTitle('Setup - Twitter')
        self.setSubTitle('Twitter API Credentials')

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._username = QLineEdit()
        self._username.setPlaceholderText('Required for posting')
        form.addRow('Username:', self._username)

        self._api_key = QLineEdit()
        self._api_key.setPlaceholderText('Enter your API key')
        form.addRow('API Key:', self._api_key)

        self._api_secret = QLineEdit()
        self._api_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_secret.setPlaceholderText('Enter your API secret')
        form.addRow('API Secret:', self._api_secret)

        self._access_token = QLineEdit()
        self._access_token.setPlaceholderText('Enter your access token')
        form.addRow('Access Token:', self._access_token)

        self._access_secret = QLineEdit()
        self._access_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self._access_secret.setPlaceholderText('Enter your access token secret')
        form.addRow('Access Token Secret:', self._access_secret)

        layout.addLayout(form)
        layout.addSpacing(10)

        btn_row = QHBoxLayout()
        test_btn = QPushButton('Test Connection')
        test_btn.clicked.connect(self._test_connection)
        btn_row.addWidget(test_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._status_label = QLabel()
        layout.addWidget(self._status_label)
        layout.addStretch()

        # Pre-fill if credentials exist
        existing = self._auth_manager.get_twitter_auth()
        if existing:
            self._username.setText(existing.get('username', ''))
            self._api_key.setText(existing.get('api_key', ''))
            self._api_secret.setText(existing.get('api_secret', ''))
            self._access_token.setText(existing.get('access_token', ''))
            self._access_secret.setText(existing.get('access_token_secret', ''))

    def _test_connection(self):
        self._save_creds()
        platform = TwitterPlatform(self._auth_manager)
        success, error = platform.test_connection()

        if success:
            self._status_label.setText(
                '<span style="color: #4CAF50; font-weight: bold;">'
                '\u2713 Connected successfully!</span>'
            )
            self._connection_tested = True
        else:
            self._status_label.setText(
                f'<span style="color: #F44336;">\u274c Connection failed: {error}</span>'
            )

    def _save_creds(self):
        key = self._api_key.text().strip()
        secret = self._api_secret.text().strip()
        token = self._access_token.text().strip()
        token_secret = self._access_secret.text().strip()
        username = self._username.text().strip()
        if key and secret and token and token_secret and username:
            self._auth_manager.save_twitter_auth(
                key, secret, token, token_secret, username=username
            )

    def validatePage(self) -> bool:  # noqa: N802
        self._save_creds()
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
        self.setAutoFillBackground(True)

        self.setTitle(f'Setup - {platform_name}')
        self.setSubTitle(f'{platform_name} Account')

        layout = QVBoxLayout(self)

        info = QLabel(
            f'{platform_name} uses an <b>embedded browser</b> for posting. '
            f'You will log in when you first post — your session cookies '
            f'are stored locally on your computer.<br><br>'
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
        layout.addStretch()

        # Pre-fill
        existing = self._auth_manager.get_account(account_id)
        if existing:
            self._profile_name.setText(existing.profile_name)

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


class SetupWizard(QWizard):
    """First-run setup wizard."""

    def __init__(self, auth_manager: AuthManager, theme_mode: str = 'system', parent=None):
        super().__init__(parent)
        logger = get_logger()
        logger.info('Setup wizard init starting')
        self.setWindowTitle('GaleFling - Setup')
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
