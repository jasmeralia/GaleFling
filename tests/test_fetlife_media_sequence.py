"""Unit coverage for FetLife's media pre-fill step sequence.

The sequence is ordered for safety, not just convenience: the avatar guard runs *first*,
before anything is staged or clicked, because ``picture[is_avatar]`` on FetLife's picture
composer replaces the account's avatar. A run that attached media before checking it could
not undo that. These tests pin the ordering and the abort, which is the part no functional
run against a live account should ever be used to discover.

Each step is exercised through the real ``_run_media_sequence()`` sequencer; only the
browser-facing leaves are substituted.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.platforms.fetlife import FetLifePlatform


class _Page:
    def runJavaScript(self, script, callback=None):  # noqa: N802 - mirrors Qt API
        if callback is not None:
            callback({})


class _View:
    def __init__(self, page):
        self._page = page

    def page(self):
        return self._page


def _platform(text='a caption', suffix='.jpg'):
    platform = FetLifePlatform(account_id='fetlife_1')
    platform._view = _View(_Page())
    platform._image_path = Path(f'/tmp/media{suffix}')
    platform._text = text
    return platform


def _wire(platform, monkeypatch, *, avatar_checked=False, calls=None):
    """Substitute the browser-facing leaves, recording the order they run in."""
    calls = calls if calls is not None else []

    def avatar_state(callback):
        calls.append('avatar')
        callback({'present': True, 'checked': avatar_checked})

    def activate(_selector, _path, callback):
        calls.append('attach')
        callback(True, '', {'opened': True})

    def poll(probe, predicate, _timeout, _reason, done):
        calls.append('poll')
        done(True, '', {'found': True, 'attached': True})

    def caption(_text, callback=None):
        calls.append('caption')
        if callback:
            callback({'caption': True, 'title': True})

    def certify(callback=None):
        calls.append('certify')
        if callback:
            callback({'certified': True})

    monkeypatch.setattr(platform, '_avatar_upload_state', avatar_state)
    monkeypatch.setattr(platform, '_activate_staged_media_picker', activate)
    monkeypatch.setattr(platform, '_poll_media_step', poll)
    monkeypatch.setattr(platform, '_inject_media_caption', caption)
    monkeypatch.setattr(platform, '_certify_upload_consent', certify)
    return calls


def test_media_prefill_runs_every_step_in_order(monkeypatch):
    platform = _platform()
    calls = _wire(platform, monkeypatch)

    platform._prefill_media()

    assert calls[0] == 'avatar', 'the avatar guard must run before anything else'
    assert 'attach' in calls
    assert 'caption' in calls
    assert 'certify' in calls
    assert calls.index('caption') < calls.index('certify')


def test_media_prefill_refuses_when_the_avatar_checkbox_is_ticked(monkeypatch):
    """Refusing here is what protects the account's avatar from being replaced."""
    platform = _platform()
    calls = _wire(platform, monkeypatch, avatar_checked=True)

    platform._prefill_media()

    assert calls == ['avatar'], f'the sequence continued past the avatar guard: {calls}'


def test_media_prefill_aborts_when_the_avatar_state_is_unreadable(monkeypatch):
    """An uninspectable checkbox is treated as unsafe, not as unchecked."""
    platform = _platform()
    calls: list[str] = []
    _wire(platform, monkeypatch, calls=calls)
    monkeypatch.setattr(
        platform,
        '_avatar_upload_state',
        lambda callback: (calls.append('avatar'), callback(None))[0],
    )

    platform._prefill_media()

    assert calls == ['avatar']


def test_media_prefill_stages_the_file_for_the_picker(monkeypatch):
    """chooseFiles() can only answer with something that was staged first."""
    platform = _platform()
    _wire(platform, monkeypatch)

    platform._prefill_media()

    # The staged selection is consumed by the picker; taking it proves it was queued.
    assert platform.take_staged_picker_files() == [str(platform._image_path)]


@pytest.mark.parametrize('suffix', ['.mp4', '.jpg'])
def test_media_prefill_handles_both_media_kinds(monkeypatch, suffix):
    """Video additionally requires a title, so the caption step branches on extension."""
    platform = _platform(suffix=suffix)
    calls = _wire(platform, monkeypatch)

    platform._prefill_media()

    assert 'caption' in calls and 'certify' in calls
