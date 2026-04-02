"""Import app-level credentials from a provider JSON file.

Supports Meta (threads / instagram / facebook), Twitter OAuth 2.0,
and AWS media staging credentials. Partial imports (missing platforms)
are valid — only sections present and complete in the file are stored.
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


def import_credentials(path: Path, auth_manager: AuthManager) -> ImportResult:
    """Parse ``path`` and store recognised credentials via ``auth_manager``.

    Partial imports are valid — only sections present in the file are
    processed. The caller is responsible for any UI feedback.
    """
    result = ImportResult()

    try:
        with open(path) as f:
            data: dict[str, Any] = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        result.errors.append(f'Could not read file: {exc}')
        get_logger().warning(f'credential_importer: failed to read {path}: {exc}')
        return result

    version = data.get('version')
    if version != SUPPORTED_VERSION:
        result.version_mismatch = True
        result.errors.append(
            f'Unsupported credential file version: {version!r} (expected {SUPPORTED_VERSION})'
        )
        return result

    # ── Meta ─────────────────────────────────────────────────────────
    meta = data.get('meta', {})
    _import_meta_platform(meta, 'threads', auth_manager, result)
    _import_meta_platform(meta, 'instagram', auth_manager, result)
    _import_meta_platform(meta, 'facebook', auth_manager, result)

    # ── Twitter OAuth 2.0 ────────────────────────────────────────────
    twitter = data.get('twitter', {})
    if twitter:
        client_id = twitter.get('client_id', '').strip()
        client_secret = twitter.get('client_secret', '').strip()
        if client_id and client_secret:
            auth_manager.save_twitter_oauth2_app_credentials(client_id, client_secret)
            result.imported.append('twitter')
            get_logger().info('credential_importer: imported twitter OAuth 2.0 credentials')
        else:
            result.skipped.append('twitter')

    # ── AWS ──────────────────────────────────────────────────────────
    aws = data.get('aws', {})
    if aws:
        key_id = aws.get('access_key_id', '').strip()
        secret = aws.get('secret_access_key', '').strip()
        region = aws.get('region', 'us-west-2').strip()
        bucket = aws.get('media_staging_bucket', '').strip()
        if key_id and secret and bucket:
            auth_manager.save_aws_media_staging_credentials(key_id, secret, region, bucket)
            result.imported.append('aws')
            get_logger().info('credential_importer: imported AWS media staging credentials')
        else:
            result.skipped.append('aws')

    return result


def _import_meta_platform(
    meta: dict[str, Any],
    platform: str,
    auth_manager: AuthManager,
    result: ImportResult,
) -> None:
    """Import one Meta platform section; mutates ``result`` in place."""
    section = meta.get(platform, {})
    if not section:
        return

    app_id = section.get('app_id', '').strip()
    app_secret = section.get('app_secret', '').strip()
    key = f'meta.{platform}'

    if not (app_id and app_secret):
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
