"""Parse and persist imported WebView session metadata.

An imported session is bound to the user agent that created it, so its WebView
profile must send that exact user agent rather than GaleFling's normalized one.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.core.webview_environment import chrome_compatible_user_agent

_METADATA_FILENAME = 'galefling_session.json'
_REQUIRED_KEYS = ('USER_ID', 'USER_AGENT', 'X_BC', 'COOKIE')
_METADATA_KEYS = ('user_agent', 'x_bc', 'user_id', 'imported_at')


class SessionImportError(Exception):
    """Raised when an auth.json file cannot be safely imported."""


@dataclass(frozen=True)
class ImportedSession:
    """Validated session values from an auth.json export."""

    user_id: str
    user_agent: str
    x_bc: str
    cookies: dict[str, str]


def parse_auth_json(raw: str) -> ImportedSession:
    """Parse and validate an OnlyFans auth.json export."""
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise SessionImportError(
            'This auth.json file is not valid JSON. Export it again and select the new file.'
        ) from exc

    if not isinstance(payload, dict):
        raise SessionImportError(
            'This auth.json file has the wrong structure. Export it again and select the new file.'
        )

    values: dict[str, str] = {}
    for key in _REQUIRED_KEYS:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise SessionImportError(
                f'The auth.json file is missing a non-empty {key} value. '
                'Export it again and select the new file.'
            )
        values[key] = value

    cookies: dict[str, str] = {}
    for segment in values['COOKIE'].split(';'):
        segment = segment.strip()
        if not segment:
            continue
        if '=' not in segment:
            raise SessionImportError(
                'The COOKIE entry in auth.json is malformed. Export it again instead of editing it.'
            )
        name, value = segment.split('=', 1)
        name = name.strip()
        if not name:
            raise SessionImportError(
                'The COOKIE entry in auth.json is malformed. Export it again instead of editing it.'
            )
        cookies[name] = value.strip()

    for cookie_name in ('auth_id', 'sess'):
        if cookie_name not in cookies or not cookies[cookie_name]:
            raise SessionImportError(
                f'The COOKIE entry is missing the {cookie_name} cookie. '
                'Log in again, export a fresh auth.json file, and retry.'
            )

    if values['USER_ID'] != cookies['auth_id']:
        raise SessionImportError(
            'USER_ID does not match the auth_id cookie. '
            'Export a fresh auth.json file instead of editing it by hand.'
        )

    return ImportedSession(
        user_id=values['USER_ID'],
        user_agent=values['USER_AGENT'],
        x_bc=values['X_BC'],
        cookies=cookies,
    )


def load_auth_json_file(path: Path) -> ImportedSession:
    """Read and parse an auth.json file, converting read failures to user-facing errors."""
    try:
        raw = path.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as exc:
        raise SessionImportError(
            'GaleFling could not read that auth.json file. Check the file and try again.'
        ) from exc
    return parse_auth_json(raw)


def save_session_metadata(storage_path: Path, session: ImportedSession) -> None:
    """Save non-cookie metadata alongside a persistent WebEngine profile."""
    storage_path.mkdir(parents=True, exist_ok=True)
    metadata = {
        'user_agent': session.user_agent,
        'x_bc': session.x_bc,
        'user_id': session.user_id,
        'imported_at': datetime.now(UTC).isoformat(),
    }
    (storage_path / _METADATA_FILENAME).write_text(
        json.dumps(metadata, indent=2) + '\n',
        encoding='utf-8',
    )


def load_session_metadata(storage_path: Path) -> dict | None:
    """Load valid imported-session metadata, returning ``None`` on any failure."""
    try:
        metadata = json.loads((storage_path / _METADATA_FILENAME).read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None

    if not isinstance(metadata, dict):
        return None
    if any(
        not isinstance(metadata.get(key), str) or not metadata[key].strip()
        for key in _METADATA_KEYS
    ):
        return None
    return metadata


def effective_user_agent(storage_path: Path, default_ua: str) -> str:
    """Return an imported profile's exact user agent or the normalized default."""
    metadata = load_session_metadata(storage_path)
    if metadata is not None:
        return metadata['user_agent']
    return chrome_compatible_user_agent(default_ua)
