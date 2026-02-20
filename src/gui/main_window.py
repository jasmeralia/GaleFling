"""Main application window."""

import contextlib
import json
import os
from datetime import datetime
from pathlib import Path

import requests
from PyQt5.QtCore import QProcess, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QAction,
    QActionGroup,
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from src.core.auth_manager import AuthManager
from src.core.config_manager import ConfigManager
from src.core.log_uploader import LogUploader
from src.core.logger import get_current_log_path, get_logger, reset_log_file
from src.core.update_checker import check_for_updates
from src.gui.image_preview_tabs import ImagePreviewDialog
from src.gui.log_submit_dialog import LogSubmitDialog
from src.gui.platform_selector import PlatformSelector
from src.gui.post_composer import PostComposer
from src.gui.results_dialog import ResultsDialog
from src.gui.settings_dialog import SettingsDialog
from src.gui.setup_wizard import SetupWizard
from src.gui.update_dialog import UpdateAvailableDialog
from src.platforms.bluesky import BlueskyPlatform
from src.platforms.twitter import TwitterPlatform
from src.utils.constants import APP_NAME, APP_VERSION, PostResult
from src.utils.helpers import get_drafts_dir, get_logs_dir, get_resource_path
from src.utils.theme import apply_theme, resolve_theme_mode


class PostWorker(QThread):
    """Background thread for posting to platforms."""

    finished = pyqtSignal(list)

    def __init__(
        self,
        platforms: dict,
        text: str,
        processed_images: dict[str, Path | None],
        platform_groups: dict[str, str],
    ):
        super().__init__()
        self._platforms = platforms
        self._text = text
        self._processed_images = processed_images
        self._platform_groups = platform_groups

    def run(self):
        results = []
        for name, platform in self._platforms.items():
            group = self._platform_groups.get(name, name)
            image_path = self._processed_images.get(group)
            result = platform.post(self._text, image_path)
            results.append(result)
        self.finished.emit(results)


class UpdateDownloadWorker(QThread):
    """Download update installer in background."""

    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, object, str)

    def __init__(self, url: str, target_path: Path, expected_size: int = 0):
        super().__init__()
        self._url = url
        self._target_path = target_path
        self._expected_size = expected_size

    def run(self):
        logger = get_logger()
        temp_path = self._target_path.with_suffix(self._target_path.suffix + '.part')
        try:
            logger.info(
                'Downloading update installer',
                extra={'url': self._url, 'target_path': str(self._target_path)},
            )
            with requests.get(self._url, stream=True, timeout=30) as response:
                response.raise_for_status()
                total = int(response.headers.get('Content-Length', '0')) or 0
                received = 0
                with open(temp_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=1024 * 256):
                        if not chunk:
                            continue
                        f.write(chunk)
                        received += len(chunk)
                        if total > 0:
                            percent = int((received / total) * 100)
                            self.progress.emit(min(100, percent))
            file_size = temp_path.stat().st_size if temp_path.exists() else 0
            if self._expected_size and file_size != self._expected_size:
                raise ValueError(
                    f'Installer download size mismatch ({file_size} of {self._expected_size} bytes).'
                )
            if file_size < 5 * 1024 * 1024:
                raise ValueError(f'Installer download too small ({file_size} bytes).')
            with open(temp_path, 'rb') as f:
                header = f.read(2)
            if header != b'MZ':
                raise ValueError('Installer download is not a valid Windows executable.')
            temp_path.replace(self._target_path)
            logger.info(
                'Update installer downloaded',
                extra={'target_path': str(self._target_path), 'bytes': file_size},
            )
            self.finished.emit(True, self._target_path, '')
        except Exception as exc:
            logger.exception('Update download failed', extra={'error': str(exc)})
            if temp_path.exists():
                with contextlib.suppress(OSError):
                    temp_path.unlink()
            self.finished.emit(False, None, str(exc))


class MainWindow(QMainWindow):
    """Main application window with composer, platform selection, and posting."""

    def __init__(self, config: ConfigManager, auth_manager: AuthManager):
        super().__init__()
        self._config = config
        self._auth_manager = auth_manager
        self._log_uploader = LogUploader(config)
        self._processed_images: dict[str, Path | None] = {}

        self._platforms = {
            'twitter': TwitterPlatform(auth_manager),
            'bluesky': BlueskyPlatform(auth_manager),
            'bluesky_alt': BlueskyPlatform(auth_manager, account_key='alt'),
        }
        self._platform_groups = {
            'twitter': 'twitter',
            'bluesky': 'bluesky',
            'bluesky_alt': 'bluesky',
        }

        self._init_ui()
        self._restore_geometry()
        self._setup_draft_timer()
        self._check_first_run()
        self._refresh_platform_state()

    def _init_ui(self):
        self.setWindowTitle(f'{APP_NAME} v{APP_VERSION}')

        # Menu bar
        self._create_menu_bar()

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Post composer
        self._composer = PostComposer()
        self._composer.set_last_image_dir(self._config.last_image_directory)
        self._composer.image_changed.connect(self._on_image_changed)
        self._composer.preview_requested.connect(self._on_preview_requested)
        layout.addWidget(self._composer)

        # Platform selector
        self._platform_selector = PlatformSelector()
        self._platform_selector.set_selected(self._config.last_selected_platforms)
        self._platform_selector.selection_changed.connect(self._on_platforms_changed)
        layout.addWidget(self._platform_selector)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        primary_button_style = (
            'QPushButton { background-color: #4CAF50; color: white; '
            'font-weight: bold; font-size: 14px; padding: 8px 24px; '
            'border-radius: 4px; }'
            'QPushButton:hover { background-color: #45a049; }'
            'QPushButton:disabled { background-color: #ccc; color: #888; }'
        )

        self._test_btn = QPushButton('Test Connections')
        self._test_btn.setStyleSheet(primary_button_style)
        self._test_btn.clicked.connect(self._test_connections)
        btn_layout.addWidget(self._test_btn)

        btn_layout.addSpacing(10)

        self._post_btn = QPushButton('Post Now')
        self._post_btn.setStyleSheet(primary_button_style)
        self._post_btn.clicked.connect(self._do_post)
        btn_layout.addWidget(self._post_btn)

        layout.addLayout(btn_layout)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage('Ready')

    def _create_menu_bar(self):
        menu_bar = self.menuBar()

        # File menu
        file_menu = menu_bar.addMenu('File')
        exit_action = QAction('Exit', self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Settings menu
        settings_menu = menu_bar.addMenu('Settings')
        open_settings = QAction('Open Settings...', self)
        open_settings.triggered.connect(self._open_settings)
        settings_menu.addAction(open_settings)
        run_setup = QAction('Run Setup Wizard...', self)
        run_setup.triggered.connect(self._show_setup_wizard)
        settings_menu.addAction(run_setup)

        # View menu
        view_menu = menu_bar.addMenu('View')
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)

        self._system_theme_action = QAction('System Default', self, checkable=True)
        self._system_theme_action.triggered.connect(lambda: self._set_theme_mode('system'))
        theme_group.addAction(self._system_theme_action)
        view_menu.addAction(self._system_theme_action)

        self._light_mode_action = QAction('Light Mode', self, checkable=True)
        self._light_mode_action.triggered.connect(lambda: self._set_theme_mode('light'))
        theme_group.addAction(self._light_mode_action)
        view_menu.addAction(self._light_mode_action)

        self._dark_mode_action = QAction('Dark Mode', self, checkable=True)
        self._dark_mode_action.triggered.connect(lambda: self._set_theme_mode('dark'))
        theme_group.addAction(self._dark_mode_action)
        view_menu.addAction(self._dark_mode_action)

        resolved_theme = resolve_theme_mode(self._config.theme_mode)
        if self._config.theme_mode == 'system':
            self._system_theme_action.setChecked(True)
        elif resolved_theme == 'dark':
            self._dark_mode_action.setChecked(True)
        else:
            self._light_mode_action.setChecked(True)

        # Help menu
        help_menu = menu_bar.addMenu('Help')

        about_action = QAction('About', self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

        check_update = QAction('Check for Updates', self)
        check_update.triggered.connect(self._manual_update_check)
        help_menu.addAction(check_update)

        send_logs = QAction('Send Logs to Jas', self)
        send_logs.triggered.connect(self._send_logs)
        help_menu.addAction(send_logs)

        clear_logs = QAction('Clear Logs', self)
        clear_logs.triggered.connect(self._clear_logs)
        help_menu.addAction(clear_logs)

    def _set_theme_mode(self, mode: str):
        self._config.theme_mode = mode
        from typing import cast

        app = cast(QApplication | None, QApplication.instance())
        if app is not None:
            apply_theme(app, self, mode)

    def _restore_geometry(self):
        geo = self._config.window_geometry
        self.setGeometry(geo['x'], geo['y'], geo['width'], geo['height'])

    def _save_geometry(self):
        rect = self.geometry()
        self._config.window_geometry = {
            'x': rect.x(),
            'y': rect.y(),
            'width': rect.width(),
            'height': rect.height(),
        }

    def _setup_draft_timer(self):
        if self._config.auto_save_draft:
            self._draft_timer = QTimer(self)
            self._draft_timer.timeout.connect(self._auto_save_draft)
            self._draft_timer.start(self._config.draft_interval * 1000)

    def _check_first_run(self):
        if (
            not self._auth_manager.has_twitter_auth()
            and not self._auth_manager.has_bluesky_auth()
            and not self._auth_manager.has_bluesky_auth_alt()
        ):
            QTimer.singleShot(100, self._show_setup_wizard)

    def _show_setup_wizard(self):
        wizard = SetupWizard(self._auth_manager, self._config.theme_mode, self)
        wizard.exec_()
        self._refresh_platform_state()

    def _on_image_changed(self, image_path):
        self._cleanup_processed_images()
        if image_path:
            selected = self._get_selected_enabled_platforms()
            if selected:
                self._show_image_preview(image_path, selected)
                self._auto_save_draft()
            self._config.last_image_directory = str(image_path.parent)

    def _on_preview_requested(self):
        image_path = self._composer.get_image_path()
        if not image_path:
            return
        selected = self._get_selected_enabled_platforms()
        if not selected:
            return
        self._show_image_preview(image_path, selected)
        self._auto_save_draft()

    def _on_platforms_changed(self, platforms):
        self._config.last_selected_platforms = platforms
        self._refresh_platform_state()

    def _refresh_platform_state(self):
        enabled = []
        tw_creds = self._auth_manager.get_twitter_auth()
        bs_creds = self._auth_manager.get_bluesky_auth()
        bs_alt_creds = self._auth_manager.get_bluesky_auth_alt()

        if tw_creds and tw_creds.get('username'):
            enabled.append('twitter')
        if bs_creds and bs_creds.get('identifier'):
            enabled.append('bluesky')
        if bs_alt_creds and bs_alt_creds.get('identifier'):
            enabled.append('bluesky_alt')

        self._platform_selector.set_platform_enabled('twitter', 'twitter' in enabled)
        self._platform_selector.set_platform_enabled('bluesky', 'bluesky' in enabled)
        self._platform_selector.set_platform_enabled('bluesky_alt', 'bluesky_alt' in enabled)
        self._platform_selector.set_platform_username(
            'twitter', tw_creds.get('username') if tw_creds else None
        )
        self._platform_selector.set_platform_username(
            'bluesky', bs_creds.get('identifier') if bs_creds else None
        )
        self._platform_selector.set_platform_username(
            'bluesky_alt', bs_alt_creds.get('identifier') if bs_alt_creds else None
        )

        selected = self._platform_selector.get_selected()
        self._composer.set_platform_state(selected, enabled)

        has_enabled = bool(enabled)
        has_selected = bool(selected)
        self._post_btn.setEnabled(has_selected)
        self._test_btn.setEnabled(has_selected)
        if not has_enabled:
            self._post_btn.setEnabled(False)
            self._test_btn.setEnabled(False)

        image_path = self._composer.get_image_path()
        if image_path:
            selected_enabled = self._get_selected_enabled_platforms()
            missing = self._get_missing_processed_platforms(selected_enabled)
            if missing:
                self._show_image_preview(image_path, selected_enabled)
                self._auto_save_draft()

    def _get_selected_enabled_platforms(self) -> list[str]:
        enabled = set(self._platform_selector.get_enabled())
        selected = self._platform_selector.get_selected()
        return [platform for platform in selected if platform in enabled]

    def _get_platform_group(self, platform: str) -> str:
        return self._platform_groups.get(platform, platform)

    def _get_missing_processed_platforms(self, platforms: list[str]) -> list[str]:
        missing = []
        seen = set()
        for platform in platforms:
            group = self._get_platform_group(platform)
            if group in seen:
                continue
            seen.add(group)
            path = self._processed_images.get(group)
            if not path or not path.exists():
                missing.append(group)
        return missing

    def _show_image_preview(self, image_path: Path, platforms: list[str]):
        groups = []
        seen = set()
        for platform in platforms:
            group = self._get_platform_group(platform)
            if group in seen:
                continue
            seen.add(group)
            groups.append(group)
        dialog = ImagePreviewDialog(image_path, groups, self, existing_paths=self._processed_images)
        if dialog.exec_() == dialog.Accepted:
            for platform, path in dialog.get_processed_paths().items():
                if path and path.exists():
                    self._processed_images[platform] = path
        elif dialog.had_errors:
            reply = QMessageBox.question(
                self,
                'Image Processing Failed',
                'One or more image previews failed to process.\n\n'
                'Would you like to send logs to Jas?',
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self._send_logs()

    def _test_connections(self):
        self._status_bar.showMessage('Testing connections...')
        self._test_btn.setEnabled(False)
        QApplication.processEvents()

        results = []
        selected = self._get_selected_enabled_platforms()

        for name in selected:
            platform = self._platforms.get(name)
            if platform:
                success, error = platform.test_connection()
                display_name = self._get_platform_display_name(name)
                results.append((display_name, success, error))

        # Show results
        msg_parts = []
        for pname, success, error in results:
            if success:
                msg_parts.append(f'\u2714\ufe0f {pname} connected.')
            else:
                msg_parts.append(f'\u274c\ufe0f {pname} failed to connect: {error}')

        QMessageBox.information(self, 'Connection Test', '\n'.join(msg_parts))
        self._test_btn.setEnabled(True)
        self._status_bar.showMessage('Ready')

    def _get_platform_display_name(self, name: str) -> str:
        if name == 'twitter':
            creds = self._auth_manager.get_twitter_auth() or {}
            return PlatformSelector._format_platform_label('Twitter', creds.get('username'))
        if name == 'bluesky_alt':
            creds = self._auth_manager.get_bluesky_auth_alt() or {}
            return PlatformSelector._format_platform_label('Bluesky', creds.get('identifier'))
        if name == 'bluesky':
            creds = self._auth_manager.get_bluesky_auth() or {}
            return PlatformSelector._format_platform_label('Bluesky', creds.get('identifier'))
        return name

    def _do_post(self):
        text = self._composer.get_text()
        if not text.strip():
            QMessageBox.warning(self, 'Empty Post', 'Please enter some text before posting.')
            return

        selected = self._get_selected_enabled_platforms()
        if not selected:
            QMessageBox.warning(self, 'No Platforms', 'Please select at least one platform.')
            return

        # Check character limits
        for name in selected:
            platform = self._platforms.get(name)
            if platform:
                specs = platform.get_specs()
                if len(text) > specs.max_text_length:
                    QMessageBox.warning(
                        self,
                        'Text Too Long',
                        f'Your post is {len(text)} characters, but '
                        f'{specs.platform_name} allows {specs.max_text_length}.',
                    )
                    return

        # Process images if needed
        image_path = self._composer.get_image_path()
        if image_path:
            missing = self._get_missing_processed_platforms(selected)
            if missing:
                self._show_image_preview(image_path, selected)
                missing = self._get_missing_processed_platforms(selected)
                if missing:
                    QMessageBox.warning(
                        self,
                        'Image Error',
                        'Image previews could not be generated for all selected platforms.',
                    )
                    return

        # Build platform dict for selected only
        post_platforms = {n: self._platforms[n] for n in selected if n in self._platforms}

        # Disable UI during posting
        self._post_btn.setEnabled(False)
        self._test_btn.setEnabled(False)
        self._status_bar.showMessage('Posting...')
        QApplication.processEvents()

        # Post in background thread
        self._worker = PostWorker(
            post_platforms,
            text,
            self._processed_images,
            self._platform_groups,
        )
        self._worker.finished.connect(self._on_post_finished)
        self._worker.start()

    def _on_post_finished(self, results: list[PostResult]):
        self._post_btn.setEnabled(True)
        self._test_btn.setEnabled(True)
        self._status_bar.showMessage('Ready')

        dialog = ResultsDialog(results, self)
        result_code = dialog.exec_()

        if dialog.send_logs_requested:
            self._send_logs()
        elif result_code == 2:
            self._open_settings()

        # Clear draft on full success
        if all(r.success for r in results):
            self._clear_draft()
            self._composer.clear()
            self._cleanup_processed_images()

    def _open_settings(self):
        dialog = SettingsDialog(self._config, self._auth_manager, self)
        dialog.exec_()
        self._refresh_platform_state()

    def _show_about(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(f'About {APP_NAME}')
        dialog.setMinimumWidth(420)

        layout = QVBoxLayout(dialog)

        title = QLabel(f'<b>{APP_NAME}</b> v{APP_VERSION}')
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(title)

        icon_path = get_resource_path('icon.png')
        if icon_path.exists():
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    96,
                    96,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                icon_label = QLabel()
                icon_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
                icon_label.setPixmap(pixmap)
                layout.addWidget(icon_label)

        body = QLabel(
            'Post to Twitter and Bluesky simultaneously.<br><br>'
            'Copyright \u00a9 2026 '
            '<a href="https://x.com/jasmeralia">Morgan Blackthorne</a>, '
            '<a href="https://discord.gg/Seyngsh5MF">Winds of Storm</a><br>'
            'Licensed under the MIT License<br><br>'
            '<b>Built with:</b><br>'
            'PyQt5 \u2013 GUI framework<br>'
            'Tweepy \u2013 Twitter API client<br>'
            'atproto \u2013 Bluesky AT Protocol SDK<br>'
            'Pillow \u2013 Image processing<br>'
            'keyring \u2013 Credential storage<br>'
            'Requests \u2013 HTTP client<br>'
            'Packaging \u2013 Version parsing<br><br>'
            'Built for Rin with love.'
        )
        body.setOpenExternalLinks(True)
        body.setWordWrap(True)
        layout.addWidget(body)

        close_btn = QPushButton('Close')
        close_btn.clicked.connect(dialog.accept)
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        dialog.exec_()

    def _clear_logs(self):
        reply = QMessageBox.question(
            self,
            'Clear Logs',
            'This will delete saved logs and screenshots. Continue?',
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        logs_dir = get_logs_dir()
        current_log = get_current_log_path()
        reset_log_file()
        new_log = get_current_log_path()
        deleted = 0

        for log_path in logs_dir.glob('app_*.log'):
            if new_log and log_path == new_log:
                continue
            with contextlib.suppress(OSError):
                log_path.unlink()
                deleted += 1
        if current_log and current_log.exists():
            with contextlib.suppress(OSError):
                current_log.unlink()
                deleted += 1

        screenshots_dir = logs_dir / 'screenshots'
        for ss_path in screenshots_dir.glob('*.png'):
            with contextlib.suppress(OSError):
                ss_path.unlink()
                deleted += 1

        QMessageBox.information(self, 'Logs Cleared', f'Deleted {deleted} log file(s).')

    def _manual_update_check(self):
        self._status_bar.showMessage('Checking for updates...')
        QApplication.processEvents()

        update = check_for_updates(self._config.allow_prerelease_updates)
        if update:
            release_label = 'beta' if update.is_prerelease else 'stable'
            dialog = UpdateAvailableDialog(
                self,
                title='Update Available',
                latest_version=update.latest_version,
                current_version=update.current_version,
                release_label=release_label,
                release_name=update.release_name,
                release_notes=update.release_notes,
            )
            if dialog.exec_() == dialog.Accepted:
                self._download_update(update)
        else:
            QMessageBox.information(self, 'No Updates', "You're running the latest version!")

        self._status_bar.showMessage('Ready')

    def _send_logs(self):
        dialog = LogSubmitDialog(self)
        if dialog.exec_() != dialog.Accepted:
            return

        notes = dialog.get_notes()
        if not notes:
            QMessageBox.warning(
                self,
                'Missing Description',
                'Please describe what you were doing before sending logs.',
            )
            return

        self._status_bar.showMessage('Uploading logs...')
        QApplication.processEvents()

        success, message, details = self._log_uploader.upload(user_notes=notes)
        if success:
            QMessageBox.information(self, 'Logs Sent', message)
        else:
            msg = QMessageBox(self)
            msg.setWindowTitle('Upload Failed')
            msg.setIcon(QMessageBox.Warning)
            msg.setText(message)
            msg.setInformativeText(
                'You can copy the error details and send them in a private message.'
            )
            copy_btn = msg.addButton('Copy Error Details', QMessageBox.ActionRole)
            msg.addButton('Close', QMessageBox.AcceptRole)
            msg.exec_()
            if msg.clickedButton() == copy_btn:
                QApplication.clipboard().setText(details)

        self._status_bar.showMessage('Ready')

    def _auto_save_draft(self):
        text = self._composer.get_text()
        image_path = self._composer.get_image_path()
        selected = self._platform_selector.get_selected()
        enabled = self._platform_selector.get_enabled()

        if not text.strip() and not image_path:
            return

        processed = {
            name: str(path)
            for name, path in self._processed_images.items()
            if path and path.exists()
        }

        draft = {
            'text': text,
            'image_path': str(image_path) if image_path else None,
            'selected_platforms': selected,
            'enabled_platforms': enabled,
            'processed_images': processed,
            'timestamp': datetime.now().isoformat(),
            'auto_saved': True,
        }

        draft_path = get_drafts_dir() / 'current_draft.json'
        try:
            with open(draft_path, 'w') as f:
                json.dump(draft, f, indent=2)
            self._status_bar.showMessage('Draft auto-saved', 3000)
        except OSError:
            pass

    def _clear_draft(self):
        draft_path = get_drafts_dir() / 'current_draft.json'
        if draft_path.exists():
            draft_path.unlink()

    def restore_draft(self):
        """Check for and offer to restore a saved draft."""
        draft_path = get_drafts_dir() / 'current_draft.json'
        if not draft_path.exists():
            return

        try:
            with open(draft_path) as f:
                draft = json.load(f)
        except (OSError, json.JSONDecodeError):
            return

        text_preview = draft.get('text', '')[:50]
        if not text_preview:
            return

        reply = QMessageBox.question(
            self,
            'Unsaved Draft Found',
            f'You have an unsaved draft:\n\n"{text_preview}..."\n\nWould you like to restore it?',
            QMessageBox.Yes | QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            self._composer.set_text(draft.get('text', ''))
            image_path = draft.get('image_path')
            if image_path:
                self._composer.set_image_path(Path(image_path))
            platforms = draft.get('selected_platforms', [])
            if platforms:
                self._platform_selector.set_selected(platforms)
            restored = {}
            for name, path in draft.get('processed_images', {}).items():
                candidate = Path(path)
                if candidate.exists():
                    restored[name] = candidate
            self._processed_images = restored
            self._refresh_platform_state()
        else:
            self._clear_draft()

    def _cleanup_processed_images(self):
        for path in self._processed_images.values():
            if path and path.exists():
                with contextlib.suppress(OSError):
                    path.unlink()
        self._processed_images.clear()

    def check_for_updates_on_startup(self):
        """Check for updates if enabled (call after show)."""
        if self._config.auto_check_updates:
            update = check_for_updates(self._config.allow_prerelease_updates)
            if update:
                release_label = 'beta' if update.is_prerelease else 'stable'
                dialog = UpdateAvailableDialog(
                    self,
                    title='Update Available!',
                    latest_version=update.latest_version,
                    current_version=update.current_version,
                    release_label=release_label,
                    release_name=update.release_name,
                    release_notes=update.release_notes,
                )
                if dialog.exec_() == dialog.Accepted:
                    self._download_update(update)

    def _download_update(self, update):
        if not update.download_url:
            QMessageBox.warning(
                self,
                'No Installer Found',
                'No installer asset was found for this release.',
            )
            return

        downloads_dir = Path.home() / 'Downloads'
        downloads_dir.mkdir(parents=True, exist_ok=True)
        filename = f'GaleFling-Setup-v{update.latest_version}.exe'
        target_path = downloads_dir / filename

        progress = QProgressDialog('Downloading update...', None, 0, 100, self)
        progress.setWindowTitle('Downloading Update')
        progress.setWindowModality(Qt.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(True)
        progress.setAutoReset(True)

        self._update_worker = UpdateDownloadWorker(
            update.download_url,
            target_path,
            expected_size=update.download_size,
        )
        self._update_worker.progress.connect(progress.setValue)
        self._update_worker.finished.connect(
            lambda ok, path, msg: self._on_update_downloaded(ok, path, msg)
        )
        self._update_worker.start()
        progress.exec_()

    def _on_update_downloaded(self, success: bool, path: Path | None, message: str):
        if not success:
            QMessageBox.warning(
                self,
                'Download Failed',
                f'Failed to download the installer.\n{message}',
            )
            return

        if path is None:
            QMessageBox.warning(
                self,
                'Download Failed',
                'Installer download completed without a valid path.',
            )
            return

        self._launch_installer_after_exit(path)
        self._auto_save_draft()
        app = QApplication.instance()
        if app is not None:
            QTimer.singleShot(100, app.quit)

    def _launch_installer_after_exit(self, path: Path):
        logger = get_logger()
        if os.name != 'nt':
            QProcess.startDetached(str(path))
            return

        try:
            import ctypes

            shell32 = ctypes.windll.shell32  # type: ignore[attr-defined]
            result = shell32.ShellExecuteW(
                None,
                'runas',
                str(path),
                None,
                None,
                1,
            )
            if result <= 32:
                raise RuntimeError(f'ShellExecuteW failed: {result}')
            logger.info('Launched installer with UAC prompt', extra={'result': int(result)})
        except Exception as exc:
            logger.warning(
                'Failed to launch installer with UAC, launching directly', extra={'error': str(exc)}
            )
            QProcess.startDetached(str(path))

    def closeEvent(self, event):  # noqa: N802
        self._save_geometry()
        self._auto_save_draft()
        event.accept()
