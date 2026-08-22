"""System-tray presence used by background scheduling."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from src.core.logger import get_logger
from src.utils.constants import APP_NAME
from src.utils.helpers import get_resource_path


class TrayIcon(QSystemTrayIcon):
    def __init__(
        self,
        parent: QWidget,
        *,
        show_window: Callable[[], None],
        show_scheduled: Callable[[], None],
        check_updates: Callable[[], None],
        show_about: Callable[[], None],
        exit_app: Callable[[], None],
    ) -> None:
        icon_path = get_resource_path('icon.png')
        if not icon_path.exists():
            icon_path = get_resource_path('icon.ico')
        super().__init__(QIcon(str(icon_path)), parent)
        self.setToolTip(APP_NAME)
        self._failure_callback: Callable[[], None] | None = None
        menu = QMenu(parent)
        self._add_action(menu, 'Show GaleFling', show_window)
        menu.addSeparator()
        self._scheduled_action = self._add_action(menu, 'Scheduled Posts (0)', show_scheduled)
        menu.addSeparator()
        self._add_action(menu, 'Check for Updates', check_updates)
        self._add_action(menu, 'About', show_about)
        menu.addSeparator()
        self._add_action(menu, 'Exit', exit_app)
        self.setContextMenu(menu)
        self.activated.connect(
            lambda reason: (
                show_window() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None
            )
        )
        self.messageClicked.connect(self._on_message_clicked)

    @staticmethod
    def _add_action(menu: QMenu, label: str, callback: Callable[[], None]) -> QAction:
        action = QAction(label, menu)
        menu.addAction(action)

        def trigger() -> None:
            get_logger().info(f'User selected Tray > {action.text()}')
            callback()

        action.triggered.connect(trigger)
        return action

    def set_pending_count(self, count: int) -> None:
        self._scheduled_action.setText(f'Scheduled Posts ({count})')

    def show_failure(self, accounts: list[str], callback: Callable[[], None]) -> None:
        self._failure_callback = callback
        account_text = ', '.join(accounts)
        self.showMessage(
            'Scheduled post failed',
            f'Could not post to: {account_text}. Click for details.',
            QSystemTrayIcon.MessageIcon.Critical,
            10000,
        )

    def _on_message_clicked(self) -> None:
        callback = self._failure_callback
        self._failure_callback = None
        if callback is not None:
            callback()
