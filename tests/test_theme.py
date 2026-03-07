"""Tests for theme utilities."""

from __future__ import annotations

from PyQt6.QtWidgets import QApplication, QMainWindow

import src.utils.theme as theme


def test_resolve_theme_mode_explicit():
    assert theme.resolve_theme_mode('dark') == 'dark'
    assert theme.resolve_theme_mode('light') == 'light'


def test_resolve_theme_mode_system_prefers_dark(monkeypatch):
    monkeypatch.setattr(theme, 'windows_prefers_dark', lambda: True)

    assert theme.resolve_theme_mode('system') == 'dark'


def test_resolve_theme_mode_system_prefers_light(monkeypatch):
    monkeypatch.setattr(theme, 'windows_prefers_dark', lambda: False)

    assert theme.resolve_theme_mode('system') == 'light'


def test_apply_theme_calls_title_bar(qtbot, monkeypatch):
    window = QMainWindow()
    qtbot.addWidget(window)
    app = QApplication.instance()
    assert app is not None

    calls: list[bool] = []

    def fake_title_bar(win, enabled):
        calls.append(enabled)

    monkeypatch.setattr(theme, 'set_windows_dark_title_bar', fake_title_bar)

    resolved = theme.apply_theme(app, window, 'dark')

    assert resolved == 'dark'
    assert calls == [True]


def test_apply_theme_light_palette(qtbot, monkeypatch):
    window = QMainWindow()
    qtbot.addWidget(window)
    app = QApplication.instance()
    assert app is not None

    monkeypatch.setattr(theme, 'set_windows_dark_title_bar', lambda *_: None)

    resolved = theme.apply_theme(app, window, 'light')

    assert resolved == 'light'


def test_windows_prefers_dark_not_windows(monkeypatch):
    monkeypatch.setattr(theme.sys, 'platform', 'linux')
    assert theme.windows_prefers_dark() is False


def test_set_windows_dark_title_bar_not_windows(monkeypatch):
    monkeypatch.setattr(theme.sys, 'platform', 'linux')
    # Should be a no-op, not raise
    theme.set_windows_dark_title_bar(None, True)


def test_apply_theme_without_window(qtbot, monkeypatch):
    app = QApplication.instance()
    assert app is not None

    monkeypatch.setattr(theme, 'set_windows_dark_title_bar', lambda *_: None)

    resolved = theme.apply_theme(app, None, 'dark')
    assert resolved == 'dark'


def test_apply_theme_resolves_system(qtbot, monkeypatch):
    app = QApplication.instance()
    assert app is not None

    monkeypatch.setattr(theme, 'windows_prefers_dark', lambda: False)
    monkeypatch.setattr(theme, 'set_windows_dark_title_bar', lambda *_: None)

    resolved = theme.apply_theme(app, None, 'system')
    assert resolved == 'light'
