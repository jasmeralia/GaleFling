from PyQt6.QtWidgets import QDialog, QLabel, QMessageBox

from src.gui.main_window import MainWindow
from src.utils.constants import MAX_MEDIA_ATTACHMENTS, AccountConfig


class DummyAuthManager:
    def __init__(
        self,
        twitter: bool,
        bluesky: bool,
        bluesky_alt: bool = False,
        snapchat: bool = False,
    ):
        self._twitter = twitter
        self._bluesky = bluesky
        self._bluesky_alt = bluesky_alt
        self._snapchat = snapchat

    # Phase 1 account-based API
    def get_accounts(self) -> list[AccountConfig]:
        accounts = []
        if self._twitter:
            accounts.append(
                AccountConfig(
                    platform_id='twitter',
                    account_id='twitter_1',
                    profile_name='jasmeralia',
                )
            )
        if self._bluesky:
            accounts.append(
                AccountConfig(
                    platform_id='bluesky',
                    account_id='bluesky_1',
                    profile_name='jasmeralia.bsky.social',
                )
            )
        if self._bluesky_alt:
            accounts.append(
                AccountConfig(
                    platform_id='bluesky',
                    account_id='bluesky_alt',
                    profile_name='alt.bsky.social',
                )
            )
        if self._snapchat:
            accounts.append(
                AccountConfig(
                    platform_id='snapchat',
                    account_id='snapchat_1',
                    profile_name='snap-user',
                )
            )
        return accounts

    def get_account(self, account_id):
        for a in self.get_accounts():
            if a.account_id == account_id:
                return a
        return None

    def get_account_credentials(self, account_id):
        return None

    # Phase 0 backward compat
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

    def get_twitter_app_credentials(self):
        return None

    def get_accounts_for_platform(self, platform_id):
        return [a for a in self.get_accounts() if a.platform_id == platform_id]


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
        self.snapchat_landscape_mode = 'crop'
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


def test_main_window_no_credentials_disables_actions(qtbot):
    window = DummyMainWindow(
        DummyConfig(selected=['twitter_1', 'bluesky_1']), DummyAuthManager(False, False)
    )
    qtbot.addWidget(window)

    assert window._platform_selector.get_enabled() == []
    assert window._platform_selector.get_selected() == []
    assert not window._post_btn.isEnabled()
    assert not window._test_btn.isEnabled()
    assert not window._composer._choose_btn.isEnabled()


def test_menu_action_logging(qtbot, monkeypatch):
    logged = []

    class DummyLogger:
        def info(self, message):
            logged.append(message)

    logger = DummyLogger()
    monkeypatch.setattr('src.gui.main_window.get_logger', lambda: logger)
    monkeypatch.setattr('src.gui.main_window.MainWindow._show_about', lambda _self: None)

    window = DummyMainWindow(DummyConfig(selected=['twitter_1']), DummyAuthManager(True, False))
    qtbot.addWidget(window)

    action = _find_menu_action(window, 'Help', 'About')
    action.trigger()

    assert 'User selected Help > About' in logged


def test_help_open_log_directory_action(qtbot, monkeypatch, tmp_path):
    opened = {}
    logs_dir = tmp_path / 'logs'

    monkeypatch.setattr('src.gui.main_window.get_logs_dir', lambda: logs_dir)
    monkeypatch.setattr(
        'src.gui.main_window.QDesktopServices.openUrl',
        lambda url: opened.setdefault('path', url.toLocalFile()) or True,
    )

    window = DummyMainWindow(DummyConfig(selected=['twitter_1']), DummyAuthManager(True, False))
    qtbot.addWidget(window)

    action = _find_menu_action(window, 'Help', 'Open Log Directory')
    action.trigger()

    assert logs_dir.exists()
    assert opened['path'] == str(logs_dir)


def test_about_dialog_displays_ffmpeg_version(qtbot, monkeypatch):
    captured = {}

    class CaptureDialog(QDialog):
        def exec(self):
            captured['texts'] = [
                label.text() for label in self.findChildren(QLabel) if label.text()
            ]
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr('src.gui.main_window.QDialog', CaptureDialog)
    monkeypatch.setattr('src.gui.main_window.get_ffmpeg_version', lambda: '7.1.1-custom')

    window = DummyMainWindow(DummyConfig(selected=['twitter_1']), DummyAuthManager(True, False))
    qtbot.addWidget(window)
    window._show_about()

    assert any('ffmpeg (7.1.1-custom)' in text for text in captured['texts'])


def test_manual_update_check_no_updates_applies_theme(qtbot, monkeypatch):
    apply_calls = []

    monkeypatch.setattr('src.gui.main_window.check_for_updates', lambda *_a, **_k: None)
    monkeypatch.setattr(
        'src.gui.main_window.apply_theme',
        lambda _app, dialog, mode: apply_calls.append((dialog, mode)),
    )
    monkeypatch.setattr(
        'src.gui.main_window.QMessageBox',
        type(
            'DummyMessageBox',
            (),
            {
                'Icon': QMessageBox.Icon,
                'StandardButton': QMessageBox.StandardButton,
                'Ok': 0,
                'Information': 1,
                'Warning': 2,
                'Question': 3,
                'Yes': 4,
                'No': 5,
                'StandardButtons': int,
                '__init__': lambda *_a, **_k: None,
                'setWindowTitle': lambda *_a, **_k: None,
                'setText': lambda *_a, **_k: None,
                'setIcon': lambda *_a, **_k: None,
                'setStandardButtons': lambda *_a, **_k: None,
                'setDefaultButton': lambda *_a, **_k: None,
                'exec': lambda *_a, **_k: 0,
            },
        ),
    )

    window = DummyMainWindow(DummyConfig(selected=['twitter_1']), DummyAuthManager(True, False))
    qtbot.addWidget(window)

    window._manual_update_check()

    assert any(mode == window._config.theme_mode for _dialog, mode in apply_calls)


def test_startup_update_check_accepts_dialog_without_attribute_error(qtbot, monkeypatch):
    class DummyUpdate:
        latest_version = '1.5.5'
        current_version = '1.5.4'
        is_prerelease = False
        release_name = 'Release 1.5.5'
        release_notes = 'Notes'

    class DummyDialog:
        def __init__(self, *_args, **_kwargs):
            return

        def exec(self):
            return QDialog.DialogCode.Accepted

    called = {}

    monkeypatch.setattr('src.gui.main_window.check_for_updates', lambda *_a, **_k: DummyUpdate())
    monkeypatch.setattr('src.gui.main_window.UpdateAvailableDialog', DummyDialog)
    monkeypatch.setattr(
        'src.gui.main_window.MainWindow._download_update',
        lambda *_a: called.setdefault('download', True),
    )

    config = DummyConfig(selected=['twitter_1'])
    config.auto_check_updates = True
    window = DummyMainWindow(config, DummyAuthManager(True, False))
    qtbot.addWidget(window)

    window.check_for_updates_on_startup()

    assert called.get('download') is True


def test_main_window_missing_usernames_disables_platforms(qtbot):
    # With no accounts returned, nothing is enabled
    window = DummyMainWindow(
        DummyConfig(selected=['twitter_1', 'bluesky_1']), DummyAuthManager(False, False)
    )
    qtbot.addWidget(window)

    assert window._platform_selector.get_enabled() == []
    assert window._platform_selector.get_selected() == []
    assert not window._post_btn.isEnabled()
    assert not window._test_btn.isEnabled()
    assert not window._composer._choose_btn.isEnabled()


def test_media_changes_do_not_auto_open_preview(qtbot, tmp_path, monkeypatch):
    calls = []

    class PreviewDialog:
        Accepted = 1

        def __init__(self, image_path, platforms, _parent=None, existing_paths=None):
            self._image_path = image_path
            self._platforms = list(platforms)
            self.had_errors = False
            calls.append(self._platforms)

        def exec(self):
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
    window = DummyMainWindow(DummyConfig(selected=['twitter_1']), auth)
    qtbot.addWidget(window)

    image_path = tmp_path / 'image.png'
    image_path.write_bytes(b'fake')
    window._composer.set_image_path(image_path)
    assert calls == []

    auth.enable_bluesky()
    window._refresh_platform_state()
    window._platform_selector.set_selected(['twitter_1', 'bluesky_1'])
    assert calls == []


def test_refresh_resorts_accounts_after_profile_update(qtbot):
    class MutableProfileAuth(DummyAuthManager):
        def __init__(self):
            super().__init__(twitter=False, bluesky=True, bluesky_alt=True)
            self._primary_profile = 'zeta.bsky.social'
            self._alt_profile = 'alpha.bsky.social'

        def get_accounts(self) -> list[AccountConfig]:
            return [
                AccountConfig(
                    platform_id='bluesky',
                    account_id='bluesky_1',
                    profile_name=self._primary_profile,
                ),
                AccountConfig(
                    platform_id='bluesky',
                    account_id='bluesky_alt',
                    profile_name=self._alt_profile,
                ),
            ]

    auth = MutableProfileAuth()
    window = DummyMainWindow(
        DummyConfig(selected=['bluesky_1', 'bluesky_alt']),
        auth,
    )
    qtbot.addWidget(window)

    assert list(window._platform_selector._checkboxes.keys()) == ['bluesky_alt', 'bluesky_1']

    auth._primary_profile = 'aardvark.bsky.social'
    window._refresh_platform_state()

    assert list(window._platform_selector._checkboxes.keys()) == ['bluesky_1', 'bluesky_alt']
    assert window._platform_selector.get_selected() == ['bluesky_1', 'bluesky_alt']


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

    window = DummyMainWindow(DummyConfig(selected=['twitter_1']), DummyAuthManager(True, False))
    qtbot.addWidget(window)

    image_path = tmp_path / 'image.png'
    image_path.write_bytes(b'fake')
    processed_path = tmp_path / 'processed.png'
    processed_path.write_bytes(b'processed')

    window._show_media_preview = fake_preview
    window._composer.set_image_path(image_path)
    window._processed_media = {'twitter': [processed_path]}
    window._composer.set_text('hello')

    calls.clear()
    window._do_post()

    assert calls == []


def test_auto_save_draft_persists_processed_images(qtbot, tmp_path, monkeypatch):
    window = DummyMainWindow(DummyConfig(selected=['twitter_1']), DummyAuthManager(True, False))
    qtbot.addWidget(window)

    image_path = tmp_path / 'image.png'
    image_path.write_bytes(b'fake')
    processed_path = tmp_path / 'processed.png'
    processed_path.write_bytes(b'processed')

    window._show_media_preview = lambda *_args, **_kwargs: None
    window._composer.set_text('hello')
    window._composer.set_image_path(image_path)
    window._processed_media = {'twitter': [processed_path]}

    monkeypatch.setattr('src.gui.main_window.get_drafts_dir', lambda: tmp_path)

    window._auto_save_draft()

    draft_path = tmp_path / 'current_draft.json'
    data = draft_path.read_text()
    assert 'processed_media' in data
    assert 'processed.png' in data
    assert 'enabled_platforms' in data


def test_auto_save_shows_status_message(qtbot, tmp_path, monkeypatch):
    window = DummyMainWindow(DummyConfig(selected=['twitter_1']), DummyAuthManager(True, False))
    qtbot.addWidget(window)
    window._composer.set_text('hello')

    monkeypatch.setattr('src.gui.main_window.get_drafts_dir', lambda: tmp_path)

    window._auto_save_draft()

    assert 'Draft auto-saved' in window.statusBar().currentMessage()


def test_successful_post_clears_draft_and_processed_images(qtbot, tmp_path, monkeypatch):
    class DummyDialog:
        def __init__(self, *_args, **_kwargs):
            self.send_logs_requested = False

        def exec(self):
            return 0

    monkeypatch.setattr('src.gui.main_window.ResultsDialog', DummyDialog)
    monkeypatch.setattr('src.gui.main_window.get_drafts_dir', lambda: tmp_path)

    window = DummyMainWindow(DummyConfig(selected=['twitter_1']), DummyAuthManager(True, False))
    qtbot.addWidget(window)

    image_path = tmp_path / 'image.png'
    image_path.write_bytes(b'fake')
    processed_path = tmp_path / 'processed.png'
    processed_path.write_bytes(b'processed')
    window._processed_media = {'twitter': [processed_path]}

    window._show_media_preview = lambda *_args, **_kwargs: None
    window._composer.set_text('hello')
    window._composer.set_image_path(image_path)

    draft_path = tmp_path / 'current_draft.json'
    draft_path.write_text('{"text": "hello"}')

    from src.utils.constants import PostResult

    results = [PostResult(success=True, platform='Twitter')]
    window._on_api_post_finished(results)

    assert window._composer.get_text() == ''
    assert window._composer.get_image_path() is None
    assert not processed_path.exists()
    assert not draft_path.exists()


def test_missing_processed_platforms_dedupes_bluesky(qtbot):
    window = DummyMainWindow(
        DummyConfig(selected=['bluesky_1', 'bluesky_alt']),
        DummyAuthManager(False, True, True),
    )
    qtbot.addWidget(window)

    missing = window._get_missing_processed_platforms(['bluesky_1', 'bluesky_alt'])

    assert missing == ['bluesky']


def test_test_connections_message_includes_usernames(qtbot, monkeypatch):
    class DummyPlatform:
        def __init__(self, success, error=None, name=''):
            self._success = success
            self._error = error
            self._name = name

        def test_connection(self):
            return self._success, self._error

        def get_platform_name(self):
            return self._name

    window = DummyMainWindow(
        DummyConfig(selected=['twitter_1', 'bluesky_1', 'bluesky_alt']),
        DummyAuthManager(True, True, True),
    )
    qtbot.addWidget(window)

    window._platforms = {
        'twitter_1': DummyPlatform(False, 'TW-AUTH-EXPIRED', 'Twitter (jasmeralia)'),
        'bluesky_1': DummyPlatform(True, name='Bluesky (jasmeralia)'),
        'bluesky_alt': DummyPlatform(True, name='Bluesky (alt)'),
    }

    captured = {}

    def fake_message_box(_self, _title, message, *_args, **_kwargs):
        captured['message'] = message
        return 0

    monkeypatch.setattr('src.gui.main_window.MainWindow._show_message_box', fake_message_box)

    window._test_connections()

    assert '\u2714\ufe0f Bluesky (jasmeralia) connected.' in captured['message']
    assert '\u2714\ufe0f Bluesky (alt) connected.' in captured['message']
    assert (
        '\u274c\ufe0f Twitter (jasmeralia) failed to connect: TW-AUTH-EXPIRED'
        in captured['message']
    )


def test_test_connections_disables_failed_platforms(qtbot, monkeypatch):
    class MutableAuthManager(DummyAuthManager):
        def __init__(self):
            super().__init__(True, False)
            self._accounts = [
                AccountConfig(
                    platform_id='twitter',
                    account_id='twitter_1',
                    profile_name='jasmeralia',
                )
            ]

        def get_accounts(self) -> list[AccountConfig]:
            return list(self._accounts)

        def get_account(self, account_id):
            for account in self._accounts:
                if account.account_id == account_id:
                    return account
            return None

        def get_account_credentials(self, account_id):
            if account_id == 'twitter_1':
                return {'access_token': 'token'}
            return None

        def set_account_enabled(self, account_id: str, enabled: bool) -> bool:
            account = self.get_account(account_id)
            if account is None:
                return False
            account.enabled = enabled
            return True

    class DummyPlatform:
        def test_connection(self):
            return False, 'TW-AUTH-EXPIRED'

        def get_platform_name(self):
            return 'Twitter (jasmeralia)'

    auth = MutableAuthManager()
    window = DummyMainWindow(DummyConfig(selected=['twitter_1']), auth)
    qtbot.addWidget(window)
    window._platforms['twitter_1'] = DummyPlatform()

    monkeypatch.setattr('src.gui.main_window.MainWindow._show_message_box', lambda *_a, **_k: 0)

    assert 'twitter_1' in window._platform_selector.get_enabled()
    assert 'twitter_1' in window._platform_selector.get_selected()

    window._test_connections()

    assert auth.get_account('twitter_1').enabled is False
    assert 'twitter_1' not in window._platform_selector.get_enabled()
    assert 'twitter_1' not in window._platform_selector.get_selected()


def test_download_update_applies_theme_to_progress(qtbot, monkeypatch, tmp_path):
    class DummyProgress:
        def __init__(self, *_args, **_kwargs):
            self.exec_called = False

        def setWindowTitle(self, _title):  # noqa: N802
            return

        def setWindowModality(self, _mode):  # noqa: N802
            return

        def setMinimumDuration(self, _value):  # noqa: N802
            return

        def setAutoClose(self, _value):  # noqa: N802
            return

        def setAutoReset(self, _value):  # noqa: N802
            return

        def setValue(self, _value):  # noqa: N802
            return

        def exec(self):
            self.exec_called = True
            return 0

    class DummyWorker:
        def __init__(self, *_args, **_kwargs):
            class _Signal:
                def connect(self, *_a, **_k):
                    return

            self.progress = _Signal()
            self.finished = _Signal()

        def start(self):
            return

    monkeypatch.setattr('src.gui.main_window.QProgressDialog', DummyProgress)
    monkeypatch.setattr('src.gui.main_window.UpdateDownloadWorker', DummyWorker)
    monkeypatch.setattr('pathlib.Path.home', lambda: tmp_path)

    applied = []

    class DummyWindow(DummyMainWindow):
        def _apply_dialog_theme(self, dialog):
            applied.append(dialog)

    window = DummyWindow(DummyConfig(selected=['twitter_1']), DummyAuthManager(True, False))
    qtbot.addWidget(window)

    update = type(
        'Update',
        (),
        {
            'download_url': 'https://example.invalid/app.exe',
            'latest_version': '0.0.0',
            'download_size': 0,
        },
    )()

    window._download_update(update)

    assert applied


def test_show_setup_wizard_logs_failure(qtbot, monkeypatch):
    class DummyLogger:
        def __init__(self):
            self.logged = False

        def exception(self, *_args, **_kwargs):
            self.logged = True

    logger = DummyLogger()
    monkeypatch.setattr('src.gui.main_window.get_logger', lambda: logger)
    monkeypatch.setattr(
        'src.gui.main_window.SetupWizard',
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError('boom')),
    )
    monkeypatch.setattr('src.gui.main_window.MainWindow._show_message_box', lambda *_a, **_k: 0)

    window = DummyMainWindow(DummyConfig(selected=['twitter_1']), DummyAuthManager(True, False))
    qtbot.addWidget(window)

    window._show_setup_wizard_impl()

    assert logger.logged


def test_action_logging_for_post_and_connections(qtbot, monkeypatch, tmp_path):
    logged = []

    class DummyLogger:
        def info(self, message, *args, **kwargs):
            logged.append(message)

        def exception(self, *_args, **_kwargs):
            return

    logger = DummyLogger()
    monkeypatch.setattr('src.gui.main_window.get_logger', lambda: logger)
    monkeypatch.setattr('src.gui.main_window.MainWindow._show_message_box', lambda *_a, **_k: 0)

    window = DummyMainWindow(DummyConfig(selected=['twitter_1']), DummyAuthManager(True, False))
    qtbot.addWidget(window)

    class DummyPlatform:
        def test_connection(self):
            return True, None

        def get_platform_name(self):
            return 'Twitter'

    window._platforms['twitter_1'] = DummyPlatform()
    window._platform_selector.set_selected(['twitter_1'])

    window._test_connections()
    assert 'User clicked Test Connections' in logged

    window._composer.get_text = lambda: ''
    window._do_post()
    assert 'User clicked Post Now' in logged

    window._platform_selector.set_selected([])
    image_path = tmp_path / 'image.png'
    image_path.write_bytes(b'fake')
    window._on_media_changed([image_path])
    assert any('User attached media' in message for message in logged)


def test_format_restriction_allows_convertible_static_webp(qtbot, monkeypatch, tmp_path):
    captured = {}

    window = DummyMainWindow(
        DummyConfig(selected=['twitter_1', 'bluesky_1']),
        DummyAuthManager(True, True),
    )
    qtbot.addWidget(window)

    monkeypatch.setattr(window, '_sync_composer_platform_state', lambda: None)
    monkeypatch.setattr(
        window._platform_selector,
        'set_format_restriction',
        lambda restricted, notice_text='': captured.update(
            {'restricted': set(restricted), 'notice': notice_text}
        ),
    )
    monkeypatch.setattr(window, '_detect_media_format', lambda _path: ('WEBP', False))
    monkeypatch.setattr('src.gui.main_window.is_animated_gif', lambda _path: False)

    media = tmp_path / 'test.webp'
    media.write_bytes(b'fake')
    window._apply_format_restriction([media])

    assert captured['restricted'] == set()


def test_count_restriction_disables_snapchat_for_multiple_images(qtbot, monkeypatch, tmp_path):
    captured = {}

    window = DummyMainWindow(
        DummyConfig(selected=['twitter_1', 'snapchat_1']),
        DummyAuthManager(True, False, snapchat=True),
    )
    qtbot.addWidget(window)

    monkeypatch.setattr(window, '_sync_composer_platform_state', lambda: None)
    monkeypatch.setattr(
        window._platform_selector,
        'set_count_restriction',
        lambda restricted, notice_text='': captured.update(
            {'restricted': set(restricted), 'notice': notice_text}
        ),
    )

    media_1 = tmp_path / 'img1.png'
    media_2 = tmp_path / 'img2.png'
    media_1.write_bytes(b'fake1')
    media_2.write_bytes(b'fake2')
    window._apply_count_restriction([media_1, media_2])

    assert 'snapchat_1' in captured['restricted']


def test_format_restriction_notice_shows_in_composer(qtbot, monkeypatch, tmp_path):
    window = DummyMainWindow(
        DummyConfig(selected=['twitter_1', 'snapchat_1']),
        DummyAuthManager(True, False, snapchat=True),
    )
    qtbot.addWidget(window)

    monkeypatch.setattr(window, '_detect_media_format', lambda _path: ('GIF', False))
    monkeypatch.setattr('src.gui.main_window.is_animated_gif', lambda _path: True)

    media = tmp_path / 'test.gif'
    media.write_bytes(b'fake')
    window._apply_format_restriction([media])

    assert not window._composer._format_restriction_notice.isHidden()
    assert 'Animated GIF' in window._composer._format_restriction_notice.text()


def test_count_restriction_notice_shows_in_composer(qtbot, tmp_path):
    window = DummyMainWindow(
        DummyConfig(selected=['twitter_1', 'snapchat_1']),
        DummyAuthManager(True, False, snapchat=True),
    )
    qtbot.addWidget(window)

    media_1 = tmp_path / 'img1.png'
    media_2 = tmp_path / 'img2.png'
    media_1.write_bytes(b'fake1')
    media_2.write_bytes(b'fake2')
    window._apply_count_restriction([media_1, media_2])

    assert not window._composer._count_restriction_notice.isHidden()
    assert 'attachments' in window._composer._count_restriction_notice.text().lower()


def test_show_message_box_applies_theme(qtbot, monkeypatch):
    apply_calls = []

    monkeypatch.setattr(
        'src.gui.main_window.apply_theme',
        lambda _app, dialog, mode: apply_calls.append((dialog, mode)),
    )
    monkeypatch.setattr(
        'src.gui.main_window.QMessageBox',
        type(
            'DummyMessageBox',
            (),
            {
                'Icon': QMessageBox.Icon,
                'StandardButton': QMessageBox.StandardButton,
                'Ok': 0,
                'Information': 1,
                'Warning': 2,
                'Question': 3,
                'Yes': 4,
                'No': 5,
                'StandardButtons': int,
                '__init__': lambda *_a, **_k: None,
                'setWindowTitle': lambda *_a, **_k: None,
                'setText': lambda *_a, **_k: None,
                'setIcon': lambda *_a, **_k: None,
                'setStandardButtons': lambda *_a, **_k: None,
                'setDefaultButton': lambda *_a, **_k: None,
                'exec': lambda *_a, **_k: 0,
            },
        ),
    )

    window = DummyMainWindow(DummyConfig(selected=['twitter_1']), DummyAuthManager(True, False))
    qtbot.addWidget(window)

    window._show_message_box('Title', 'Body', QMessageBox.Icon.Information)

    assert apply_calls


def test_manual_update_check_accepts_update(qtbot, monkeypatch):
    update = type(
        'Update',
        (),
        {
            'latest_version': '1.0.1',
            'current_version': '1.0.0',
            'release_name': 'Test',
            'release_notes': 'Notes',
            'download_url': 'https://example.invalid/app.exe',
            'download_size': 0,
            'browser_url': '',
            'is_prerelease': False,
        },
    )()

    monkeypatch.setattr('src.gui.main_window.check_for_updates', lambda *_a, **_k: update)

    class DummyDialog:
        Accepted = 1

        def __init__(self, *_a, **_k):
            return

        def exec(self):
            return self.Accepted

    monkeypatch.setattr('src.gui.main_window.UpdateAvailableDialog', DummyDialog)
    called = {}

    def fake_download(_update):
        called['downloaded'] = _update.latest_version

    window = DummyMainWindow(DummyConfig(selected=['twitter_1']), DummyAuthManager(True, False))
    qtbot.addWidget(window)
    window._download_update = fake_download

    window._manual_update_check()

    assert called['downloaded'] == '1.0.1'


def test_show_media_preview_logs_send_on_error(qtbot, monkeypatch, tmp_path):
    class PreviewDialog:
        Accepted = 1

        def __init__(self, *_a, **_k):
            self.had_errors = True

        def exec(self):
            return 0

        def get_processed_paths(self):
            return {}

    monkeypatch.setattr('src.gui.main_window.ImagePreviewDialog', PreviewDialog)
    monkeypatch.setattr(
        'src.gui.main_window.MainWindow._show_message_box',
        lambda *_a, **_k: 16384,  # QMessageBox.Yes
    )
    called = {}

    def fake_send_logs():
        called['sent'] = True

    window = DummyMainWindow(DummyConfig(selected=['twitter_1']), DummyAuthManager(True, False))
    qtbot.addWidget(window)
    window._send_logs = fake_send_logs

    image_path = tmp_path / 'image.png'
    image_path.write_bytes(b'fake')
    window._show_media_preview([image_path], ['twitter'])

    assert called.get('sent') is True


def test_show_media_preview_converts_single_image_for_snapchat(qtbot, monkeypatch, tmp_path):
    calls = []
    converted = tmp_path / 'snapchat_converted.mp4'
    converted.write_bytes(b'mp4')

    class PreviewDialog:
        Accepted = 1

        def __init__(self, image_path, platforms, _parent=None, existing_paths=None):
            self.had_errors = False
            self._platforms = list(platforms)
            self._image_path = image_path
            calls.append(self._platforms)

        def exec(self):
            return self.Accepted

        def get_processed_paths(self):
            output = {}
            for platform in self._platforms:
                if platform == 'snapchat':
                    path = converted
                else:
                    path = self._image_path.with_name(f'processed_{platform}.png')
                    path.write_bytes(b'processed')
                output[platform] = path
            return output

    monkeypatch.setattr('src.gui.main_window.ImagePreviewDialog', PreviewDialog)
    monkeypatch.setattr('src.gui.main_window.is_animated_gif', lambda _path: False)
    monkeypatch.setattr(
        'src.gui.main_window.convert_image_to_video',
        lambda _image_path, _specs: converted,
    )

    window = DummyMainWindow(
        DummyConfig(selected=['twitter_1', 'snapchat_1']),
        DummyAuthManager(True, False, snapchat=True),
    )
    qtbot.addWidget(window)

    image_path = tmp_path / 'image.png'
    image_path.write_bytes(b'fake')
    window._show_media_preview([image_path], ['twitter_1', 'snapchat_1'])

    assert calls == [['twitter', 'snapchat']]
    assert window._processed_media['snapchat'][0] == converted
    assert window._processed_media['twitter'][0].exists()


def test_show_media_preview_missing_first_media_stays_missing(qtbot, monkeypatch, tmp_path):
    class PreviewDialog:
        Accepted = 1
        _calls = 0

        def __init__(self, image_path, _platforms, _parent=None, existing_paths=None):
            self.had_errors = False
            self._image_path = image_path
            self._existing_paths = existing_paths or {}
            self._call_idx = PreviewDialog._calls
            PreviewDialog._calls += 1

        def exec(self):
            return self.Accepted

        def get_processed_paths(self):
            # First media fails to process for twitter; second succeeds.
            if self._call_idx == 0:
                return {'twitter': None}
            processed = self._image_path.with_name(f'processed_{self._image_path.name}')
            processed.write_bytes(b'processed')
            return {'twitter': processed}

    monkeypatch.setattr('src.gui.main_window.ImagePreviewDialog', PreviewDialog)

    window = DummyMainWindow(DummyConfig(selected=['twitter_1']), DummyAuthManager(True, False))
    qtbot.addWidget(window)

    media_1 = tmp_path / 'image1.png'
    media_2 = tmp_path / 'image2.png'
    media_1.write_bytes(b'fake1')
    media_2.write_bytes(b'fake2')

    window._show_media_preview([media_1, media_2], ['twitter_1'])

    # Only one processed media should be cached; first is still missing.
    assert len(window._processed_media['twitter']) == 1
    missing = window._get_missing_processed_platforms(['twitter_1'], expected_count=2)
    assert missing == ['twitter']


def test_show_media_preview_caps_at_max_attachments(qtbot, monkeypatch, tmp_path):
    seen_media = []

    class PreviewDialog:
        Accepted = 1

        def __init__(self, image_path, _platforms, _parent=None, existing_paths=None):
            self.had_errors = False
            seen_media.append(image_path)

        def exec(self):
            return self.Accepted

        def get_processed_paths(self):
            return {}

    monkeypatch.setattr('src.gui.main_window.ImagePreviewDialog', PreviewDialog)

    window = DummyMainWindow(DummyConfig(selected=['twitter_1']), DummyAuthManager(True, False))
    qtbot.addWidget(window)

    media_paths = []
    for i in range(MAX_MEDIA_ATTACHMENTS + 2):
        p = tmp_path / f'image_{i}.png'
        p.write_bytes(b'fake')
        media_paths.append(p)

    window._show_media_preview(media_paths, ['twitter_1'])

    assert len(seen_media) == MAX_MEDIA_ATTACHMENTS


def test_main_window_single_platform_enabled(qtbot):
    window = DummyMainWindow(DummyConfig(selected=['twitter_1']), DummyAuthManager(True, False))
    qtbot.addWidget(window)

    assert window._platform_selector.get_enabled() == ['twitter_1']
    assert window._platform_selector.get_selected() == ['twitter_1']
    assert window._post_btn.isEnabled()
    assert window._test_btn.isEnabled()
    assert window._composer._choose_btn.isEnabled()
    assert window._test_btn.styleSheet() == window._post_btn.styleSheet()
    assert window._platform_selector.get_platform_label('twitter_1') == 'Twitter (jasmeralia)'


def test_main_window_disable_when_unchecked(qtbot):
    window = DummyMainWindow(DummyConfig(selected=[]), DummyAuthManager(True, True))
    qtbot.addWidget(window)

    assert 'twitter_1' in window._platform_selector.get_enabled()
    assert 'bluesky_1' in window._platform_selector.get_enabled()
    assert window._platform_selector.get_selected() == []
    assert not window._post_btn.isEnabled()
    assert not window._test_btn.isEnabled()
    assert not window._composer._choose_btn.isEnabled()


def test_snapchat_landscape_mode_persists_from_composer(qtbot):
    config = DummyConfig(selected=['twitter_1'])
    window = DummyMainWindow(config, DummyAuthManager(True, False))
    qtbot.addWidget(window)

    window._composer.set_snapchat_landscape_mode('rotate')

    assert config.snapchat_landscape_mode == 'rotate'
