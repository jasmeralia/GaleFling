from pathlib import Path
from types import SimpleNamespace

from src.core import autostart


def test_linux_autostart_entry_includes_minimized_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(autostart.sys, 'platform', 'linux')
    monkeypatch.setattr(autostart.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(autostart.sys, 'executable', '/opt/Gale Fling/galefling')
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))

    autostart.set_autostart(True, start_minimized=True)

    entry = (tmp_path / 'autostart' / 'galefling.desktop').read_text()
    assert 'Exec="/opt/Gale Fling/galefling" "--autostart" "--start-minimized"' in entry


def test_linux_appimage_autostart_uses_persistent_image_path(tmp_path, monkeypatch):
    monkeypatch.setattr(autostart.sys, 'platform', 'linux')
    monkeypatch.setattr(autostart.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(autostart.sys, 'executable', '/tmp/.mount_Gale/usr/bin/galefling')
    monkeypatch.setenv('APPIMAGE', '/home/rin/Applications/Gale Fling.AppImage')
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))

    autostart.set_autostart(True, start_minimized=True)

    entry = (tmp_path / 'autostart' / 'galefling.desktop').read_text()
    assert 'Exec="/home/rin/Applications/Gale Fling.AppImage"' in entry
    assert '/tmp/.mount_Gale' not in entry


def test_linux_source_autostart_uses_absolute_entrypoint(tmp_path, monkeypatch):
    monkeypatch.setattr(autostart.sys, 'platform', 'linux')
    monkeypatch.setattr(autostart.sys, 'frozen', False, raising=False)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))

    autostart.set_autostart(True, start_minimized=False)

    entry = (tmp_path / 'autostart' / 'galefling.desktop').read_text()
    expected_entrypoint = Path(autostart.__file__).resolve().parents[1] / 'main.py'
    assert f'"{expected_entrypoint}"' in entry
    assert '"-m" "src.main"' not in entry


def test_linux_autostart_regular_window_and_disable(tmp_path, monkeypatch):
    monkeypatch.setattr(autostart.sys, 'platform', 'linux')
    monkeypatch.setattr(autostart.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(autostart.sys, 'executable', '/opt/galefling')
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))

    autostart.set_autostart(True, start_minimized=False)
    path = Path(tmp_path) / 'autostart' / 'galefling.desktop'
    assert '--autostart' in path.read_text()
    assert '--start-minimized' not in path.read_text()

    autostart.set_autostart(False, start_minimized=False)
    assert not path.exists()


def test_windows_autostart_creates_updates_and_removes_run_value(monkeypatch):
    values = {}

    class FakeKey:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    fake_winreg = SimpleNamespace(
        HKEY_CURRENT_USER=object(),
        KEY_SET_VALUE=2,
        REG_SZ=1,
        CreateKey=lambda *_args: FakeKey(),
        OpenKey=lambda *_args: FakeKey(),
        SetValueEx=lambda _key, name, _reserved, _kind, value: values.__setitem__(name, value),
        DeleteValue=lambda _key, name: values.pop(name),
    )
    monkeypatch.setattr(autostart.sys, 'platform', 'win32')
    monkeypatch.setattr(autostart.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(autostart.sys, 'executable', r'C:\Program Files\GaleFling\GaleFling.exe')
    monkeypatch.setattr(autostart.importlib, 'import_module', lambda _name: fake_winreg)

    autostart.set_autostart(True, start_minimized=True)
    assert values['GaleFling'] == (
        r'"C:\Program Files\GaleFling\GaleFling.exe" --autostart --start-minimized'
    )

    autostart.set_autostart(False, start_minimized=False)
    assert values == {}


def test_windows_autostart_disable_tolerates_missing_run_key(monkeypatch):
    fake_winreg = SimpleNamespace(
        HKEY_CURRENT_USER=object(),
        KEY_SET_VALUE=2,
        REG_SZ=1,
        OpenKey=lambda *_args: (_ for _ in ()).throw(FileNotFoundError()),
    )
    monkeypatch.setattr(autostart.sys, 'platform', 'win32')
    monkeypatch.setattr(autostart.importlib, 'import_module', lambda _name: fake_winreg)

    autostart.set_autostart(False, start_minimized=False)
