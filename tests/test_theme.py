"""Tests for dark theme utilities."""

from __future__ import annotations

import pytest
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QMainWindow

import src.utils.theme as theme
from src.utils import tokens


@pytest.fixture
def app_with_restored_theme():
    app = QApplication.instance()
    assert app is not None
    original_palette = QPalette(app.palette())
    original_stylesheet = app.styleSheet()

    yield app

    app.setStyleSheet(original_stylesheet)
    app.setPalette(original_palette)


def test_apply_theme_sets_dark_palette_stylesheet_and_title_bar(
    qtbot, monkeypatch, app_with_restored_theme
):
    window = QMainWindow()
    qtbot.addWidget(window)
    app = app_with_restored_theme

    calls: list[tuple[QMainWindow, bool]] = []

    def fake_title_bar(win, enabled):
        calls.append((win, enabled))

    monkeypatch.setattr(theme, 'set_windows_dark_title_bar', fake_title_bar)

    result = theme.apply_theme(app, window)

    palette = app.palette()
    assert result is None
    assert palette.color(QPalette.ColorRole.Window) == QColor(tokens.SURFACE)
    assert palette.color(QPalette.ColorRole.Highlight) == QColor(tokens.ACCENT)
    assert palette.color(QPalette.ColorRole.HighlightedText) == QColor(tokens.CANVAS)
    assert app.styleSheet() == theme.GLOBAL_QSS
    assert calls == [(window, True)]


def test_set_windows_dark_title_bar_not_windows(monkeypatch):
    monkeypatch.setattr(theme.sys, 'platform', 'linux')
    # Should be a no-op, not raise
    theme.set_windows_dark_title_bar(None, True)
