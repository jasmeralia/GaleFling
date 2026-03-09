"""Tests for setup wizard WebView login UX."""

from __future__ import annotations

from PyQt6.QtWidgets import QLabel

from src.gui.setup_wizard import WebViewLoginDialog, WebViewPlatformSetupPage


class _DummyAuthManager:
    def get_account(self, _account_id):
        return None

    def add_account(self, _account):
        return


class _FakePlatform:
    def __init__(self, detected: bool):
        self._detected = detected

    def create_webview(self, parent=None):
        return QLabel('fake webview', parent)

    def navigate_to_composer(self):
        return

    def has_valid_session(self):
        return self._detected


def test_webview_login_dialog_detects_without_auto_close(qtbot):
    platform = _FakePlatform(detected=True)
    dialog = WebViewLoginDialog(platform, 'Snapchat')
    qtbot.addWidget(dialog)
    dialog.show()

    dialog._check_login()

    assert dialog.login_detected is True
    assert dialog.result() == 0  # not auto-accepted
    assert 'Login detected' in dialog._status_banner.text()

    dialog.close()


def test_webview_setup_page_detected_does_not_auto_advance(qtbot, monkeypatch):
    page = WebViewPlatformSetupPage(
        _DummyAuthManager(),
        'snapchat',
        'Snapchat',
        'snapchat_1',
    )
    qtbot.addWidget(page)
    page._profile_name.setText('tester')

    monkeypatch.setattr(
        WebViewPlatformSetupPage,
        '_create_platform',
        lambda _self: _FakePlatform(detected=False),
    )

    class _DummyDialog:
        def __init__(self, *_args, **_kwargs):
            self.login_detected = True

        def exec(self):
            return 0

    monkeypatch.setattr('src.gui.setup_wizard.WebViewLoginDialog', _DummyDialog)

    class _DummyWizard:
        def __init__(self):
            self.next_called = False

        def next(self):
            self.next_called = True

    wizard = _DummyWizard()
    monkeypatch.setattr(page, 'wizard', lambda: wizard)

    page._open_login_window()

    assert 'Login detected' in page._status_label.text()
    assert wizard.next_called is False


def test_webview_setup_page_not_detected_uses_delayed_refresh(qtbot, monkeypatch):
    page = WebViewPlatformSetupPage(
        _DummyAuthManager(),
        'snapchat',
        'Snapchat',
        'snapchat_1',
    )
    qtbot.addWidget(page)
    page._profile_name.setText('tester')

    monkeypatch.setattr(
        WebViewPlatformSetupPage,
        '_create_platform',
        lambda _self: _FakePlatform(detected=False),
    )

    class _DummyDialog:
        def __init__(self, *_args, **_kwargs):
            self.login_detected = False

        def exec(self):
            return 0

    monkeypatch.setattr('src.gui.setup_wizard.WebViewLoginDialog', _DummyDialog)

    refresh_calls = []
    monkeypatch.setattr(page, '_update_login_status', lambda: refresh_calls.append(True))
    monkeypatch.setattr('src.gui.setup_wizard.QTimer.singleShot', lambda _ms, fn: fn())

    page._open_login_window()

    assert page._status_label.text() == 'Checking login status...'
    assert refresh_calls == [True]
