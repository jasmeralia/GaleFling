"""Tabbed WebView panel for confirm-click platforms."""

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.platforms.base_webview import BaseWebViewPlatform
from src.utils.constants import PostResult


class _StatusRow(QWidget):
    """Single row showing a platform's posting status."""

    def __init__(self, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        self._icon = QLabel('\u23f3')  # hourglass
        self._icon.setFixedWidth(24)
        layout.addWidget(self._icon)
        self._label = QLabel(label)
        self._label.setStyleSheet('font-size: 13px;')
        layout.addWidget(self._label)
        layout.addStretch()
        self._status = QLabel('Waiting...')
        self._status.setStyleSheet('font-size: 13px; color: #888;')
        layout.addWidget(self._status)

    def set_success(self, message: str = 'Posted!'):
        self._icon.setText('\u2714')  # checkmark
        self._icon.setStyleSheet('color: #4CAF50; font-size: 16px;')
        self._status.setText(message)
        self._status.setStyleSheet('font-size: 13px; color: #4CAF50;')

    def set_failure(self, message: str = 'Failed'):
        self._icon.setText('\u274c')  # cross
        self._icon.setStyleSheet('color: #F44336; font-size: 16px;')
        self._status.setText(message)
        self._status.setStyleSheet('font-size: 13px; color: #F44336;')

    def set_pending(self, message: str = 'Posting...'):
        self._icon.setText('\u23f3')  # hourglass
        self._icon.setStyleSheet('color: #FF9800; font-size: 16px;')
        self._status.setText(message)
        self._status.setStyleSheet('font-size: 13px; color: #FF9800;')


class WebViewPanel(QDialog):
    """Tabbed dialog showing WebView composer tabs for confirm-click platforms.

    The panel shows:
    - A status section at the top with results from API (silent) platforms
    - Tabs below for each WebView platform, each containing an embedded browser
    - A close/done button
    """

    all_confirmed = pyqtSignal()

    def __init__(
        self,
        api_results: list[PostResult],
        webview_platforms: list[BaseWebViewPlatform],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._api_results = api_results
        self._webview_platforms = webview_platforms
        self._status_rows: dict[str, _StatusRow] = {}
        self._tab_indices: dict[str, int] = {}
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle('Almost there! Confirm your posts below.')
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setMinimumSize(900, 700)
        self.showMaximized()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # ── API results status section ──────────────────────────────
        if self._api_results:
            api_header = QLabel('API Platform Results:')
            api_header.setStyleSheet('font-weight: bold; font-size: 13px;')
            layout.addWidget(api_header)

            for result in self._api_results:
                display = result.profile_name or result.platform
                row = _StatusRow(display, self)
                if result.success:
                    row.set_success('Posted!')
                else:
                    msg = result.error_message or result.error_code or 'Failed'
                    row.set_failure(msg)
                layout.addWidget(row)

        # ── WebView tabs ────────────────────────────────────────────
        if self._webview_platforms:
            if self._api_results:
                layout.addSpacing(8)

            instructions = QLabel('Click Post on each tab below:')
            instructions.setStyleSheet('font-weight: bold; font-size: 13px;')
            layout.addWidget(instructions)

            # Status rows for WebView platforms
            for platform in self._webview_platforms:
                display = platform.profile_name or platform.get_platform_name()
                row = _StatusRow(display, self)
                row.set_pending('Waiting for you to post...')
                self._status_rows[platform.account_id] = row
                layout.addWidget(row)

            # Tab widget
            self._tabs = QTabWidget()
            for i, platform in enumerate(self._webview_platforms):
                tab_label = platform.profile_name or platform.get_platform_name()
                view = platform.create_webview(self._tabs)
                self._tabs.addTab(view, tab_label)
                self._tab_indices[platform.account_id] = i

                # Start loading and pre-filling
                platform.navigate_to_composer()
                platform.start_success_polling()

            layout.addWidget(self._tabs, stretch=1)

        # ── Bottom buttons ──────────────────────────────────────────
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._mark_done_btn = QPushButton('Mark as Done')
        self._mark_done_btn.setToolTip(
            'Mark the current tab as posted even if the app could not detect it.'
        )
        self._mark_done_btn.clicked.connect(self._mark_current_done)
        btn_layout.addWidget(self._mark_done_btn)

        btn_layout.addSpacing(10)

        self._close_btn = QPushButton('Close')
        self._close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self._close_btn)

        layout.addLayout(btn_layout)

        # Poll for confirmed tabs
        self._check_timer = QTimer(self)
        self._check_timer.setInterval(1000)
        self._check_timer.timeout.connect(self._check_confirmed)
        self._check_timer.start()

    def _mark_current_done(self):
        """Manually mark the currently visible tab's platform as confirmed."""
        if not self._webview_platforms:
            return
        current_idx = self._tabs.currentIndex()
        for platform in self._webview_platforms:
            if self._tab_indices.get(platform.account_id) == current_idx:
                platform.mark_confirmed()
                self._update_status(platform)
                break

    def _check_confirmed(self):
        """Periodically check which WebView platforms have been confirmed."""
        all_done = True
        for platform in self._webview_platforms:
            if platform.is_post_confirmed:
                self._update_status(platform)
            else:
                all_done = False

        if all_done and self._webview_platforms:
            self._check_timer.stop()
            self.all_confirmed.emit()

    def _update_status(self, platform: BaseWebViewPlatform):
        """Update the status row for a platform."""
        row = self._status_rows.get(platform.account_id)
        if not row:
            return
        if platform.is_post_confirmed:
            if platform.captured_post_url:
                row.set_success('Posted!')
            else:
                row.set_success('Posted (link unavailable)')

            # Mark the tab with a checkmark
            idx = self._tab_indices.get(platform.account_id)
            if idx is not None:
                label = self._tabs.tabText(idx)
                if not label.startswith('\u2714'):
                    self._tabs.setTabText(idx, f'\u2714 {label}')

    def get_results(self) -> list[PostResult]:
        """Build PostResult list for all WebView platforms."""
        results = []
        for platform in self._webview_platforms:
            platform.stop_success_polling()
            results.append(platform.build_result())
        return results

    def closeEvent(self, event):  # noqa: N802
        """Clean up polling timers on close."""
        self._check_timer.stop()
        for platform in self._webview_platforms:
            platform.stop_success_polling()
        event.accept()
