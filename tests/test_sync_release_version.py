"""Tests for release version synchronization."""

from __future__ import annotations

from datetime import date

import pytest

from scripts.sync_release_version import (
    Version,
    choose_release_version,
    sync_release_version,
)


def _write_release_files(root, version='1.8.11'):
    constants = root / 'src' / 'utils'
    constants.mkdir(parents=True)
    (constants / 'constants.py').write_text(
        f"APP_NAME = 'GaleFling'\nAPP_VERSION = '{version}'\n",
        encoding='utf-8',
    )
    (root / 'README.md').write_text(
        '# GaleFling\n\n'
        '![Release Build](https://img.shields.io/github/actions/workflow/status/'
        f'jasmeralia/GaleFling/release.yml?event=push&branch=v{version}'
        '&label=Release%20Build)\n\n'
        f'**Current Version:** {version}\n',
        encoding='utf-8',
    )
    (root / 'CHANGELOG.md').write_text(
        '# Changelog\n\n'
        'All notable changes to this project will be documented in this file.\n\n'
        f'## [{version}] - 2026-04-09\n\n'
        '### Fixed\n'
        '- Existing entry.\n',
        encoding='utf-8',
    )


def test_choose_release_version_keeps_new_untagged_code_version():
    version, bumped = choose_release_version(Version.parse('1.8.14'), ['v1.8.13'])

    assert version == Version.parse('1.8.14')
    assert bumped is False


def test_choose_release_version_bumps_when_code_version_is_already_tagged():
    version, bumped = choose_release_version(Version.parse('1.8.13'), ['v1.8.12', 'v1.8.13'])

    assert version == Version.parse('1.8.14')
    assert bumped is True


def test_choose_release_version_bumps_stale_code_to_next_patch_after_latest_tag():
    version, bumped = choose_release_version(Version.parse('1.8.11'), ['v1.8.12', 'v1.8.13'])

    assert version == Version.parse('1.8.14')
    assert bumped is True


def test_sync_release_version_updates_files_when_bumped(tmp_path):
    _write_release_files(tmp_path)

    result = sync_release_version(
        tmp_path,
        ['v1.8.12', 'v1.8.13'],
        date(2026, 5, 7),
        write=True,
    )

    assert result == {
        'app_version': '1.8.11',
        'release_version': '1.8.14',
        'tag_name': 'v1.8.14',
        'bumped': True,
    }
    assert "APP_VERSION = '1.8.14'" in (tmp_path / 'src' / 'utils' / 'constants.py').read_text(
        encoding='utf-8'
    )
    readme = (tmp_path / 'README.md').read_text(encoding='utf-8')
    assert '**Current Version:** 1.8.14' in readme
    assert 'branch=v1.8.14' in readme
    changelog = (tmp_path / 'CHANGELOG.md').read_text(encoding='utf-8')
    assert changelog.index('## [1.8.14] - 2026-05-07') < changelog.index('## [1.8.11]')
    assert '- Automatic release for latest changes merged to master.' in changelog


def test_sync_release_version_does_not_write_when_code_version_is_releaseable(tmp_path):
    _write_release_files(tmp_path, version='1.8.14')

    result = sync_release_version(tmp_path, ['v1.8.13'], date(2026, 5, 7), write=True)

    assert result['tag_name'] == 'v1.8.14'
    assert result['bumped'] is False
    assert '## [1.8.14]' in (tmp_path / 'CHANGELOG.md').read_text(encoding='utf-8')


def test_version_rejects_non_three_part_versions():
    with pytest.raises(ValueError, match='Expected X.Y.Z version'):
        Version.parse('1.8')
