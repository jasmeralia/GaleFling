"""First-run setup wizard for credential configuration."""

from PyQt5.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from src.core.auth_manager import AuthManager
from src.platforms.bluesky import BlueskyPlatform
from src.platforms.twitter import TwitterPlatform


class WelcomePage(QWizardPage):
    """Welcome page introducing the setup process."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Welcome to GalePost!")

        layout = QVBoxLayout(self)
        layout.addSpacing(20)

        intro = QLabel(
            "Let's get you set up to post to Twitter and Bluesky!\n\n"
            "We'll need your account credentials for each platform.\n"
            "Don't worry - they're stored securely on your computer.\n\n"
            "This should only take a minute."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("font-size: 13px; line-height: 1.5;")
        layout.addWidget(intro)
        layout.addStretch()


class TwitterSetupPage(QWizardPage):
    """Twitter API credentials setup."""

    def __init__(self, auth_manager: AuthManager, parent=None):
        super().__init__(parent)
        self._auth_manager = auth_manager
        self._connection_tested = False

        self.setTitle("Setup - Twitter")
        self.setSubTitle("Step 1 of 2 - Twitter API Credentials")

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._api_key = QLineEdit()
        self._api_key.setPlaceholderText("Enter your API key")
        form.addRow("API Key:", self._api_key)

        self._api_secret = QLineEdit()
        self._api_secret.setEchoMode(QLineEdit.Password)
        self._api_secret.setPlaceholderText("Enter your API secret")
        form.addRow("API Secret:", self._api_secret)

        self._access_token = QLineEdit()
        self._access_token.setPlaceholderText("Enter your access token")
        form.addRow("Access Token:", self._access_token)

        self._access_secret = QLineEdit()
        self._access_secret.setEchoMode(QLineEdit.Password)
        self._access_secret.setPlaceholderText("Enter your access token secret")
        form.addRow("Access Token Secret:", self._access_secret)

        layout.addLayout(form)
        layout.addSpacing(10)

        btn_row = QHBoxLayout()
        test_btn = QPushButton("Test Connection")
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
                f'<span style="color: #F44336;">\u274C Connection failed: {error}</span>'
            )

    def _save_creds(self):
        key = self._api_key.text().strip()
        secret = self._api_secret.text().strip()
        token = self._access_token.text().strip()
        token_secret = self._access_secret.text().strip()
        if key and secret and token and token_secret:
            self._auth_manager.save_twitter_auth(key, secret, token, token_secret)

    def validatePage(self) -> bool:
        self._save_creds()
        return True


class BlueskySetupPage(QWizardPage):
    """Bluesky account setup."""

    def __init__(self, auth_manager: AuthManager, parent=None):
        super().__init__(parent)
        self._auth_manager = auth_manager

        self.setTitle("Setup - Bluesky")
        self.setSubTitle("Step 2 of 2 - Bluesky Account")

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._identifier = QLineEdit()
        self._identifier.setPlaceholderText("yourname.bsky.social")
        form.addRow("Username (handle):", self._identifier)

        hint = QLabel("Example: yourname.bsky.social")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        form.addRow("", hint)

        self._app_password = QLineEdit()
        self._app_password.setEchoMode(QLineEdit.Password)
        self._app_password.setPlaceholderText("xxxx-xxxx-xxxx-xxxx")
        form.addRow("App Password:", self._app_password)

        pw_hint = QLabel("Format: xxxx-xxxx-xxxx-xxxx")
        pw_hint.setStyleSheet("color: #888; font-size: 11px;")
        form.addRow("", pw_hint)

        layout.addLayout(form)
        layout.addSpacing(10)

        btn_row = QHBoxLayout()
        test_btn = QPushButton("Test Connection")
        test_btn.clicked.connect(self._test_connection)
        btn_row.addWidget(test_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._status_label = QLabel()
        layout.addWidget(self._status_label)
        layout.addStretch()

        # Pre-fill
        existing = self._auth_manager.get_bluesky_auth()
        if existing:
            self._identifier.setText(existing.get('identifier', ''))
            self._app_password.setText(existing.get('app_password', ''))

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
                f'<span style="color: #F44336;">\u274C Connection failed: {error}</span>'
            )

    def _save_creds(self):
        identifier = self._identifier.text().strip()
        password = self._app_password.text().strip()
        if identifier and password:
            self._auth_manager.save_bluesky_auth(identifier, password)

    def validatePage(self) -> bool:
        self._save_creds()
        return True


class SetupWizard(QWizard):
    """First-run setup wizard."""

    def __init__(self, auth_manager: AuthManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GalePost - Setup")
        self.setMinimumSize(550, 450)

        self.addPage(WelcomePage())
        self.addPage(TwitterSetupPage(auth_manager))
        self.addPage(BlueskySetupPage(auth_manager))

        self.setButtonText(QWizard.FinishButton, "Finish")
