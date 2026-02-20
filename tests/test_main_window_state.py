from src.gui.main_window import MainWindow


class DummyAuthManager:
    def __init__(self, twitter: bool, bluesky: bool, bluesky_alt: bool = False):
        self._twitter = twitter
        self._bluesky = bluesky
        self._bluesky_alt = bluesky_alt

    def has_twitter_auth(self) -> bool:
        return self._twitter

    def has_bluesky_auth(self) -> bool:
        return self._bluesky

    def has_bluesky_auth_alt(self) -> bool:
        return self._bluesky_alt

    def get_twitter_auth(self):
        return {'api_key': 'x', 'username': 'jasmeralia'} if self._twitter else None

    def get_bluesky_auth(self):
        return {'identifier': 'jasmeralia.bsky.social'} if self._bluesky else None

    def get_bluesky_auth_alt(self):
        return {'identifier': 'alt.bsky.social'} if self._bluesky_alt else None


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
    assert window._platform_selector.get_platform_label('bluesky_alt') == 'Bluesky'
    assert not window._post_btn.isEnabled()
    assert not window._test_btn.isEnabled()
    assert not window._composer._choose_btn.isEnabled()


def test_main_window_missing_usernames_disables_platforms(qtbot):
    class UsernameMissingAuth(DummyAuthManager):
        def get_twitter_auth(self):
            return {'api_key': 'x', 'username': ''} if self._twitter else None

        def get_bluesky_auth(self):
            return {'identifier': ''} if self._bluesky else None

        def get_bluesky_auth_alt(self):
            return {'identifier': ''} if self._bluesky_alt else None

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

        def __init__(self, image_path, platforms, _parent=None, existing_paths=None):
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

    assert calls[-1] == ['twitter', 'bluesky']


def test_resubmit_does_not_regenerate_preview_when_cached(qtbot, tmp_path, monkeypatch):
    calls = []

    def fake_preview(_image_path, platforms):
        calls.append(list(platforms))

    class DummyWorker:
        def __init__(self, *_args, **_kwargs):
            class _Signal:
                def connect(self, *_a, **_k):
                    return

            self.finished = _Signal()

        def start(self):
            return

    monkeypatch.setattr('src.gui.main_window.PostWorker', DummyWorker)

    window = DummyMainWindow(DummyConfig(selected=['twitter']), DummyAuthManager(True, False))
    qtbot.addWidget(window)

    image_path = tmp_path / 'image.png'
    image_path.write_bytes(b'fake')
    processed_path = tmp_path / 'processed.png'
    processed_path.write_bytes(b'processed')

    window._show_image_preview = fake_preview
    window._composer.set_image_path(image_path)
    window._processed_images = {'twitter': processed_path}
    window._composer.set_text('hello')

    calls.clear()
    window._do_post()

    assert calls == []


def test_auto_save_draft_persists_processed_images(qtbot, tmp_path, monkeypatch):
    window = DummyMainWindow(DummyConfig(selected=['twitter']), DummyAuthManager(True, False))
    qtbot.addWidget(window)

    image_path = tmp_path / 'image.png'
    image_path.write_bytes(b'fake')
    processed_path = tmp_path / 'processed.png'
    processed_path.write_bytes(b'processed')

    window._show_image_preview = lambda *_args, **_kwargs: None
    window._composer.set_text('hello')
    window._composer.set_image_path(image_path)
    window._processed_images = {'twitter': processed_path}

    monkeypatch.setattr('src.gui.main_window.get_drafts_dir', lambda: tmp_path)

    window._auto_save_draft()

    draft_path = tmp_path / 'current_draft.json'
    data = draft_path.read_text()
    assert 'processed_images' in data
    assert 'processed.png' in data
    assert 'enabled_platforms' in data


def test_auto_save_shows_status_message(qtbot, tmp_path, monkeypatch):
    window = DummyMainWindow(DummyConfig(selected=['twitter']), DummyAuthManager(True, False))
    qtbot.addWidget(window)
    window._composer.set_text('hello')

    monkeypatch.setattr('src.gui.main_window.get_drafts_dir', lambda: tmp_path)

    window._auto_save_draft()

    assert 'Draft auto-saved' in window.statusBar().currentMessage()


def test_successful_post_clears_draft_and_processed_images(qtbot, tmp_path, monkeypatch):
    class DummyDialog:
        def __init__(self, *_args, **_kwargs):
            self.send_logs_requested = False

        def exec_(self):
            return 0

    monkeypatch.setattr('src.gui.main_window.ResultsDialog', DummyDialog)
    monkeypatch.setattr('src.gui.main_window.get_drafts_dir', lambda: tmp_path)

    window = DummyMainWindow(DummyConfig(selected=['twitter']), DummyAuthManager(True, False))
    qtbot.addWidget(window)

    image_path = tmp_path / 'image.png'
    image_path.write_bytes(b'fake')
    processed_path = tmp_path / 'processed.png'
    processed_path.write_bytes(b'processed')
    window._processed_images = {'twitter': processed_path}

    window._show_image_preview = lambda *_args, **_kwargs: None
    window._composer.set_text('hello')
    window._composer.set_image_path(image_path)

    draft_path = tmp_path / 'current_draft.json'
    draft_path.write_text('{"text": "hello"}')

    from src.utils.constants import PostResult

    results = [PostResult(success=True, platform='Twitter')]
    window._on_post_finished(results)

    assert window._composer.get_text() == ''
    assert window._composer.get_image_path() is None
    assert not processed_path.exists()
    assert not draft_path.exists()


def test_missing_processed_platforms_dedupes_bluesky(qtbot):
    window = DummyMainWindow(
        DummyConfig(selected=['bluesky', 'bluesky_alt']),
        DummyAuthManager(False, True, True),
    )
    qtbot.addWidget(window)

    missing = window._get_missing_processed_platforms(['bluesky', 'bluesky_alt'])

    assert missing == ['bluesky']


def test_test_connections_message_includes_usernames(qtbot, monkeypatch):
    class DummyPlatform:
        def __init__(self, success, error=None):
            self._success = success
            self._error = error

        def test_connection(self):
            return self._success, self._error

    window = DummyMainWindow(
        DummyConfig(selected=['twitter', 'bluesky', 'bluesky_alt']),
        DummyAuthManager(True, True, True),
    )
    qtbot.addWidget(window)

    window._platforms = {
        'twitter': DummyPlatform(False, 'TW-AUTH-EXPIRED'),
        'bluesky': DummyPlatform(True),
        'bluesky_alt': DummyPlatform(True),
    }

    captured = {}

    def fake_info(_parent, _title, message):
        captured['message'] = message

    monkeypatch.setattr('src.gui.main_window.QMessageBox.information', fake_info)

    window._test_connections()

    assert '\u2714\ufe0f Bluesky (jasmeralia) connected.' in captured['message']
    assert '\u2714\ufe0f Bluesky (alt) connected.' in captured['message']
    assert (
        '\u274c\ufe0f Twitter (jasmeralia) failed to connect: TW-AUTH-EXPIRED'
        in captured['message']
    )


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
