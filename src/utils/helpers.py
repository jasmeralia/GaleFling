"""Utility functions."""

import os
import platform
import sys
import uuid
from pathlib import Path
from typing import TypedDict


def get_app_data_dir() -> Path:
    """Return the application data directory, creating it if needed."""
    if sys.platform == 'win32':
        base = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))
    else:
        base = Path.home() / '.config'
    app_dir = base / 'GalePost'
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_auth_dir() -> Path:
    """Return the auth directory, creating it if needed."""
    auth_dir = get_app_data_dir() / 'auth'
    auth_dir.mkdir(parents=True, exist_ok=True)
    return auth_dir


def get_drafts_dir() -> Path:
    """Return the drafts directory, creating it if needed."""
    drafts_dir = get_app_data_dir() / 'drafts'
    drafts_dir.mkdir(parents=True, exist_ok=True)
    return drafts_dir


def get_logs_dir() -> Path:
    """Return the logs directory, creating it if needed."""
    logs_dir = get_app_data_dir() / 'logs'
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / 'screenshots').mkdir(exist_ok=True)
    return logs_dir


def get_installation_id() -> str:
    """Return a persistent unique ID for this installation."""
    id_file = get_app_data_dir() / 'installation_id'
    if id_file.exists():
        return id_file.read_text().strip()
    install_id = str(uuid.uuid4())
    id_file.write_text(install_id)
    return install_id


def get_resource_path(filename: str) -> Path:
    """Return path to a bundled resource file."""
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent.parent / 'resources'
    return base / filename


class OsInfo(TypedDict):
    name: str
    release: str
    version: str
    platform: str


def get_os_info() -> OsInfo:
    """Return OS name/version details."""
    if sys.platform == 'win32':
        win_release, win_version, win_csd, _ = platform.win32_ver()
        release = win_release or platform.release()
        version = win_version or platform.version()
        build = None
        if version:
            parts = version.split('.')
            if len(parts) >= 3 and parts[2].isdigit():
                build = int(parts[2])
        if release == '10' and build and build >= 22000:
            release = '11'
        csd = win_csd or 'SP0'
        return {
            'name': 'Windows',
            'release': release,
            'version': version,
            'platform': f'Windows-{release}-{version}-{csd}',
        }

    return {
        'name': platform.system(),
        'release': platform.release(),
        'version': platform.version(),
        'platform': platform.platform(),
    }
