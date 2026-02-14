"""Utility functions."""

import os
import sys
import uuid
from pathlib import Path


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
    if getattr(sys, 'frozen', False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).resolve().parent.parent.parent
    logs_dir = base / 'logs'
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
