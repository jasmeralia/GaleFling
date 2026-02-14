#!/usr/bin/env python3
"""Generate changelog sections between current and previous versions."""

from __future__ import annotations

import os
from pathlib import Path


def extract_sections(changelog: str, current_version: str, prev_version: str) -> str:
    sections: list[str] = []
    current_lines: list[str] = []
    in_section = False

    for line in changelog.splitlines(keepends=True):
        if line.startswith("## ["):
            if in_section:
                sections.append("".join(current_lines).rstrip())
                current_lines = []
            in_section = True
        if in_section:
            current_lines.append(line)

    if current_lines:
        sections.append("".join(current_lines).rstrip())

    def section_version(section: str) -> str:
        header = section.splitlines()[0]
        if header.startswith("## [") and "]" in header:
            return header.split("[", 1)[1].split("]", 1)[0]
        return ""

    output_sections: list[str] = []
    found_prev = False
    for section in sections:
        version = section_version(section)
        if not version:
            continue
        if version == prev_version:
            found_prev = True
            break
        output_sections.append(section)

    if not found_prev and current_version:
        for section in sections:
            if section_version(section) == current_version:
                output_sections = [section]
                break

    return "\n\n".join(output_sections).strip()


def main() -> int:
    current_tag = os.environ.get("CURRENT_TAG", "")
    prev_tag = os.environ.get("PREV_TAG", "")
    current_version = current_tag[1:] if current_tag.startswith("v") else current_tag
    prev_version = prev_tag[1:] if prev_tag.startswith("v") else prev_tag

    changelog_path = Path("CHANGELOG.md")
    if not changelog_path.exists():
        return 0

    changelog = changelog_path.read_text(encoding="utf-8")
    output = extract_sections(changelog, current_version, prev_version)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
