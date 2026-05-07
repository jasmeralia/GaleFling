"""Synchronize release version files from APP_VERSION and existing tags."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

VERSION_RE = re.compile(r'^\d+\.\d+\.\d+$')
APP_VERSION_RE = re.compile(r"APP_VERSION = ['\"](?P<version>\d+\.\d+\.\d+)['\"]")
README_CURRENT_RE = re.compile(r'^\*\*Current Version:\*\* \d+\.\d+\.\d+$', re.MULTILINE)
README_BADGE_RE = re.compile(r'branch=v\d+\.\d+\.\d+')
CHANGELOG_HEADER_RE = re.compile(r'^## \[\d+\.\d+\.\d+\] - \d{4}-\d{2}-\d{2}$', re.MULTILINE)


@dataclass(frozen=True, order=True)
class Version:
    """Strict three-part semantic version."""

    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> Version:
        if not VERSION_RE.match(value):
            raise ValueError(f"Expected X.Y.Z version, got '{value}'")
        major, minor, patch = (int(part) for part in value.split('.'))
        return cls(major, minor, patch)

    @classmethod
    def parse_tag(cls, value: str) -> Version:
        if not value.startswith('v'):
            raise ValueError(f"Expected v-prefixed tag, got '{value}'")
        return cls.parse(value[1:])

    def bump_patch(self) -> Version:
        return Version(self.major, self.minor, self.patch + 1)

    def __str__(self) -> str:
        return f'{self.major}.{self.minor}.{self.patch}'

    @property
    def tag(self) -> str:
        return f'v{self}'


def read_app_version(constants_path: Path) -> Version:
    text = constants_path.read_text(encoding='utf-8')
    match = APP_VERSION_RE.search(text)
    if not match:
        raise ValueError(f'Could not find APP_VERSION in {constants_path}')
    return Version.parse(match.group('version'))


def parse_tags(tags: list[str]) -> list[Version]:
    versions: list[Version] = []
    for tag in tags:
        tag = tag.strip()
        if not tag:
            continue
        try:
            versions.append(Version.parse_tag(tag))
        except ValueError:
            continue
    return sorted(versions)


def choose_release_version(app_version: Version, tags: list[str]) -> tuple[Version, bool]:
    """Return target release version and whether files need a bump."""

    parsed_tags = parse_tags(tags)
    latest_tag_version = parsed_tags[-1] if parsed_tags else None
    tag_versions = set(parsed_tags)

    if app_version in tag_versions:
        base_version = latest_tag_version or app_version
        return base_version.bump_patch(), True

    if latest_tag_version is not None and app_version <= latest_tag_version:
        return latest_tag_version.bump_patch(), True

    return app_version, False


def replace_once(pattern: re.Pattern[str], replacement: str, text: str, label: str) -> str:
    updated, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise ValueError(f'Expected exactly one {label} replacement, got {count}')
    return updated


def update_constants(path: Path, version: Version) -> None:
    text = path.read_text(encoding='utf-8')
    updated = replace_once(APP_VERSION_RE, f"APP_VERSION = '{version}'", text, 'APP_VERSION')
    path.write_text(updated, encoding='utf-8')


def update_readme(path: Path, version: Version) -> None:
    text = path.read_text(encoding='utf-8')
    updated = replace_once(
        README_CURRENT_RE,
        f'**Current Version:** {version}',
        text,
        'README current version',
    )
    updated = replace_once(README_BADGE_RE, f'branch={version.tag}', updated, 'README badge tag')
    path.write_text(updated, encoding='utf-8')


def update_changelog(path: Path, version: Version, entry_date: date) -> None:
    text = path.read_text(encoding='utf-8')
    if f'## [{version}]' in text:
        return

    match = CHANGELOG_HEADER_RE.search(text)
    if not match:
        raise ValueError(f'Could not find first version section in {path}')

    entry = (
        f'## [{version}] - {entry_date.isoformat()}\n\n'
        '### Changed\n'
        '- Automatic release for latest changes merged to master.\n\n'
    )
    updated = text[: match.start()] + entry + text[match.start() :]
    path.write_text(updated, encoding='utf-8')


def sync_release_version(
    root: Path, tags: list[str], entry_date: date, write: bool
) -> dict[str, object]:
    constants_path = root / 'src' / 'utils' / 'constants.py'
    app_version = read_app_version(constants_path)
    release_version, bumped = choose_release_version(app_version, tags)

    if write and bumped:
        update_constants(constants_path, release_version)
        update_readme(root / 'README.md', release_version)
        update_changelog(root / 'CHANGELOG.md', release_version, entry_date)

    return {
        'app_version': str(app_version),
        'release_version': str(release_version),
        'tag_name': release_version.tag,
        'bumped': bumped,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='.', help='Repository root')
    parser.add_argument('--tags-file', required=True, help='File containing one git tag per line')
    parser.add_argument(
        '--date', default=date.today().isoformat(), help='Changelog date as YYYY-MM-DD'
    )
    parser.add_argument('--write', action='store_true', help='Update files when a bump is needed')
    args = parser.parse_args()

    tags = Path(args.tags_file).read_text(encoding='utf-8').splitlines()
    result = sync_release_version(
        Path(args.root),
        tags,
        date.fromisoformat(args.date),
        args.write,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
