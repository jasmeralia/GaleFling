"""Per-user start-at-login integration for Windows and Linux."""

from __future__ import annotations

import contextlib
import importlib
import os
import sys
from pathlib import Path

_APP_NAME = 'GaleFling'
_AUTOSTART_FILENAME = 'galefling.desktop'


def _launch_arguments(start_minimized: bool) -> list[str]:
    if getattr(sys, 'frozen', False):
        # sys.executable points inside an AppImage's temporary mount. APPIMAGE is
        # the persistent path to the AppImage file and remains valid after logout.
        executable = os.environ.get('APPIMAGE') if sys.platform.startswith('linux') else None
        arguments = [executable or sys.executable]
    else:
        entrypoint = Path(__file__).resolve().parents[1] / 'main.py'
        arguments = [sys.executable, str(entrypoint)]
    arguments.append('--autostart')
    if start_minimized:
        arguments.append('--start-minimized')
    return arguments


def _windows_command(start_minimized: bool) -> str:
    return ' '.join(
        f'"{argument}"' if ' ' in argument else argument
        for argument in _launch_arguments(start_minimized)
    )


def _linux_desktop_entry(start_minimized: bool) -> str:
    command = ' '.join(
        _desktop_exec_argument(argument) for argument in _launch_arguments(start_minimized)
    )
    return (
        '[Desktop Entry]\n'
        'Type=Application\n'
        f'Name={_APP_NAME}\n'
        f'Exec={command}\n'
        'Terminal=false\n'
        'X-GNOME-Autostart-enabled=true\n'
    )


def _desktop_exec_argument(argument: str) -> str:
    """Quote one Desktop Entry Exec argument using the freedesktop rules."""
    escaped = argument.replace('%', '%%').replace('\\', '\\' * 4)
    for character in ('"', '`', '$'):
        escaped = escaped.replace(character, '\\' * 2 + character)
    return f'"{escaped}"'


def set_autostart(enabled: bool, *, start_minimized: bool) -> None:
    """Enable, update, or remove this user's login launch entry."""
    if sys.platform == 'win32':
        _set_windows_autostart(enabled, start_minimized=start_minimized)
        return
    if sys.platform.startswith('linux'):
        _set_linux_autostart(enabled, start_minimized=start_minimized)


def _set_windows_autostart(enabled: bool, *, start_minimized: bool) -> None:
    winreg = importlib.import_module('winreg')

    key_path = r'Software\Microsoft\Windows\CurrentVersion\Run'
    if enabled:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(
                key,
                _APP_NAME,
                0,
                winreg.REG_SZ,
                _windows_command(start_minimized),
            )
    else:
        with (
            contextlib.suppress(FileNotFoundError),
            winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                key_path,
                0,
                winreg.KEY_SET_VALUE,
            ) as key,
            contextlib.suppress(FileNotFoundError),
        ):
            winreg.DeleteValue(key, _APP_NAME)


def _linux_autostart_path() -> Path:
    config_home = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    return config_home / 'autostart' / _AUTOSTART_FILENAME


def _set_linux_autostart(enabled: bool, *, start_minimized: bool) -> None:
    path = _linux_autostart_path()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_linux_desktop_entry(start_minimized), encoding='utf-8')
