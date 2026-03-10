from __future__ import annotations

from src.gui.setup_wizard import BlueskySetupPage, InstagramSetupPage, TwitterSetupPage


class _DummyAccount:
    def __init__(self, profile_name: str):
        self.profile_name = profile_name


class _DummyAuthManager:
    def __init__(self):
        self._twitter_app: dict[str, str] = {}
        self._account_creds: dict[str, dict[str, str]] = {}
        self.accounts = []
        self.saved_bluesky: dict[str, str] | None = None
        self.saved_bluesky_alt: dict[str, str] | None = None

    def get_twitter_app_credentials(self):
        return self._twitter_app or None

    def get_twitter_auth(self):
        return None

    def save_twitter_app_credentials(self, api_key: str, api_secret: str):
        self._twitter_app = {'api_key': api_key, 'api_secret': api_secret}

    def get_account(self, account_id):
        if account_id in {a.account_id for a in self.accounts}:
            return _DummyAccount(
                next(a.profile_name for a in self.accounts if a.account_id == account_id)
            )
        return None

    def get_account_credentials(self, account_id):
        return self._account_creds.get(account_id)

    def save_account_credentials(self, account_id, creds):
        self._account_creds[account_id] = dict(creds)

    def add_account(self, account):
        self.accounts.append(account)

    def get_bluesky_auth(self):
        return self.saved_bluesky

    def get_bluesky_auth_alt(self):
        return self.saved_bluesky_alt

    def save_bluesky_auth(self, identifier, app_password):
        self.saved_bluesky = {'identifier': identifier, 'app_password': app_password}

    def save_bluesky_auth_alt(self, identifier, app_password):
        self.saved_bluesky_alt = {'identifier': identifier, 'app_password': app_password}


def test_twitter_start_pin_flow_missing_credentials_shows_warning(qtbot, monkeypatch):
    auth = _DummyAuthManager()
    page = TwitterSetupPage(auth)
    qtbot.addWidget(page)

    warnings = []
    monkeypatch.setattr(
        'src.gui.setup_wizard.QMessageBox.warning',
        lambda *_args: warnings.append(_args[2]),
    )

    page._start_pin_flow('twitter_1')

    assert warnings == ['Enter your Twitter API key and secret before starting PIN flow.']


def test_twitter_complete_pin_flow_saves_tokens_and_account(qtbot, monkeypatch):
    auth = _DummyAuthManager()
    page = TwitterSetupPage(auth)
    qtbot.addWidget(page)

    page._api_key.setText('api-key')
    page._api_secret.setText('api-secret')
    widgets = page._twitter_accounts['twitter_1']
    widgets['username'].setText('jasmeralia')
    widgets['pin'].setText('123456')
    page._pin_handlers['twitter_1'] = object()

    monkeypatch.setattr(
        'src.gui.setup_wizard.TwitterPlatform.complete_pin_flow',
        lambda _handler, _pin: ('token', 'secret'),
    )

    page._complete_pin_flow('twitter_1')

    assert auth._twitter_app == {'api_key': 'api-key', 'api_secret': 'api-secret'}
    assert auth.get_account_credentials('twitter_1') == {
        'access_token': 'token',
        'access_token_secret': 'secret',
    }
    assert auth.accounts[-1].account_id == 'twitter_1'
    assert 'Authorized' in widgets['status'].text()


def test_bluesky_validate_unique_accounts_rejects_duplicate(qtbot, monkeypatch):
    auth = _DummyAuthManager()
    page = BlueskySetupPage(auth)
    qtbot.addWidget(page)

    page._identifier.setText('same.bsky.social')
    page._app_password.setText('abcd-1234-abcd-1234')
    page._identifier_alt.setText('same.bsky.social')
    page._app_password_alt.setText('other-1234-abcd-1234')

    warnings = []
    monkeypatch.setattr(
        'src.gui.setup_wizard.QMessageBox.warning',
        lambda *_args: warnings.append(_args[2]),
    )

    assert page._validate_unique_accounts() is False
    assert warnings and 'Bluesky accounts must be different.' in warnings[0]


def test_bluesky_validate_page_saves_both_accounts(qtbot):
    auth = _DummyAuthManager()
    page = BlueskySetupPage(auth)
    qtbot.addWidget(page)

    page._identifier.setText('one.bsky.social')
    page._app_password.setText('one-1111-one-1111')
    page._identifier_alt.setText('two.bsky.social')
    page._app_password_alt.setText('two-2222-two-2222')

    assert page.validatePage() is True

    assert auth.saved_bluesky == {
        'identifier': 'one.bsky.social',
        'app_password': 'one-1111-one-1111',
    }
    assert auth.saved_bluesky_alt == {
        'identifier': 'two.bsky.social',
        'app_password': 'two-2222-two-2222',
    }
    assert {a.account_id for a in auth.accounts} == {'bluesky_1', 'bluesky_alt'}


def test_instagram_validate_page_saves_credentials_and_account(qtbot):
    auth = _DummyAuthManager()
    page = InstagramSetupPage(auth)
    qtbot.addWidget(page)

    page._profile_name.setText('jasmeralia')
    page._access_token.setText('ig-token')
    page._ig_user_id.setText('17841400000')
    page._page_id.setText('100000000000')

    assert page.validatePage() is True

    assert auth.get_account_credentials('instagram_1') == {
        'access_token': 'ig-token',
        'ig_user_id': '17841400000',
        'page_id': '100000000000',
        'profile_name': 'jasmeralia',
    }
    assert auth.accounts[-1].account_id == 'instagram_1'
