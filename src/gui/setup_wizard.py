"""First-run setup wizard for credential configuration."""

from PyQt5.QtGui import QPalette
from PyQt5.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from src.core.auth_manager import AuthManager
from src.platforms.bluesky import BlueskyPlatform
from src.platforms.twitter import TwitterPlatform
from src.utils.theme import resolve_theme_mode, set_windows_dark_title_bar


class WelcomePage(QWizardPage):
    """Welcome page introducing the setup process."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle('Welcome to GaleFling!')
        self.setAutoFillBackground(True)

        layout = QVBoxLayout(self)
        layout.addSpacing(20)

        intro = QLabel(
            "Let's get you set up to post to Twitter and Bluesky!\n\n"
            "We'll need your account credentials for each platform.\n"
            "Don't worry - they're stored securely on your computer.\n\n"
            'This should only take a minute.'
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
        self.setSubTitle('Step 1 of 2 - Twitter API Credentials')

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._username = QLineEdit()
        self._username.setPlaceholderText('Required for posting')
        form.addRow('Username:', self._username)

        self._api_key = QLineEdit()
        self._api_key.setPlaceholderText('Enter your API key')
        form.addRow('API Key:', self._api_key)

        self._api_secret = QLineEdit()
        self._api_secret.setEchoMode(QLineEdit.Password)
        self._api_secret.setPlaceholderText('Enter your API secret')
        form.addRow('API Secret:', self._api_secret)

        self._access_token = QLineEdit()
        self._access_token.setPlaceholderText('Enter your access token')
        form.addRow('Access Token:', self._access_token)

        self._access_secret = QLineEdit()
        self._access_secret.setEchoMode(QLineEdit.Password)
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
        self.setSubTitle('Step 2 of 2 - Bluesky Account')

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._identifier = QLineEdit()
        self._identifier.setPlaceholderText('yourname.bsky.social')
        form.addRow('Username (handle):', self._identifier)

        hint = QLabel('Example: yourname.bsky.social')
        muted = self.palette().color(QPalette.Disabled, QPalette.Text).name()
        hint.setStyleSheet(f'color: {muted}; font-size: 11px;')
        form.addRow('', hint)

        self._app_password = QLineEdit()
        self._app_password.setEchoMode(QLineEdit.Password)
        self._app_password.setPlaceholderText('xxxx-xxxx-xxxx-xxxx')
        form.addRow('App Password:', self._app_password)

        pw_hint = QLabel('Format: xxxx-xxxx-xxxx-xxxx')
        pw_hint.setStyleSheet(f'color: {muted}; font-size: 11px;')
        form.addRow('', pw_hint)

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
                f'<span style="color: #F44336;">\u274c Connection failed: {error}</span>'
            )

    def _save_creds(self):
        identifier = self._identifier.text().strip()
        password = self._app_password.text().strip()
        if identifier and password:
            self._auth_manager.save_bluesky_auth(identifier, password)

    def validatePage(self) -> bool:  # noqa: N802
        self._save_creds()
        return True


class SetupWizard(QWizard):
    """First-run setup wizard."""

    def __init__(self, auth_manager: AuthManager, theme_mode: str = 'system', parent=None):
        super().__init__(parent)
        self.setWindowTitle('GaleFling - Setup')
        self.setMinimumSize(550, 450)
        self._theme_mode = theme_mode
        self._wizard_palette = None
        self._window_bg = None
        self._window_text = None
        from typing import cast

        app = cast(QApplication | None, QApplication.instance())
        if app is not None:
            self.setStyle(app.style())
            self.setPalette(app.palette())
            self._wizard_palette = app.palette()
            window_bg = self._wizard_palette.color(QPalette.Window).name()
            window_text = self._wizard_palette.color(QPalette.WindowText).name()
            base_bg = self._wizard_palette.color(QPalette.Base).name()
            base_text = self._wizard_palette.color(QPalette.Text).name()
            resolved = resolve_theme_mode(self._theme_mode)
            header_bg = '#3c3c3c' if resolved == 'dark' else window_bg
            header_text = '#f0f0f0' if resolved == 'dark' else window_text
            self._window_bg = window_bg
            self._window_text = window_text
            self.setStyleSheet(
                'QWizard QWizardPage#qt_wizard_page '
                'QLabel[objectName="qt_wizard_h1_label"], '
                'QWizard QWizardPage#qt_wizard_page '
                'QLabel[objectName="qt_wizard_h2_label"] {'
                f'  color: {header_text};'
                '}'
                'QWizard QWidget#qt_wizard_header, '
                'QWizard QWidget#qt_wizard_title, '
                'QWizard QFrame#qt_wizard_header, '
                'QWizard QFrame#qt_wizard_title {'
                f'  background-color: {header_bg};'
                f'  color: {header_text};'
                '}'
                'QWizard QFrame#qt_wizard_button_box, '
                'QWizard QDialogButtonBox {'
                f'  background-color: {header_bg};'
                f'  color: {header_text};'
                '}'
                'QWizard, QWizardPage, QWidget {'
                f'  background-color: {window_bg};'
                f'  color: {window_text};'
                '}'
                'QLabel {'
                f'  color: {window_text};'
                '}'
                'QWizard QDialogButtonBox, QWizard QFrame {'
                f'  background-color: {window_bg};'
                '}'
                'QWizard QPushButton {'
                f'  background-color: {base_bg};'
                f'  color: {base_text};'
                '}'
                'QLineEdit {'
                f'  background-color: {base_bg};'
                f'  color: {base_text};'
                '}'
                'QGroupBox {'
                f'  color: {window_text};'
                '}'
            )
            self.setWizardStyle(QWizard.ModernStyle)
            self.setAutoFillBackground(True)
            set_windows_dark_title_bar(self, resolved == 'dark')

        self.addPage(WelcomePage())
        self.addPage(TwitterSetupPage(auth_manager))
        self.addPage(BlueskySetupPage(auth_manager))

        self.setButtonText(QWizard.FinishButton, 'Finish')

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        if not self._wizard_palette or not self._window_bg or not self._window_text:
            return

        # Force theme on Qt wizard chrome (header + button row) after widgets exist.
        resolved = resolve_theme_mode(self._theme_mode)
        header_bg = '#3c3c3c' if resolved == 'dark' else self._window_bg
        header_text = '#f0f0f0' if resolved == 'dark' else self._window_text
        for widget in self.findChildren(QWidget):
            name = widget.objectName()
            if name.startswith('qt_wizard') or isinstance(widget, QDialogButtonBox):
                widget.setAutoFillBackground(True)
                widget.setPalette(self._wizard_palette)
                widget.setStyleSheet(f'background-color: {header_bg}; color: {header_text};')

        for label_name in (
            'qt_wizard_h1_label',
            'qt_wizard_h2_label',
            'qt_wizard_title_label',
            'qt_wizard_subtitle_label',
        ):
            label = self.findChild(QLabel, label_name)
            if label is None:
                continue
            label.setStyleSheet(f'color: {header_text};')
