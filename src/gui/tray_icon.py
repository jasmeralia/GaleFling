"""System-tray presence used by background scheduling."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from src.core.logger import get_logger
from src.utils import tokens
from src.utils.constants import APP_NAME
from src.utils.helpers import get_resource_path

# Corner-badge proportions, relative to the icon's own size, so both dots stay
# legible down to the ~16px trays render at instead of only at preview sizes.
_BADGE_DOT_RATIO = 0.34
_BADGE_RING_RATIO = 0.12
_BADGE_INSET_RATIO = 0.03


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
        self._icon_path: Path = icon_path
        self._has_pending = False
        self._has_unseen_failure = False
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
        has_pending = count > 0
        if has_pending != self._has_pending:
            self._has_pending = has_pending
            self._refresh_icon()

    def mark_failure_unseen(self) -> None:
        """Show the failure badge. Cleared by clear_failure_indicator(), not by a fix."""
        if not self._has_unseen_failure:
            self._has_unseen_failure = True
            self._refresh_icon()

    def clear_failure_indicator(self) -> None:
        if self._has_unseen_failure:
            self._has_unseen_failure = False
            self._refresh_icon()

    def _refresh_icon(self) -> None:
        self.setIcon(self._compose_icon())

    def _compose_icon(self) -> QIcon:
        """Base app icon plus abstract corner badges.

        Accent dot bottom-left for pending posts, danger dot bottom-right for an
        unseen scheduling failure — both corners stay clear of the artwork's
        wingtips, so the two badges remain distinguishable at small tray sizes.
        """
        base = QPixmap(str(self._icon_path))
        if base.isNull() or not (self._has_pending or self._has_unseen_failure):
            return QIcon(str(self._icon_path))

        pixmap = QPixmap(base)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        size = pixmap.width()
        dot = max(3, round(size * _BADGE_DOT_RATIO))
        ring = max(1, round(dot * _BADGE_RING_RATIO))
        inset = max(1, round(size * _BADGE_INSET_RATIO))

        def draw_dot(*, right: bool, color: str) -> None:
            x0 = (size - inset - dot) if right else inset
            y0 = size - inset - dot
            painter.setBrush(QColor(tokens.CANVAS))
            painter.drawEllipse(x0 - ring, y0 - ring, dot + 2 * ring, dot + 2 * ring)
            painter.setBrush(QColor(color))
            painter.drawEllipse(x0, y0, dot, dot)

        if self._has_pending:
            draw_dot(right=False, color=tokens.ACCENT)
        if self._has_unseen_failure:
            draw_dot(right=True, color=tokens.DANGER)
        painter.end()
        return QIcon(pixmap)

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
