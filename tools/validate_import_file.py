#!/usr/bin/env python3
"""Check an app-credential import file against what is already stored locally.

Structural validation only: confirms the file parses, matches the version and
key layout that ``src/core/credential_importer.py`` expects, and reports
whether each field would *add*, *change*, or *match* the corresponding value
already on disk under the GaleFling config directory. No credential value is
ever printed, logged, or returned by this script — only match/differ/new/empty
status, so it's safe to run against real credentials and safe to paste its
output anywhere.

This does not call ``import_credentials()`` and never writes anything -- it's
a read-only comparison, not a dry-run of the real import.

Usage::

    .venv/bin/python tools/validate_import_file.py path/to/creds_import.json
    .venv/bin/python tools/validate_import_file.py path/to/creds_import.json --config-dir ~/.config/GaleFling
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from src.core.credential_importer import SUPPORTED_VERSION
except ImportError:
    SUPPORTED_VERSION = 1  # keep in sync with src/core/credential_importer.py

# (import file dotted path, required keys, stored auth filename, stored keys)
# Mirrors the section handling in src/core/credential_importer.py /
# src/core/auth_manager.py -- update both places together if the schema changes.
SECTIONS = [
    (
        'meta.threads',
        ('app_id', 'app_secret'),
        'meta_threads_app_auth.json',
        ('app_id', 'app_secret'),
    ),
    (
        'meta.instagram',
        ('app_id', 'app_secret'),
        'meta_instagram_app_auth.json',
        ('app_id', 'app_secret'),
    ),
    (
        'meta.facebook',
        ('app_id', 'app_secret'),
        'meta_facebook_app_auth.json',
        ('app_id', 'app_secret'),
    ),
    (
        'twitter',
        ('client_id', 'client_secret'),
        'twitter_oauth2_app_auth.json',
        ('client_id', 'client_secret'),
    ),
    (
        'aws',
        ('access_key_id', 'secret_access_key', 'media_staging_bucket'),
        'aws_media_staging_auth.json',
        ('access_key_id', 'secret_access_key', 'region', 'media_staging_bucket'),
    ),
]


def default_config_dir() -> Path:
    if sys.platform == 'win32':
        base = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))
    else:
        base = Path.home() / '.config'
    return base / 'GaleFling'


def get_section(data: dict[str, Any], dotted: str) -> dict[str, Any]:
    node = data
    for part in dotted.split('.'):
        if not isinstance(node, dict):
            return {}
        node = node.get(part, {})
    return node if isinstance(node, dict) else {}


def field_status(import_value: Any, current_value: Any) -> str:
    imported = str(import_value).strip() if import_value is not None else ''
    current = str(current_value).strip() if current_value is not None else ''
    if not imported:
        return 'empty in import file'
    if not current:
        return 'new (nothing currently stored)'
    return 'matches current value' if imported == current else 'differs from current value'


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def validate(import_path: Path, config_dir: Path) -> int:
    try:
        with open(import_path) as f:
            data = json.load(f)
    except OSError as exc:
        print(f'Could not read {import_path}: {exc}')
        return 1
    except json.JSONDecodeError as exc:
        print(f'Not valid JSON: {exc}')
        return 1

    version = data.get('version')
    print(
        f'version: {version!r} (expected {SUPPORTED_VERSION!r}) '
        f'{"OK" if version == SUPPORTED_VERSION else "MISMATCH"}'
    )
    if version != SUPPORTED_VERSION:
        return 1

    auth_dir = config_dir / 'auth'
    print(f'comparing against: {auth_dir}')
    print()

    known_top_level = {'version', 'meta', 'twitter', 'aws'}
    unknown = sorted(set(data.keys()) - known_top_level)
    if unknown:
        print(f'note: unrecognized top-level key(s) {unknown} -- ignored by the current importer\n')

    meta = data.get('meta', {})
    redirect_uri = str(meta.get('oauth_redirect_uri', '')).strip()
    settings = load_json(auth_dir / 'meta_oauth_settings.json') or {}
    current_redirect = settings.get('oauth_redirect_uri', '')
    if redirect_uri:
        print(f'meta.oauth_redirect_uri: {field_status(redirect_uri, current_redirect)}')
    else:
        print('meta.oauth_redirect_uri: absent from import file (existing value, if any, is kept)')
    print()

    for dotted, required_keys, filename, stored_keys in SECTIONS:
        section = get_section(data, dotted)
        present_keys = [k for k in required_keys if str(section.get(k, '')).strip()]
        missing_keys = [k for k in required_keys if k not in present_keys]

        if not section:
            print(f'{dotted}: absent from import file')
            continue

        stored = load_json(auth_dir / filename)
        if missing_keys:
            print(
                f'{dotted}: INCOMPLETE in import file (missing: {missing_keys}) -- would be skipped'
            )
        else:
            print(f'{dotted}: complete in import file')

        for key in stored_keys:
            if key not in section:
                if stored and stored.get(key):
                    print(
                        f'  {key}: not in import file (current value would be kept, if section is skipped)'
                    )
                continue
            current_value = (stored or {}).get(key)
            print(f'  {key}: {field_status(section.get(key), current_value)}')
        print()

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('import_file', type=Path, help='Path to the credential import JSON file')
    parser.add_argument(
        '--config-dir',
        type=Path,
        default=None,
        help='GaleFling config directory to compare against (default: auto-detected app data dir)',
    )
    args = parser.parse_args()

    config_dir = args.config_dir.expanduser() if args.config_dir else default_config_dir()
    return validate(args.import_file.expanduser(), config_dir)


if __name__ == '__main__':
    raise SystemExit(main())
