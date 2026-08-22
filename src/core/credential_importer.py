"""Import app-level credentials from a provider JSON file.

Supports Meta (threads / instagram / facebook), Twitter OAuth 2.0,
AWS media staging, and SMTP (scheduled-post failure notifications)
credentials. Partial imports (missing platforms) are valid — only
sections present and complete in the file are stored.

Hardened against malformed input: a section present with the wrong JSON
type (not an object), or a field present with the wrong type (not a
string), is reported as an error/skip rather than raising. Diagnostic
logging for missing/blank fields names the required field *names* only —
literal constants from this module, never a value read from the file —
so nothing from the credentials themselves can reach the log file (which
may be uploaded and emailed via the existing log-upload path).

See docs/CREDENTIALS.md for the full schema, per-field required-ness,
and why SUPPORTED_VERSION isn't bumped for additive sections.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.core.auth_manager import AuthManager
from src.core.logger import get_logger

SUPPORTED_VERSION = 1


@dataclass
class ImportResult:
    """Summary of what was imported."""

    imported: list[str] = field(default_factory=list)  # e.g. ['meta.threads', 'aws']
    skipped: list[str] = field(default_factory=list)  # present but incomplete
    errors: list[str] = field(default_factory=list)  # parse / validation errors
    version_mismatch: bool = False

    @property
    def success(self) -> bool:
        return not self.errors and bool(self.imported)


def _get_section(data: dict[str, Any], key: str, result: ImportResult) -> dict[str, Any] | None:
    """Return ``data[key]`` as a dict.

    Returns ``None`` when the key is absent or explicitly ``null`` — both mean
    "nothing to import here," matching how an omitted key already behaves.
    A key present with any other non-object type is malformed: records an
    error (naming only the section and the offending JSON type, never a
    value) and returns ``None`` so the caller skips it without crashing.
    """
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, dict):
        type_name = type(value).__name__
        result.errors.append(
            f"'{key}' must be a JSON object, got {type_name} — file may be malformed"
        )
        get_logger().warning(
            f'credential_importer: {key!r} section was {type_name}, expected object'
        )
        return None
    return value


def _field_str(section: dict[str, Any], key: str) -> str:
    """Return ``section[key]`` as a stripped string, or ``''`` if absent/null/not a string."""
    value = section.get(key)
    if not isinstance(value, str):
        return ''
    return value.strip()


def _log_missing_fields(
    section_name: str, section: dict[str, Any], required: tuple[str, ...]
) -> None:
    """Log which required field *names* (never values) are missing or blank for a skipped section."""
    missing = [name for name in required if not _field_str(section, name)]
    if missing:
        get_logger().warning(
            f'credential_importer: {section_name} section incomplete — missing/blank fields: {missing}'
        )


def import_credentials(path: Path, auth_manager: AuthManager) -> ImportResult:
    """Parse ``path`` and store recognised credentials via ``auth_manager``.

    Partial imports are valid — only sections present in the file are
    processed. The caller is responsible for any UI feedback.
    """
    result = ImportResult()

    try:
        with open(path) as f:
            data: Any = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        result.errors.append(f'Could not read file: {exc}')
        get_logger().warning(f'credential_importer: failed to read {path}: {exc}')
        return result

    if not isinstance(data, dict):
        type_name = type(data).__name__
        result.errors.append(
            f'Credential file must contain a JSON object at the top level, got {type_name}'
        )
        get_logger().warning(
            f'credential_importer: top-level JSON was {type_name}, expected object'
        )
        return result

    version = data.get('version')
    if version != SUPPORTED_VERSION:
        result.version_mismatch = True
        result.errors.append(
            f'Unsupported credential file version: {version!r} (expected {SUPPORTED_VERSION})'
        )
        return result

    # ── Meta ─────────────────────────────────────────────────────────
    meta = _get_section(data, 'meta', result)
    if meta is not None:
        _import_meta_platform(meta, 'threads', auth_manager, result)
        _import_meta_platform(meta, 'instagram', auth_manager, result)
        _import_meta_platform(meta, 'facebook', auth_manager, result)

        oauth_redirect_uri = _field_str(meta, 'oauth_redirect_uri')
        if oauth_redirect_uri:
            auth_manager.save_meta_oauth_redirect_uri(oauth_redirect_uri)
            result.imported.append('meta.oauth_redirect_uri')
            get_logger().info('credential_importer: imported meta oauth_redirect_uri')

    # ── Twitter OAuth 2.0 ────────────────────────────────────────────
    twitter = _get_section(data, 'twitter', result)
    if twitter is not None:
        client_id = _field_str(twitter, 'client_id')
        client_secret = _field_str(twitter, 'client_secret')
        if client_id and client_secret:
            auth_manager.save_twitter_oauth2_app_credentials(client_id, client_secret)
            result.imported.append('twitter')
            get_logger().info('credential_importer: imported twitter OAuth 2.0 credentials')
        else:
            _log_missing_fields('twitter', twitter, ('client_id', 'client_secret'))
            result.skipped.append('twitter')

    # ── AWS ──────────────────────────────────────────────────────────
    aws = _get_section(data, 'aws', result)
    if aws is not None:
        key_id = _field_str(aws, 'access_key_id')
        secret = _field_str(aws, 'secret_access_key')
        region = _field_str(aws, 'region') or 'us-west-2'
        bucket = _field_str(aws, 'media_staging_bucket')
        if key_id and secret and bucket:
            auth_manager.save_aws_media_staging_credentials(key_id, secret, region, bucket)
            result.imported.append('aws')
            get_logger().info('credential_importer: imported AWS media staging credentials')
        else:
            _log_missing_fields(
                'aws', aws, ('access_key_id', 'secret_access_key', 'media_staging_bucket')
            )
            result.skipped.append('aws')

    # ── SMTP ─────────────────────────────────────────────────────────
    smtp = _get_section(data, 'smtp', result)
    if smtp is not None:
        host = _field_str(smtp, 'host')
        username = _field_str(smtp, 'username')
        app_password = _field_str(smtp, 'app_password')
        try:
            port = int(smtp.get('port', 587) or 587)
        except (TypeError, ValueError):
            port = 587
        if host and username and app_password:
            auth_manager.save_smtp_credentials(host, port, username, app_password)
            result.imported.append('smtp')
            get_logger().info('credential_importer: imported SMTP credentials')
        else:
            _log_missing_fields('smtp', smtp, ('host', 'username', 'app_password'))
            result.skipped.append('smtp')

    return result


def _import_meta_platform(
    meta: dict[str, Any],
    platform: str,
    auth_manager: AuthManager,
    result: ImportResult,
) -> None:
    """Import one Meta platform section; mutates ``result`` in place."""
    key = f'meta.{platform}'
    section = meta.get(platform)
    if section is None:
        return
    if not isinstance(section, dict):
        type_name = type(section).__name__
        result.errors.append(
            f"'{key}' must be a JSON object, got {type_name} — file may be malformed"
        )
        get_logger().warning(
            f'credential_importer: {key!r} section was {type_name}, expected object'
        )
        return

    app_id = _field_str(section, 'app_id')
    app_secret = _field_str(section, 'app_secret')

    if not (app_id and app_secret):
        _log_missing_fields(key, section, ('app_id', 'app_secret'))
        result.skipped.append(key)
        return

    save_fn = {
        'threads': auth_manager.save_meta_threads_app_credentials,
        'instagram': auth_manager.save_meta_instagram_app_credentials,
        'facebook': auth_manager.save_meta_facebook_app_credentials,
    }.get(platform)
    if save_fn:
        save_fn(app_id, app_secret)
        result.imported.append(key)
        get_logger().info(f'credential_importer: imported {key} credentials')
