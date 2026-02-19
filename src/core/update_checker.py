"""Check GitHub releases for application updates."""

from dataclasses import dataclass

import requests
from packaging.version import parse as parse_version

from src.core.logger import get_logger
from src.utils.constants import APP_VERSION

GITHUB_REPO = 'jasmeralia/galefling'
RELEASES_API = f'https://api.github.com/repos/{GITHUB_REPO}/releases'


@dataclass
class UpdateInfo:
    """Information about an available update."""

    current_version: str
    latest_version: str
    release_name: str
    release_notes: str
    download_url: str
    download_size: int
    browser_url: str


def check_for_updates(include_prerelease: bool = False) -> UpdateInfo | None:
    """Check GitHub for a newer version. Returns UpdateInfo or None."""
    logger = get_logger()

    try:
        response = requests.get(RELEASES_API, timeout=10)
        if response.status_code != 200:
            logger.info(f'Update check returned HTTP {response.status_code}')
            return None

        releases = response.json()
        if not isinstance(releases, list):
            logger.info('Update check returned unexpected payload')
            return None

        data = None
        for release in releases:
            if release.get('draft'):
                continue
            if release.get('prerelease') and not include_prerelease:
                continue
            data = release
            break
        if data is None:
            return None

        tag = data.get('tag_name', '')
        latest_str = tag.lstrip('v')

        if not latest_str:
            return None

        current = parse_version(APP_VERSION)
        latest = parse_version(latest_str)

        if latest <= current:
            logger.info(f'App is up to date ({APP_VERSION})')
            return None

        # Find installer asset
        download_url = ''
        download_size = 0
        for asset in data.get('assets', []):
            name = asset.get('name', '')
            if name.endswith('.exe') and 'Setup' in name:
                download_url = asset.get('browser_download_url', '')
                download_size = int(asset.get('size', 0) or 0)
                break

        browser_url = data.get('html_url', f'https://github.com/{GITHUB_REPO}/releases')

        logger.info(f'Update available: {APP_VERSION} -> {latest_str}')
        return UpdateInfo(
            current_version=APP_VERSION,
            latest_version=latest_str,
            release_name=data.get('name', f'Version {latest_str}'),
            release_notes=data.get('body', ''),
            download_url=download_url,
            download_size=download_size,
            browser_url=browser_url,
        )

    except Exception as e:
        logger.warning(f'Update check failed: {e}')
        return None
