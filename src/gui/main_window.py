"""Main application window."""

import json
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QThread, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from src.core.auth_manager import AuthManager
from src.core.config_manager import ConfigManager
from src.core.image_processor import process_image, validate_image
from src.core.log_uploader import LogUploader
from src.core.update_checker import check_for_updates
from src.gui.image_preview_tabs import ImagePreviewDialog
from src.gui.platform_selector import PlatformSelector
from src.gui.post_composer import PostComposer
from src.gui.results_dialog import ResultsDialog
from src.gui.settings_dialog import SettingsDialog
from src.gui.setup_wizard import SetupWizard
from src.platforms.bluesky import BlueskyPlatform
from src.platforms.twitter import TwitterPlatform
from src.utils.constants import APP_NAME, APP_VERSION, PostResult
from src.utils.helpers import get_drafts_dir


class PostWorker(QThread):
    """Background thread for posting to platforms."""
    finished = pyqtSignal(list)

    def __init__(self, platforms: dict, text: str,
                 processed_images: dict[str, Path | None]):
        super().__init__()
        self._platforms = platforms
        self._text = text
        self._processed_images = processed_images

    def run(self):
        results = []
        for name, platform in self._platforms.items():
            image_path = self._processed_images.get(name)
            result = platform.post(self._text, image_path)
            results.append(result)
        self.finished.emit(results)


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
        }

        self._init_ui()
        self._restore_geometry()
        self._setup_draft_timer()
        self._check_first_run()

    def _init_ui(self):
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")

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

        self._test_btn = QPushButton("Test Connections")
        self._test_btn.clicked.connect(self._test_connections)
        btn_layout.addWidget(self._test_btn)

        btn_layout.addSpacing(10)

        self._post_btn = QPushButton("Post Now")
        self._post_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; "
            "font-weight: bold; font-size: 14px; padding: 8px 24px; "
            "border-radius: 4px; }"
            "QPushButton:hover { background-color: #45a049; }"
            "QPushButton:disabled { background-color: #ccc; color: #888; }"
        )
        self._post_btn.clicked.connect(self._do_post)
        btn_layout.addWidget(self._post_btn)

        layout.addLayout(btn_layout)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready")

    def _create_menu_bar(self):
        menu_bar = self.menuBar()

        # File menu
        file_menu = menu_bar.addMenu("File")
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Settings menu
        settings_menu = menu_bar.addMenu("Settings")
        open_settings = QAction("Open Settings...", self)
        open_settings.triggered.connect(self._open_settings)
        settings_menu.addAction(open_settings)

        # Help menu
        help_menu = menu_bar.addMenu("Help")

        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

        check_update = QAction("Check for Updates", self)
        check_update.triggered.connect(self._manual_update_check)
        help_menu.addAction(check_update)

        send_logs = QAction("Send Logs to Jas", self)
        send_logs.triggered.connect(self._send_logs)
        help_menu.addAction(send_logs)

    def _restore_geometry(self):
        geo = self._config.window_geometry
        self.setGeometry(geo['x'], geo['y'], geo['width'], geo['height'])

    def _save_geometry(self):
        rect = self.geometry()
        self._config.window_geometry = {
            'x': rect.x(), 'y': rect.y(),
            'width': rect.width(), 'height': rect.height(),
        }

    def _setup_draft_timer(self):
        if self._config.auto_save_draft:
            self._draft_timer = QTimer(self)
            self._draft_timer.timeout.connect(self._auto_save_draft)
            self._draft_timer.start(self._config.draft_interval * 1000)

    def _check_first_run(self):
        if not self._auth_manager.has_twitter_auth() and \
           not self._auth_manager.has_bluesky_auth():
            QTimer.singleShot(100, self._show_setup_wizard)

    def _show_setup_wizard(self):
        wizard = SetupWizard(self._auth_manager, self)
        wizard.exec_()

    def _on_image_changed(self, image_path):
        self._processed_images.clear()
        if image_path:
            selected = self._platform_selector.get_selected()
            dialog = ImagePreviewDialog(image_path, selected, self)
            if dialog.exec_() == dialog.Accepted:
                self._processed_images = dialog.get_processed_paths()
            self._config.last_image_directory = str(image_path.parent)

    def _on_platforms_changed(self, platforms):
        self._config.last_selected_platforms = platforms

    def _test_connections(self):
        self._status_bar.showMessage("Testing connections...")
        self._test_btn.setEnabled(False)
        QApplication.processEvents()

        results = []
        selected = self._platform_selector.get_selected()

        for name in selected:
            platform = self._platforms.get(name)
            if platform:
                success, error = platform.test_connection()
                results.append((platform.get_platform_name(), success, error))

        # Show results
        msg_parts = []
        for pname, success, error in results:
            if success:
                msg_parts.append(f"\u2713 {pname}: Connected!")
            else:
                msg_parts.append(f"\u274C {pname}: Failed ({error})")

        QMessageBox.information(self, "Connection Test", "\n".join(msg_parts))
        self._test_btn.setEnabled(True)
        self._status_bar.showMessage("Ready")

    def _do_post(self):
        text = self._composer.get_text()
        if not text.strip():
            QMessageBox.warning(self, "Empty Post", "Please enter some text before posting.")
            return

        selected = self._platform_selector.get_selected()
        if not selected:
            QMessageBox.warning(self, "No Platforms", "Please select at least one platform.")
            return

        # Check character limits
        for name in selected:
            platform = self._platforms.get(name)
            if platform:
                specs = platform.get_specs()
                if len(text) > specs.max_text_length:
                    QMessageBox.warning(
                        self, "Text Too Long",
                        f"Your post is {len(text)} characters, but "
                        f"{specs.platform_name} allows {specs.max_text_length}."
                    )
                    return

        # Process images if needed
        image_path = self._composer.get_image_path()
        if image_path and not self._processed_images:
            # Process now if not already previewed
            for name in selected:
                platform = self._platforms.get(name)
                if platform:
                    specs = platform.get_specs()
                    error = validate_image(image_path, specs)
                    if error:
                        from src.core.error_handler import get_user_message
                        QMessageBox.warning(
                            self, "Image Error",
                            f"{specs.platform_name}: {get_user_message(error)}"
                        )
                        return
                    result = process_image(image_path, specs)
                    self._processed_images[name] = result.path

        # Build platform dict for selected only
        post_platforms = {n: self._platforms[n] for n in selected if n in self._platforms}

        # Disable UI during posting
        self._post_btn.setEnabled(False)
        self._test_btn.setEnabled(False)
        self._status_bar.showMessage("Posting...")
        QApplication.processEvents()

        # Post in background thread
        self._worker = PostWorker(post_platforms, text, self._processed_images)
        self._worker.finished.connect(self._on_post_finished)
        self._worker.start()

    def _on_post_finished(self, results: list[PostResult]):
        self._post_btn.setEnabled(True)
        self._test_btn.setEnabled(True)
        self._status_bar.showMessage("Ready")

        dialog = ResultsDialog(results, self)
        result_code = dialog.exec_()

        if dialog.send_logs_requested:
            self._send_logs()
        elif result_code == 2:
            self._open_settings()

        # Clear draft on full success
        if all(r.success for r in results):
            self._clear_draft()

    def _open_settings(self):
        dialog = SettingsDialog(self._config, self._auth_manager, self)
        dialog.exec_()

    def _show_about(self):
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<b>{APP_NAME}</b> v{APP_VERSION}<br><br>"
            f"Post to Twitter and Bluesky simultaneously.<br><br>"
            f"Built for Rin with love."
        )

    def _manual_update_check(self):
        self._status_bar.showMessage("Checking for updates...")
        QApplication.processEvents()

        update = check_for_updates()
        if update:
            reply = QMessageBox.question(
                self, "Update Available",
                f"Version {update.latest_version} is available.\n"
                f"You're currently using {update.current_version}.\n\n"
                f"{update.release_name}\n\n"
                f"Would you like to download it?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                url = update.download_url or update.browser_url
                QDesktopServices.openUrl(QUrl(url))
        else:
            QMessageBox.information(self, "No Updates", "You're running the latest version!")

        self._status_bar.showMessage("Ready")

    def _send_logs(self):
        self._status_bar.showMessage("Uploading logs...")
        QApplication.processEvents()

        success, message = self._log_uploader.upload()
        if success:
            QMessageBox.information(self, "Logs Sent", message)
        else:
            QMessageBox.warning(self, "Upload Failed", message)

        self._status_bar.showMessage("Ready")

    def _auto_save_draft(self):
        text = self._composer.get_text()
        image_path = self._composer.get_image_path()
        selected = self._platform_selector.get_selected()

        if not text.strip() and not image_path:
            return

        draft = {
            'text': text,
            'image_path': str(image_path) if image_path else None,
            'selected_platforms': selected,
            'timestamp': datetime.now().isoformat(),
            'auto_saved': True,
        }

        draft_path = get_drafts_dir() / 'current_draft.json'
        try:
            with open(draft_path, 'w') as f:
                json.dump(draft, f, indent=2)
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
            self, "Unsaved Draft Found",
            f"You have an unsaved draft:\n\n\"{text_preview}...\"\n\n"
            f"Would you like to restore it?",
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
        else:
            self._clear_draft()

    def check_for_updates_on_startup(self):
        """Check for updates if enabled (call after show)."""
        if self._config.auto_check_updates:
            update = check_for_updates()
            if update:
                reply = QMessageBox.question(
                    self, "Update Available!",
                    f"Version {update.latest_version} is now available.\n"
                    f"You're currently using {update.current_version}.\n\n"
                    f"Would you like to download it?",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Ignore,
                )
                if reply == QMessageBox.Yes:
                    url = update.download_url or update.browser_url
                    QDesktopServices.openUrl(QUrl(url))

    def closeEvent(self, event):
        self._save_geometry()
        self._auto_save_draft()
        event.accept()
