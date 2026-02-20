from src.gui.main_window import MainWindow


class DummyAuthManager:
    def __init__(self, twitter: bool, bluesky: bool):
        self._twitter = twitter
        self._bluesky = bluesky

    def has_twitter_auth(self) -> bool:
        return self._twitter

    def has_bluesky_auth(self) -> bool:
        return self._bluesky

    def get_twitter_auth(self):
        return {'api_key': 'x', 'username': 'jasmeralia'} if self._twitter else None

    def get_bluesky_auth(self):
        return {'identifier': 'jasmeralia.bsky.social'} if self._bluesky else None


class DummyConfig:
    def __init__(self, selected=None):
        self.last_selected_platforms = selected or []
        self.last_image_directory = ''
        self.auto_save_draft = False
        self.draft_interval = 30
        self.auto_check_updates = False
        self.allow_prerelease_updates = False
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


def test_main_window_no_credentials_disables_actions(qtbot):
    window = DummyMainWindow(
        DummyConfig(selected=['twitter', 'bluesky']), DummyAuthManager(False, False)
    )
    qtbot.addWidget(window)

    assert window._platform_selector.get_enabled() == []
    assert window._platform_selector.get_selected() == []
    assert window._platform_selector.get_platform_label('twitter') == 'Twitter'
    assert window._platform_selector.get_platform_label('bluesky') == 'Bluesky'
    assert not window._post_btn.isEnabled()
    assert not window._test_btn.isEnabled()
    assert not window._composer._choose_btn.isEnabled()


def test_main_window_missing_usernames_disables_platforms(qtbot):
    class UsernameMissingAuth(DummyAuthManager):
        def get_twitter_auth(self):
            return {'api_key': 'x', 'username': ''} if self._twitter else None

        def get_bluesky_auth(self):
            return {'identifier': ''} if self._bluesky else None

    window = DummyMainWindow(
        DummyConfig(selected=['twitter', 'bluesky']), UsernameMissingAuth(True, True)
    )
    qtbot.addWidget(window)

    assert window._platform_selector.get_enabled() == []
    assert window._platform_selector.get_selected() == []
    assert not window._post_btn.isEnabled()
    assert not window._test_btn.isEnabled()
    assert not window._composer._choose_btn.isEnabled()


def test_image_preview_opens_for_newly_enabled_platform(qtbot, tmp_path, monkeypatch):
    calls = []

    class PreviewDialog:
        Accepted = 1

        def __init__(self, image_path, platforms, _parent=None):
            self._image_path = image_path
            self._platforms = list(platforms)
            self.had_errors = False
            calls.append(self._platforms)

        def exec_(self):
            return self.Accepted

        def get_processed_paths(self):
            return {platform: self._image_path for platform in self._platforms}

    monkeypatch.setattr(
        'src.gui.main_window.ImagePreviewDialog',
        PreviewDialog,
    )

    class ToggleAuth(DummyAuthManager):
        def __init__(self):
            super().__init__(twitter=True, bluesky=False)

        def enable_bluesky(self):
            self._bluesky = True

    auth = ToggleAuth()
    window = DummyMainWindow(DummyConfig(selected=['twitter']), auth)
    qtbot.addWidget(window)

    image_path = tmp_path / 'image.png'
    image_path.write_bytes(b'fake')
    window._composer.set_image_path(image_path)

    assert calls == [['twitter']]

    auth.enable_bluesky()
    window._refresh_platform_state()
    window._platform_selector.set_selected(['twitter', 'bluesky'])

    assert calls[-1] == ['bluesky']


def test_main_window_single_platform_enabled(qtbot):
    window = DummyMainWindow(DummyConfig(selected=['twitter']), DummyAuthManager(True, False))
    qtbot.addWidget(window)

    assert window._platform_selector.get_enabled() == ['twitter']
    assert window._platform_selector.get_selected() == ['twitter']
    assert window._post_btn.isEnabled()
    assert window._test_btn.isEnabled()
    assert window._composer._choose_btn.isEnabled()
    assert window._test_btn.styleSheet() == window._post_btn.styleSheet()
    assert window._platform_selector.get_platform_label('twitter') == 'Twitter (jasmeralia)'


def test_main_window_disable_when_unchecked(qtbot):
    window = DummyMainWindow(DummyConfig(selected=[]), DummyAuthManager(True, True))
    qtbot.addWidget(window)

    assert window._platform_selector.get_enabled() == ['twitter', 'bluesky']
    assert window._platform_selector.get_selected() == []
    assert not window._post_btn.isEnabled()
    assert not window._test_btn.isEnabled()
    assert not window._composer._choose_btn.isEnabled()
