"""Tests for release note section extraction."""

from scripts.release_notes import extract_sections


def test_extract_sections_between_versions():
    changelog = """# Changelog

## [0.2.2] - 2026-02-14

### Fixed
- Thing A

## [0.2.1] - 2026-02-13

### Added
- Thing B

## [0.2.0] - 2026-02-12

### Changed
- Thing C
"""

    result = extract_sections(changelog, current_version='0.2.2', prev_version='0.2.0')
    assert '0.2.2' in result
    assert '0.2.1' in result
    assert '0.2.0' not in result


def test_extract_sections_falls_back_to_current_only():
    changelog = """# Changelog

## [0.2.5] - 2026-02-14

### Fixed
- Thing A

## [0.2.4] - 2026-02-13

### Added
- Thing B
"""

    result = extract_sections(changelog, current_version='0.2.5', prev_version='1.0.0')
    assert '0.2.5' in result
    assert '0.2.4' not in result


def test_extract_sections_empty_when_neither_tag_documented():
    """Dependabot/chore releases often skip the changelog entirely; with no
    boundary to anchor on, we must not dump the whole file's history."""
    changelog = """# Changelog

## [0.2.0] - 2026-02-01

### Added
- Original feature
"""

    result = extract_sections(changelog, current_version='0.2.9', prev_version='0.2.8')
    assert result == ''
