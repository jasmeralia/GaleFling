"""Dark theme utilities."""

from __future__ import annotations

import sys

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QWidget

from src.utils import tokens

GLOBAL_QSS = f"""
QWidget {{
    background-color: {tokens.SURFACE};
    color: {tokens.TEXT};
    font-size: {tokens.FONT_BODY[0]}pt;
    font-weight: {tokens.FONT_BODY[1]};
}}

QWidget:disabled {{
    color: {tokens.TEXT_MUTED};
}}

QPushButton {{
    background-color: {tokens.SURFACE_RAISED};
    color: {tokens.TEXT};
    border: 1px solid {tokens.BORDER};
    border-radius: 4px;
    padding: 6px 12px;
    font-weight: {tokens.FONT_BODY_STRONG[1]};
}}

QPushButton:hover,
QPushButton:focus {{
    border-color: {tokens.ACCENT};
}}

QPushButton:pressed {{
    background-color: {tokens.SURFACE_INSET};
    border-color: {tokens.ACCENT};
}}

QPushButton:disabled {{
    background-color: {tokens.SURFACE};
    color: {tokens.TEXT_MUTED};
    border-color: {tokens.BORDER};
}}

QLineEdit,
QTextEdit,
QPlainTextEdit {{
    background-color: {tokens.SURFACE_INSET};
    color: {tokens.TEXT};
    border: 1px solid {tokens.BORDER};
    border-radius: 4px;
    padding: 5px;
    selection-background-color: {tokens.ACCENT};
    selection-color: {tokens.CANVAS};
}}

QLineEdit:focus,
QTextEdit:focus,
QPlainTextEdit:focus {{
    border-color: {tokens.ACCENT};
}}

QLineEdit:disabled,
QTextEdit:disabled,
QPlainTextEdit:disabled {{
    color: {tokens.TEXT_MUTED};
}}

QTabBar::tab {{
    background-color: {tokens.SURFACE};
    color: {tokens.TEXT_MUTED};
    border: 1px solid {tokens.BORDER};
    padding: 7px 12px;
}}

QTabBar::tab:selected {{
    background-color: {tokens.SURFACE_RAISED};
    color: {tokens.TEXT};
    border-bottom-color: {tokens.ACCENT};
}}

QTabBar::tab:hover {{
    color: {tokens.TEXT};
    border-color: {tokens.ACCENT};
}}

QCheckBox {{
    color: {tokens.TEXT};
    spacing: 6px;
}}

QCheckBox:disabled {{
    color: {tokens.TEXT_MUTED};
}}

QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    background-color: {tokens.SURFACE_INSET};
    border: 1px solid {tokens.BORDER};
    border-radius: 3px;
}}

QCheckBox::indicator:hover {{
    border-color: {tokens.ACCENT};
}}

QCheckBox::indicator:checked {{
    background-color: {tokens.ACCENT};
    border-color: {tokens.ACCENT};
}}

QCheckBox::indicator:disabled {{
    background-color: {tokens.SURFACE};
    border-color: {tokens.BORDER};
}}

QScrollBar:vertical {{
    background: {tokens.SURFACE};
    width: 8px;
    margin: 0;
}}

QScrollBar:horizontal {{
    background: {tokens.SURFACE};
    height: 8px;
    margin: 0;
}}

QScrollBar::handle:vertical,
QScrollBar::handle:horizontal {{
    background: {tokens.SURFACE_RAISED};
    border-radius: 4px;
    min-height: 24px;
    min-width: 24px;
}}

QScrollBar::handle:vertical:hover,
QScrollBar::handle:horizontal:hover {{
    background: {tokens.BORDER};
}}

QScrollBar::add-line,
QScrollBar::sub-line,
QScrollBar::add-page,
QScrollBar::sub-page {{
    background: none;
    border: none;
}}
"""


def _apply_palette(app: QApplication) -> None:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(tokens.SURFACE))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(tokens.TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(tokens.SURFACE_INSET))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(tokens.SURFACE_RAISED))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(tokens.SURFACE_RAISED))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(tokens.TEXT))
    palette.setColor(QPalette.ColorRole.Text, QColor(tokens.TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(tokens.SURFACE_RAISED))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(tokens.TEXT))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(tokens.DANGER))
    palette.setColor(QPalette.ColorRole.Link, QColor(tokens.ACCENT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(tokens.ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(tokens.CANVAS))
    app.setPalette(palette)


def set_windows_dark_title_bar(window: QWidget, enabled: bool) -> None:
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        from ctypes import wintypes

        hwnd = int(window.winId())

        # Attribute values vary by Windows build. Try 20 first, then 19.
        dwmwa_use_immersive_dark_mode = 20
        dwmwa_use_immersive_dark_mode_before_20h1 = 19
        value = wintypes.BOOL(1 if enabled else 0)

        dwmapi = ctypes.WinDLL('dwmapi', use_last_error=True)
        for attr in (dwmwa_use_immersive_dark_mode, dwmwa_use_immersive_dark_mode_before_20h1):
            dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd),
                wintypes.DWORD(attr),
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
    except Exception:
        # Best-effort only. If this fails, the title bar stays default.
        return


def apply_theme(app: QApplication, window: QWidget | None = None) -> None:
    app.setStyle('Fusion')
    _apply_palette(app)
    app.setStyleSheet(GLOBAL_QSS)

    if window is not None:
        set_windows_dark_title_bar(window, True)
