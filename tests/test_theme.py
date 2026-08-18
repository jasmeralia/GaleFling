"""Tests for dark theme utilities."""

from __future__ import annotations

import re

import pytest
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QMainWindow

import src.utils.theme as theme
from src.utils import tokens

# Qt's QSS parser accepts only these for font-weight; anything else — including
# the plausible-looking small integers Qt5's old 0-99 QFont::Weight scale used
# — makes Qt silently drop the *entire* rule block, not just that property.
# https://doc.qt.io/qt-6/stylesheet-reference.html#font-weight
_VALID_QSS_FONT_WEIGHTS = {'normal', 'bold', 'bolder', 'lighter'} | {
    str(n) for n in range(100, 1000, 100)
}


def test_global_qss_font_weights_are_valid_qt_values():
    """An invalid font-weight (e.g. a bare 40) silently drops color/background
    too, for every widget matching that rule — this exact bug made nearly all
    body text render in a fallback gray instead of tokens.TEXT."""
    weights = re.findall(r'font-weight:\s*([^;]+);', theme.GLOBAL_QSS)
    assert weights, 'expected at least one font-weight declaration in GLOBAL_QSS'
    for weight in weights:
        assert weight.strip() in _VALID_QSS_FONT_WEIGHTS, f'invalid font-weight: {weight!r}'


def test_font_tokens_use_valid_qss_weights():
    for name in ('FONT_HEADING', 'FONT_BODY_STRONG', 'FONT_BODY', 'FONT_MONO'):
        _size, weight = getattr(tokens, name)
        assert str(weight) in _VALID_QSS_FONT_WEIGHTS, f'{name} has invalid weight {weight!r}'


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
