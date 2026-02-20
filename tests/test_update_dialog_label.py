from types import SimpleNamespace

import src.gui.main_window as main_window
from src.gui.main_window import MainWindow


class DummyAuthManager:
    def has_twitter_auth(self):
        return True

    def has_bluesky_auth(self):
        return True

    def has_bluesky_auth_alt(self):
        return False

    def get_twitter_auth(self):
        return {'api_key': 'x', 'username': 'user'}

    def get_bluesky_auth(self):
        return {'identifier': 'user.bsky.social'}

    def get_bluesky_auth_alt(self):
        return None


class DummyConfig:
    def __init__(self):
        self.last_selected_platforms = ['twitter', 'bluesky']
        self.last_image_directory = ''
        self.auto_save_draft = False
        self.draft_interval = 30
        self.auto_check_updates = False
        self.allow_prerelease_updates = True
        self.theme_mode = 'system'
        self.window_geometry = {'x': 0, 'y': 0, 'width': 800, 'height': 600}
        self.log_upload_endpoint = 'https://example.invalid'
        self.log_upload_enabled = True
        self.debug_mode = False

    def save(self):
        return

    def set(self, key, value):
        setattr(self, key, value)


class DummyMainWindow(MainWindow):
    def _check_first_run(self):
        return


def test_update_dialog_labels_beta(qtbot, monkeypatch):
    captured = {}

    update = SimpleNamespace(
        latest_version='0.2.99',
        current_version='0.2.0',
        release_name='Beta Release',
        release_notes='Beta notes',
        download_url='',
        download_size=0,
        browser_url='',
        is_prerelease=True,
    )

    monkeypatch.setattr(main_window, 'check_for_updates', lambda *_args, **_kwargs: update)

    class DummyDialog:
        Accepted = 1

        def __init__(self, _parent, **kwargs):
            captured['label'] = kwargs['release_label']

        def exec_(self):
            return 0

    monkeypatch.setattr(main_window, 'UpdateAvailableDialog', DummyDialog)

    window = DummyMainWindow(DummyConfig(), DummyAuthManager())
    qtbot.addWidget(window)

    window._manual_update_check()
    assert captured['label'] == 'beta'


def test_update_dialog_labels_stable(qtbot, monkeypatch):
    captured = {}

    update = SimpleNamespace(
        latest_version='0.2.99',
        current_version='0.2.0',
        release_name='Stable Release',
        release_notes='Stable notes',
        download_url='',
        download_size=0,
        browser_url='',
        is_prerelease=False,
    )

    monkeypatch.setattr(main_window, 'check_for_updates', lambda *_args, **_kwargs: update)

    class DummyDialog:
        Accepted = 1

        def __init__(self, _parent, **kwargs):
            captured['label'] = kwargs['release_label']

        def exec_(self):
            return 0

    monkeypatch.setattr(main_window, 'UpdateAvailableDialog', DummyDialog)

    window = DummyMainWindow(DummyConfig(), DummyAuthManager())
    qtbot.addWidget(window)

    window._manual_update_check()
    assert captured['label'] == 'stable'
