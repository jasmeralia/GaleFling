"""Theme utilities for light/dark mode handling."""

from __future__ import annotations

import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import QApplication, QMainWindow


def windows_prefers_dark() -> bool:
    if sys.platform != 'win32':
        return False
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r'SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize',
        )
        value, _ = winreg.QueryValueEx(key, 'AppsUseLightTheme')
        return value == 0
    except Exception:
        return False


def resolve_theme_mode(mode: str) -> str:
    if mode == 'dark':
        return 'dark'
    if mode == 'light':
        return 'light'
    return 'dark' if windows_prefers_dark() else 'light'


def _apply_dark_palette(app: QApplication):
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.WindowText, Qt.white)
    palette.setColor(QPalette.Base, QColor(35, 35, 35))
    palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ToolTipBase, Qt.white)
    palette.setColor(QPalette.ToolTipText, Qt.white)
    palette.setColor(QPalette.Text, Qt.white)
    palette.setColor(QPalette.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ButtonText, Qt.white)
    palette.setColor(QPalette.BrightText, Qt.red)
    palette.setColor(QPalette.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, Qt.black)
    app.setPalette(palette)


def _set_windows_dark_title_bar(window: QMainWindow, enabled: bool) -> None:
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


def apply_theme(app: QApplication, window: QMainWindow | None, mode: str) -> str:
    resolved = resolve_theme_mode(mode)
    use_dark = resolved == 'dark'

    app.setStyle('Fusion')
    if use_dark:
        _apply_dark_palette(app)
    else:
        app.setPalette(app.style().standardPalette())

    if window is not None:
        _set_windows_dark_title_bar(window, use_dark)

    return resolved
