from types import SimpleNamespace

from PyQt5.QtWidgets import QMessageBox

import src.gui.main_window as main_window
from src.gui.main_window import MainWindow


class DummyAuthManager:
    def has_twitter_auth(self):
        return True

    def has_bluesky_auth(self):
        return True

    def get_twitter_auth(self):
        return {'api_key': 'x'}

    def get_bluesky_auth(self):
        return {'identifier': 'x'}


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

    def fake_question(_parent, _title, text, *_args, **_kwargs):
        captured['text'] = text
        return QMessageBox.No

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
    monkeypatch.setattr(QMessageBox, 'question', fake_question)

    window = DummyMainWindow(DummyConfig(), DummyAuthManager())
    qtbot.addWidget(window)

    window._manual_update_check()
    assert '(beta)' in captured['text']


def test_update_dialog_labels_stable(qtbot, monkeypatch):
    captured = {}

    def fake_question(_parent, _title, text, *_args, **_kwargs):
        captured['text'] = text
        return QMessageBox.No

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
    monkeypatch.setattr(QMessageBox, 'question', fake_question)

    window = DummyMainWindow(DummyConfig(), DummyAuthManager())
    qtbot.addWidget(window)

    window._manual_update_check()
    assert '(stable)' in captured['text']
