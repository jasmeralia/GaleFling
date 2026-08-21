#!/usr/bin/env python3
"""Generate README screenshots using entirely fake, offscreen-rendered data.

Runs GaleFling's real GUI code against a throwaway AuthManager/ConfigManager
pointed at an isolated temp HOME, with fabricated account handles (no real
credentials or usernames anywhere), and grabs PNGs of the widgets that
README.md embeds under docs/images/.

Usage:
    .venv/bin/python tools/screenshots/generate_readme_screenshots.py

Re-run this after UI changes to regenerate the README screenshot set.
"""

# The HOME/QT_QPA_PLATFORM env vars below must be set before importing
# anything that touches app config paths or Qt.
# ruff: noqa: E402

import os
import sys
import tempfile
from pathlib import Path

# Isolate all app state (config, accounts, logs) under a scratch HOME so this
# script never reads or writes real GaleFling config/credentials.
_SCRATCH_HOME = tempfile.mkdtemp(prefix='galefling-screenshot-home-')
os.environ['HOME'] = _SCRATCH_HOME
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PIL import Image
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

from src.core.auth_manager import AuthManager
from src.core.config_manager import ConfigManager
from src.gui.main_window import MainWindow
from src.gui.results_dialog import ResultsDialog
from src.gui.settings_dialog import SettingsDialog
from src.gui.setup_wizard import SetupWizard
from src.utils.constants import AccountConfig, PostResult
from src.utils.theme import apply_theme

OUT_DIR = Path(__file__).resolve().parent.parent.parent / 'docs' / 'images'

# One account per active service, plus a second Twitter account to show off
# multi-account support -- all fake, no resemblance to real handles.
FAKE_ACCOUNTS = [
    AccountConfig(
        platform_id='bluesky', account_id='bluesky_1', profile_name='samplecreator.bsky.social'
    ),
    AccountConfig(
        platform_id='meta_facebook_page',
        account_id='meta_facebook_page_1',
        profile_name='Sample Creator Page',
    ),
    AccountConfig(
        platform_id='meta_instagram', account_id='meta_instagram_1', profile_name='samplecreator'
    ),
    AccountConfig(
        platform_id='meta_threads', account_id='meta_threads_1', profile_name='samplecreator'
    ),
    AccountConfig(platform_id='twitter', account_id='twitter_1', profile_name='samplecreator'),
    AccountConfig(platform_id='twitter', account_id='twitter_2', profile_name='samplecreator_sfw'),
    AccountConfig(platform_id='fetlife', account_id='fetlife_1', profile_name='SampleCreator'),
]

# Accounts with saved (fake) credentials show a "Ready" status pill; the rest
# show "Unavailable" -- a mix makes for a more representative screenshot than
# an all-or-nothing account list. FetLife is WebView/session-based rather
# than credential-based, so it's left "Unavailable" here regardless.
FAKE_READY_ACCOUNT_IDS = {'bluesky_1', 'meta_instagram_1', 'twitter_1'}


def _qpixmap_to_pil(pixmap) -> Image.Image:
    qimage = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = qimage.width(), qimage.height()
    buf = qimage.bits().asstring(qimage.sizeInBytes())
    return Image.frombuffer('RGBA', (width, height), buf, 'raw', 'RGBA', 0, 1).copy()


def _grab(widget) -> Image.Image:
    QApplication.processEvents()
    return _qpixmap_to_pil(widget.grab())


def _save(image: Image.Image, name: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / name
    image.convert('RGB').save(path)
    print(f'Wrote {path} ({image.width}x{image.height})')


def build_auth_manager(*, with_ready_accounts: bool = False) -> AuthManager:
    auth_manager = AuthManager()
    for account in FAKE_ACCOUNTS:
        auth_manager.add_account(account)
        if with_ready_accounts and account.account_id in FAKE_READY_ACCOUNT_IDS:
            auth_manager.save_account_credentials(account.account_id, {'access_token': 'fake'})
    return auth_manager


def capture_main_window(app: QApplication) -> None:
    config = ConfigManager()
    auth_manager = build_auth_manager(with_ready_accounts=True)

    window = MainWindow(config, auth_manager)
    apply_theme(app, window)
    window.resize(960, 1320)
    window.show()
    QApplication.processEvents()

    composer = window._composer
    composer._text_edit.setPlainText('Testing out the new dark mode UI ✨')
    composer._emoji_button.click()
    QApplication.processEvents()

    window_image = _grab(window)
    popup = composer._emoji_button._popup
    if popup is not None:
        popup_image = _grab(popup)
        window_origin = window.mapToGlobal(window.rect().topLeft())
        popup_origin = popup.mapToGlobal(popup.rect().topLeft())
        paste_at = (popup_origin.x() - window_origin.x(), popup_origin.y() - window_origin.y())
        window_image.paste(popup_image, paste_at)
        popup.close()

    _save(window_image, 'main-window.png')
    window.close()


def capture_settings_dialog(app: QApplication) -> None:
    config = ConfigManager()
    auth_manager = build_auth_manager()
    auth_manager.save_twitter_app_credentials('sample-api-key', 'sample-api-secret')

    dialog = SettingsDialog(config, auth_manager)
    apply_theme(app, dialog)
    dialog.show()
    QApplication.processEvents()

    _select_settings_nav_item(dialog, 'Twitter')
    QApplication.processEvents()

    _save(_grab(dialog), 'settings-dialog.png')
    dialog.close()


def _select_settings_nav_item(dialog, label: str) -> None:
    from PyQt6.QtWidgets import QListWidget

    for list_widget in dialog.findChildren(QListWidget):
        for row in range(list_widget.count()):
            item = list_widget.item(row)
            if item.text().strip() == label:
                list_widget.setCurrentItem(item)
                return


def capture_setup_wizard(app: QApplication) -> None:
    auth_manager = AuthManager()  # deliberately empty -- this is the fresh-setup flow

    wizard = SetupWizard(auth_manager)
    apply_theme(app, wizard)
    wizard.resize(640, 780)
    wizard.show()
    QApplication.processEvents()

    bluesky_page_id = next(
        page_id
        for page_id in wizard.pageIds()
        if type(wizard.page(page_id)).__name__ == 'BlueskySetupPage'
    )
    wizard.setCurrentId(bluesky_page_id)
    page = wizard.currentPage()
    assert page is not None
    page._identifier.setText('samplecreator.bsky.social')  # type: ignore[attr-defined]
    page._app_password.setText('xxxx-xxxx-xxxx-xxxx')  # type: ignore[attr-defined]
    page.adjustSize()
    wizard.adjustSize()
    wizard.resize(640, 780)
    for _ in range(5):
        QApplication.processEvents()

    _save(_grab(wizard), 'setup-wizard.png')
    wizard.close()


def capture_results_dialog(app: QApplication) -> None:
    results = [
        PostResult(
            success=True,
            platform='Bluesky',
            post_url='https://bsky.app/profile/samplecreator.bsky.social/post/sample123',
            account_id='bluesky_1',
            profile_name='samplecreator.bsky.social',
        ),
        PostResult(
            success=True,
            platform='Twitter',
            post_url='https://twitter.com/samplecreator/status/1234567890',
            account_id='twitter_1',
            profile_name='samplecreator',
        ),
        PostResult(
            success=False,
            platform='FetLife',
            error_message='Session expired -- please reconnect this account in Settings.',
            account_id='fetlife_1',
            profile_name='SampleCreator',
            # Fixed rather than datetime.now() so re-running this script doesn't
            # churn the output PNG's bytes on every regeneration.
            timestamp='2026-01-01T12:00:00',
        ),
    ]
    dialog = ResultsDialog(results)
    apply_theme(app, dialog)
    dialog.show()
    QApplication.processEvents()

    _save(_grab(dialog), 'results-dialog.png')
    dialog.close()


def main() -> None:
    app = QApplication(sys.argv)
    apply_theme(app)

    capture_main_window(app)
    capture_settings_dialog(app)
    capture_setup_wizard(app)
    capture_results_dialog(app)


if __name__ == '__main__':
    main()
