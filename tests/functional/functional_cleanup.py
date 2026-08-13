"""Cleanup policy for API-platform mutating functional tests.

Twitter, Bluesky, Instagram, Threads and Facebook Page mutating tests delete the post
they create as soon as their assertions pass.  That keeps the live account clean, but it
also destroys the only evidence the post ever existed — and `AGENTS.md` rule 9 requires a
live artifact to survive until inspection is finished.  A probe against an
already-deleted post answers "not found", which reads identically to a real measurement
failure, so deleting early has already cost a re-run.

``--leave-mutating-artifacts`` (or ``GALEFLING_LEAVE_MUTATING_ARTIFACTS=1``) suppresses
the delete and prints what the operator needs in order to find and remove the post by
hand.  Deletion stays the default: an unattended run must not litter the account.

WebView mutating tests are *not* routed through here.  They already leave their artifacts
up unconditionally and print ``CLEANUP PENDING``; task #420 covers giving them an opt-in
deletion pass.  The ledger written below deliberately uses the record shape that task
specifies, so the two can share one cleanup consumer instead of two formats.

No credential values are printed or written to the ledger (`AGENTS.md` rule 8).  That is
why a failed delete is reported by exception *class name* rather than message: a
``requests`` or ``tweepy`` error renders the request URL, and for the Graph platforms
that URL carries ``access_token`` in its query string.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

LEAVE_ARTIFACTS_ENV = 'GALEFLING_LEAVE_MUTATING_ARTIFACTS'
LEAVE_ARTIFACTS_OPTION = '--leave-mutating-artifacts'

# Machine-readable list of artifacts still live on a platform, so a later cleanup pass
# does not have to re-derive them from pytest scrollback.  Gitignored: it names real
# posts on real accounts.
LEDGER_PATH = Path(__file__).parent / '.artifacts.jsonl'

_CONFIG = None


class ArtifactAlreadyGoneError(Exception):
    """Raised by a delete callback when the artifact was already absent.

    Kept distinct from a failure so a repeated cleanup is not reported as a broken
    teardown, and so "the platform says this is not there" cannot be mistaken for
    "the delete call itself broke".
    """


class ArtifactDeleteFailedError(Exception):
    """Deletion failed, with a message the caller has confirmed is credential-free.

    Only this exception's message is echoed.  Every other exception is reported by class
    name alone — see the module docstring.
    """


def configure(config) -> None:
    """Record the pytest config so the option and the terminal are reachable from tests."""
    global _CONFIG
    _CONFIG = config


def leave_artifacts_enabled() -> bool:
    """Return whether mutating artifacts should be left on the platform for inspection."""
    if os.environ.get(LEAVE_ARTIFACTS_ENV):
        return True
    if _CONFIG is None:
        return False
    return bool(_CONFIG.getoption(LEAVE_ARTIFACTS_OPTION, default=False))


def post_tag(post_text: str) -> str:
    """Return the cleanup tag embedded in text built by ``conftest.mutating_post_text()``.

    That helper puts the 8-character UUID tag first, so the tag is the leading token —
    including for the no-extra-parts case, where the text *is* the tag.
    """
    parts = post_text.split(maxsplit=1)
    return parts[0] if parts else ''


def _emit(message: str) -> None:
    """Print a line that survives pytest's output capture on a *passing* test.

    A plain ``print`` is swallowed unless the test fails or the run passes ``-s``.  The
    artifact tag is needed most precisely when the test passed, so capture is suspended
    for the write rather than relying on every caller remembering the flag.
    """
    capture = _CONFIG.pluginmanager.getplugin('capturemanager') if _CONFIG else None
    if capture is None:
        print(message)
        return
    with capture.global_and_fixture_disabled():
        print(message)


def _current_test_id() -> str | None:
    """Return the running test's node ID, without pytest's trailing phase marker."""
    current = os.environ.get('PYTEST_CURRENT_TEST', '')
    return current.split(' (')[0] or None


def _record_live_artifact(platform: str, tag: str, url: str | None, account_id: str | None) -> None:
    """Append one still-live artifact to the cleanup ledger.

    Field names and types are fixed by task #420 so a single cleanup pass can consume
    both API and WebView records.  ``url`` is written as ``null`` rather than omitted
    when no permalink was available.
    """
    record = {
        'platform': platform,
        'account_id': account_id,
        'tag': tag,
        'url': url,
        'test': _current_test_id(),
        'created_at': datetime.now(UTC).isoformat(),
    }
    try:
        with LEDGER_PATH.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(record) + '\n')
    except OSError as exc:
        # Never fail a test over bookkeeping, but never lose it silently either — the
        # printed tag is the operator's only remaining handle on the post.
        _emit(f'  ledger write failed ({type(exc).__name__}) — record only the printed tag')


def finish_mutating_artifact(
    platform: str,
    post_text: str,
    *,
    delete: Callable[[], None],
    url: str | None = None,
    account_id: str | None = None,
) -> None:
    """Delete the artifact a mutating test just created, or leave it up for inspection.

    ``delete`` takes no arguments and raises on failure: :class:`ArtifactAlreadyGoneError` when
    the platform reports the artifact is already absent, :class:`ArtifactDeleteFailedError` with
    a credential-free message for a known-bad response, anything else for an unexpected
    error.  Returning normally means the artifact was removed.

    The tag line is emitted before anything URL-related is touched, so a missing or
    unusable permalink can never suppress it — the tag is the only fallback the operator
    has for finding the post by hand.
    """
    tag = post_tag(post_text)

    if leave_artifacts_enabled():
        _emit(
            f'\n  {platform} artifact left up (tag {tag}) — {LEAVE_ARTIFACTS_OPTION} is set; '
            f'delete it manually once inspection is finished'
        )
        _emit_url(platform, url)
        _record_live_artifact(platform, tag, url, account_id)
        return

    try:
        delete()
    except ArtifactAlreadyGoneError:
        _emit(f'\n  {platform} artifact already gone (tag {tag})')
    except ArtifactDeleteFailedError as exc:
        _emit(
            f'\n  {platform} artifact delete FAILED (tag {tag}) — {exc}; '
            f'the post is still live, delete it manually'
        )
        _emit_url(platform, url)
        _record_live_artifact(platform, tag, url, account_id)
    except Exception as exc:
        _emit(
            f'\n  {platform} artifact delete FAILED (tag {tag}) — {type(exc).__name__}; '
            f'the post is still live, delete it manually'
        )
        _emit_url(platform, url)
        _record_live_artifact(platform, tag, url, account_id)
    else:
        _emit(f'\n  {platform} artifact deleted (tag {tag})')


def _emit_url(platform: str, url: str | None) -> None:
    """Report the permalink as its own line, or say plainly that there is none."""
    if url:
        _emit(f'  {platform} artifact URL: {url}')
    else:
        _emit(f'  {platform} artifact URL: none reported — search the account for the tag')
