"""Small non-modal in-app confirmation toast."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QLabel, QMainWindow

from src.utils import tokens


class Toast(QLabel):
    def __init__(self, text: str, parent: QMainWindow, duration_ms: int = 3500) -> None:
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f'background: {tokens.SURFACE_RAISED}; color: {tokens.TEXT}; '
            f'border: 1px solid {tokens.SUCCESS}; border-radius: 6px; '
            'padding: 10px 16px; font-weight: bold;'
        )
        self.setMaximumWidth(440)
        self.adjustSize()
        self.move(max(12, (parent.width() - self.width()) // 2), 18)
        self.raise_()
        self.show()
        QTimer.singleShot(duration_ms, self.deleteLater)


def show_toast(parent: QMainWindow, text: str) -> Toast:
    return Toast(text, parent)
