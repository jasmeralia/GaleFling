"""Tests for Settings > Reset Configuration menu action."""

from PyQt6.QtWidgets import QMessageBox

import src.gui.main_window as _main_window_module
from src.gui.main_window import MainWindow
from src.utils.constants import AccountConfig

# ── Minimal stubs ────────────────────────────────────────────────────────────


class _AuthStub:
    """Minimal auth manager stub that tracks clear_all_credentials calls."""

    def __init__(self):
        self._cleared = False
        self._accounts: list[AccountConfig] = [
            AccountConfig(platform_id='twitter', account_id='twitter_1', profile_name='user')
        ]

    def get_accounts(self):
        return list(self._accounts)

    def get_account(self, account_id):
        for a in self._accounts:
            if a.account_id == account_id:
                return a
        return None

    def get_accounts_for_platform(self, platform_id):
        return [a for a in self._accounts if a.platform_id == platform_id]

    def get_account_credentials(self, account_id):
        return None

    def has_twitter_auth(self):
        return True

    def has_bluesky_auth(self):
        return False

    def has_bluesky_auth_alt(self):
        return False

    def get_twitter_auth(self):
        return {'api_key': 'k', 'username': 'user'}

    def get_bluesky_auth(self):
        return None

    def get_bluesky_auth_alt(self):
        return None

    def get_twitter_app_credentials(self):
        return None

    def clear_all_credentials(self):
        self._cleared = True
        self._accounts = []


class _ConfigStub:
    def __init__(self):
        self.theme_mode = 'system'
        self.last_selected_platforms = ['twitter']
        self.last_image_directory = ''
        self.auto_save_draft = False
        self.draft_interval = 30
        self.auto_check_updates = False
        self.allow_prerelease_updates = False
        self.window_geometry = {'x': 0, 'y': 0, 'width': 800, 'height': 600}
        self.snapchat_landscape_mode = 'crop'
        self.snapchat_multi_image_mode = 'first'
        self.preview_worker_count = 2
        self.log_upload_endpoint = 'https://example.invalid'
        self.log_upload_enabled = True
        self.debug_mode = False
        self._reset_called = False

    def save(self):
        pass

    def set(self, key, value):
        setattr(self, key, value)

    def reset_to_defaults(self):
        self._reset_called = True


class _DummyWindow(MainWindow):
    def _check_first_run(self):
        pass


def _find_menu_action(window, menu_text, action_text):
    for menu_action in window.menuBar().actions():
        if menu_action.text() != menu_text:
            continue
        menu = menu_action.menu()
        if menu is None:
            continue
        for action in menu.actions():
            if action.text() == action_text:
                return action
    raise AssertionError(f'Action not found: {menu_text} > {action_text}')


# ── Tests ────────────────────────────────────────────────────────────────────


def test_reset_configuration_menu_item_exists(qtbot):
    window = _DummyWindow(_ConfigStub(), _AuthStub())
    qtbot.addWidget(window)
    # Should not raise
    action = _find_menu_action(window, 'Settings', 'Reset Configuration...')
    assert action is not None


def test_reset_configuration_logs_selection(qtbot, monkeypatch):
    logged = []

    class _Logger:
        def info(self, msg):
            logged.append(msg)

        def warning(self, msg):
            pass

        def debug(self, msg):
            pass

    monkeypatch.setattr('src.gui.main_window.get_logger', lambda: _Logger())
    monkeypatch.setattr(
        MainWindow,
        '_reset_configuration',
        lambda self: logged.append('User selected Settings > Reset Configuration...'),
    )

    window = _DummyWindow(_ConfigStub(), _AuthStub())
    qtbot.addWidget(window)

    action = _find_menu_action(window, 'Settings', 'Reset Configuration...')
    action.trigger()

    assert 'User selected Settings > Reset Configuration...' in logged


def test_reset_configuration_cancelled_does_nothing(qtbot, monkeypatch, tmp_path):
    auth = _AuthStub()
    config = _ConfigStub()

    # Simulate user clicking "No"
    monkeypatch.setattr(
        _main_window_module.QMessageBox,
        'exec',
        lambda self: QMessageBox.StandardButton.No,
    )
    monkeypatch.setattr('src.gui.main_window.get_app_data_dir', lambda: tmp_path)

    window = _DummyWindow(config, auth)
    qtbot.addWidget(window)

    window._reset_configuration()

    assert auth._cleared is False
    assert config._reset_called is False


def test_reset_configuration_confirmed_clears_credentials_and_config(qtbot, monkeypatch, tmp_path):
    auth = _AuthStub()
    config = _ConfigStub()

    # Simulate user clicking "Yes"
    monkeypatch.setattr(
        _main_window_module.QMessageBox,
        'exec',
        lambda self: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr('src.gui.main_window.get_app_data_dir', lambda: tmp_path)

    window = _DummyWindow(config, auth)
    qtbot.addWidget(window)

    window._reset_configuration()

    assert auth._cleared is True
    assert config._reset_called is True


def test_reset_configuration_destroys_webview_profiles(qtbot, monkeypatch, tmp_path):
    auth = _AuthStub()
    config = _ConfigStub()

    # Create fake webprofile directories
    webprofiles_dir = tmp_path / 'webprofiles'
    (webprofiles_dir / 'snapchat_1').mkdir(parents=True)
    (webprofiles_dir / 'onlyfans_1').mkdir(parents=True)
    (webprofiles_dir / 'snapchat_1' / 'Cookies').write_bytes(b'fake')

    evicted = []
    monkeypatch.setattr(
        _main_window_module.BaseWebViewPlatform,
        '_evict_profile',
        classmethod(lambda cls, account_id: evicted.append(account_id)),
    )
    monkeypatch.setattr(
        _main_window_module.QMessageBox,
        'exec',
        lambda self: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr('src.gui.main_window.get_app_data_dir', lambda: tmp_path)

    window = _DummyWindow(config, auth)
    qtbot.addWidget(window)

    window._reset_configuration()

    assert not (webprofiles_dir / 'snapchat_1').exists()
    assert not (webprofiles_dir / 'onlyfans_1').exists()
    assert set(evicted) == {'snapchat_1', 'onlyfans_1'}


def test_reset_configuration_works_without_webprofiles_dir(qtbot, monkeypatch, tmp_path):
    """Reset should not error when no webprofiles directory exists yet."""
    auth = _AuthStub()
    config = _ConfigStub()

    monkeypatch.setattr(
        _main_window_module.QMessageBox,
        'exec',
        lambda self: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr('src.gui.main_window.get_app_data_dir', lambda: tmp_path)

    window = _DummyWindow(config, auth)
    qtbot.addWidget(window)

    # Should not raise
    window._reset_configuration()

    assert auth._cleared is True
    assert config._reset_called is True
