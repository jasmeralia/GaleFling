#!/usr/bin/env python3
"""Decide whether the current workflow run should produce a release, and which tag.

Inputs come from environment variables (set by .github/workflows/release.yml):
  EVENT_NAME        github.event_name        (push, pull_request, workflow_dispatch)
  REF               github.ref               (refs/heads/foo, refs/tags/vX.Y.Z, ...)
  DISPATCH_RELEASE  workflow_dispatch input  (true/false, only on workflow_dispatch)

Outputs (written to $GITHUB_OUTPUT, also printed):
  is_release  true|false  build installer and publish a GitHub release
  create_tag  true|false  the tag must be created (false when it already exists)
  tag_name    vX.Y.Z

Resolution rules:
  pull_request                   -> is_release=false
  push refs/tags/vX.Y.Z          -> is_release=true, tag_name=$REF, create_tag=false
  push refs/heads/master         -> if HEAD already tagged: is_release=false (no double-release)
                                    else: tag_name = next patch after newest vX.Y.Z tag,
                                          is_release=true, create_tag=true
  workflow_dispatch (release=false) -> is_release=false (just lint+test the chosen ref)
  workflow_dispatch (release=true):
      ref is refs/tags/vX.Y.Z    -> same as push:tag (rebuild that tag)
      ref is refs/heads/master   -> same as push:master
      anything else              -> error (releases only from master or an existing tag)
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

TAG_RE = re.compile(r'^v\d+\.\d+\.\d+$')


def _git(args: list[str]) -> str:
    return subprocess.run(['git', *args], check=True, capture_output=True, text=True).stdout.strip()


def latest_tag() -> str | None:
    try:
        out = _git(['tag', '--list', 'v[0-9]*.[0-9]*.[0-9]*', '--sort=-v:refname'])
    except subprocess.CalledProcessError:
        return None
    for line in out.splitlines():
        line = line.strip()
        if TAG_RE.match(line):
            return line
    return None


def head_release_tag() -> str | None:
    try:
        out = _git(['tag', '--points-at', 'HEAD'])
    except subprocess.CalledProcessError:
        return None
    for line in out.splitlines():
        line = line.strip()
        if TAG_RE.match(line):
            return line
    return None


def next_patch(latest: str | None) -> str:
    if latest is None:
        return 'v1.0.0'
    major, minor, patch = (int(p) for p in latest[1:].split('.'))
    return f'v{major}.{minor}.{patch + 1}'


def emit(values: dict[str, str]) -> None:
    output_path = os.environ.get('GITHUB_OUTPUT')
    rendered = '\n'.join(f'{k}={v}' for k, v in values.items())
    if output_path:
        with Path(output_path).open('a', encoding='utf-8') as fh:
            fh.write(rendered + '\n')
    print(rendered)


def main() -> int:
    event = os.environ.get('EVENT_NAME', '')
    ref = os.environ.get('REF', '')
    dispatch_release = os.environ.get('DISPATCH_RELEASE', '').lower() == 'true'

    if event == 'pull_request':
        emit({'is_release': 'false', 'create_tag': 'false', 'tag_name': ''})
        return 0

    # Treat workflow_dispatch with release=true the same as the matching push event.
    if event == 'workflow_dispatch':
        if not dispatch_release:
            emit({'is_release': 'false', 'create_tag': 'false', 'tag_name': ''})
            return 0
        if ref.startswith('refs/tags/') or ref == 'refs/heads/master':
            event = 'push'
        else:
            print(
                f'workflow_dispatch with release=true requires refs/heads/master '
                f'or an existing refs/tags/vX.Y.Z, got {ref!r}',
                file=sys.stderr,
            )
            return 1

    if event == 'push' and ref.startswith('refs/tags/'):
        tag = ref.removeprefix('refs/tags/')
        if not TAG_RE.match(tag):
            print(f'Expected v-prefixed semver tag, got {tag!r}', file=sys.stderr)
            return 1
        emit({'is_release': 'true', 'create_tag': 'false', 'tag_name': tag})
        return 0

    if event == 'push' and ref == 'refs/heads/master':
        existing = head_release_tag()
        if existing:
            emit({'is_release': 'false', 'create_tag': 'false', 'tag_name': existing})
            return 0
        tag = next_patch(latest_tag())
        emit({'is_release': 'true', 'create_tag': 'true', 'tag_name': tag})
        return 0

    print(f'Unhandled event/ref combination: event={event!r} ref={ref!r}', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
