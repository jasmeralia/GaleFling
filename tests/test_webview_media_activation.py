"""Unit coverage for the media-picker activation sequence and its guard branches.

``_activate_staged_media_picker()`` is the step that turns a trusted gesture into a file
actually reaching a composer, and almost all of its logic is failure handling: a control
that would not click, a picker that reported open but never fired, a platform that opts
out of the hidden-input fallback. Those branches decide whether a broken upload is
reported as broken or silently passes, which is the whole reason the method reports rather
than assumes — so they are worth asserting directly.

None of this needs a browser. The Qt seam is ``QTimer.singleShot``, replaced here with an
immediate call so the callback ordering is deterministic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.platforms import base_webview
from src.platforms.base_webview import BaseWebViewPlatform
from src.platforms.fansly import FanslyPlatform


class _ImmediateTimer:
    """Runs deferred callbacks inline, so ordering is deterministic under test."""

    @staticmethod
    def singleShot(_ms, fn):  # noqa: N802 - mirrors Qt API
        fn()


class _Page:
    def __init__(self, replies=None):
        self.js_calls: list[str] = []
        self._replies = list(replies or [])

    def runJavaScript(self, script, callback=None):  # noqa: N802 - mirrors Qt API
        self.js_calls.append(script)
        if callback is not None:
            callback(self._replies.pop(0) if self._replies else None)


class _View:
    def __init__(self, page):
        self._page = page
        self.focus_proxy = None

    def page(self):
        return self._page

    def focusProxy(self):  # noqa: N802 - mirrors Qt API
        return self.focus_proxy


@pytest.fixture(autouse=True)
def _immediate_timers(monkeypatch):
    monkeypatch.setattr(base_webview, 'QTimer', _ImmediateTimer)


def _platform(replies=None):
    platform = FanslyPlatform(account_id='fansly_1')
    page = _Page(replies)
    platform._view = _View(page)
    return platform, page


def _capture():
    seen: list[tuple[bool, str, object]] = []

    def callback(ok, reason, detail):
        seen.append((ok, reason, detail))

    return seen, callback


def test_activation_reports_a_control_that_would_not_click(monkeypatch):
    """An unclickable attach control must end the sequence, not fall through to the input."""
    platform, _page = _platform([{'found': False, 'tried': ['#attach']}])
    monkeypatch.setattr(platform, '_send_trusted_click', lambda *_: None)
    seen, callback = _capture()

    platform._activate_staged_media_picker('#attach', Path('/tmp/photo.jpg'), callback)

    assert len(seen) == 1
    ok, reason, _detail = seen[0]
    assert ok is False
    assert reason == 'no visible element'


def test_activation_succeeds_when_the_visible_control_opens_the_picker(monkeypatch):
    """Many attach controls open the picker themselves; no second click should follow."""
    platform, _page = _platform([{'found': True, 'x': 5, 'y': 6, 'selector': '#attach'}])
    seen, callback = _capture()

    # The counter has to move *during* the click, not before it: the sequence records a
    # baseline first, so a bump that happens earlier is invisible to it — which is exactly
    # how the real page behaves when its own handler fires chooseFiles() on the gesture.
    def click_opens_the_picker(*_args):
        platform.take_staged_picker_files()

    monkeypatch.setattr(platform, '_send_trusted_click', click_opens_the_picker)

    platform._activate_staged_media_picker('#attach', Path('/tmp/photo.jpg'), callback)

    assert len(seen) == 1
    ok, _reason, detail = seen[0]
    assert ok is True
    assert detail['via'] == 'visible control'


def test_activation_refuses_to_open_the_hidden_input_when_told_not_to(monkeypatch):
    """fallback_to_input=False means a silent control is a failure, not a retry."""
    platform, _page = _platform([{'found': True, 'x': 1, 'y': 2, 'selector': '#attach'}])
    monkeypatch.setattr(platform, '_send_trusted_click', lambda *_: None)
    seen, callback = _capture()

    platform._activate_staged_media_picker(
        '#attach', Path('/tmp/photo.jpg'), callback, fallback_to_input=False
    )

    assert len(seen) == 1
    ok, reason, _detail = seen[0]
    assert ok is False
    assert 'did not open' in reason


def test_activation_reports_a_picker_that_refused_to_open(monkeypatch):
    """An activation refusal is final — retrying only produces another silent no-op."""
    platform, _page = _platform(
        [
            {'found': True, 'x': 1, 'y': 2, 'selector': '#attach'},
            {'opened': False, 'reason': 'no user activation — call trusted_click() first'},
        ]
    )
    monkeypatch.setattr(platform, '_send_trusted_click', lambda *_: None)
    seen, callback = _capture()

    platform._activate_staged_media_picker('#attach', Path('/tmp/photo.jpg'), callback)

    assert len(seen) == 1
    ok, reason, _detail = seen[0]
    assert ok is False
    assert 'no user activation' in reason


def test_activation_rejects_a_picker_that_reported_open_but_never_fired(monkeypatch):
    """The regression this whole reporting path exists for.

    Chromium swallows a refused click, so ``opened: true`` alone is not evidence. Only
    ``chooseFiles()`` actually being called is, and that is what picker_invocations counts.
    """
    platform, _page = _platform(
        [
            {'found': True, 'x': 1, 'y': 2, 'selector': '#attach'},
            {'opened': True, 'userActivationActive': True},
        ]
    )
    monkeypatch.setattr(platform, '_send_trusted_click', lambda *_: None)
    seen, callback = _capture()

    platform._activate_staged_media_picker('#attach', Path('/tmp/photo.jpg'), callback)

    assert len(seen) == 1
    ok, reason, _detail = seen[0]
    assert ok is False
    assert 'chooseFiles() was not called' in reason


# ── Guard branches on the primitives themselves ─────────────────────────


def test_trusted_click_without_a_view_reports_rather_than_raising():
    platform = FanslyPlatform(account_id='fansly_1')
    platform._view = None
    seen: list[dict] = []
    platform.trusted_click('#anything', callback=seen.append)
    assert seen == [{'clicked': False, 'reason': 'no webview'}]


def test_trusted_click_without_a_page_reports_rather_than_raising():
    platform = FanslyPlatform(account_id='fansly_1')
    platform._view = _View(None)
    seen: list[dict] = []
    platform.trusted_click('#anything', callback=seen.append)
    assert seen == [{'clicked': False, 'reason': 'no page'}]


def test_trusted_click_reports_a_disabled_control_distinctly():
    """A disabled control is not the same failure as a missing one.

    Fansly's Post control expresses disabled state as a class rather than the DOM
    property, so conflating the two would read as "the button isn't there".
    """
    platform, _page = _platform([{'found': True, 'disabled': True, 'selector': '#post'}])
    seen: list[dict] = []
    platform.trusted_click('#post', callback=seen.append)
    assert seen == [{'clicked': False, 'reason': 'control disabled', 'selector': '#post'}]


def test_send_trusted_click_is_inert_without_a_view():
    platform = FanslyPlatform(account_id='fansly_1')
    platform._view = None
    platform._send_trusted_click(1, 2)


def test_open_media_picker_is_inert_without_a_view():
    platform = FanslyPlatform(account_id='fansly_1')
    platform._view = None
    platform.open_media_picker(Path('/tmp/photo.jpg'))


def test_inject_text_reports_a_missing_view_or_selector():
    platform = FanslyPlatform(account_id='fansly_1')
    platform._view = None
    seen: list[dict] = []
    platform._inject_text('hello', callback=seen.append)
    assert seen == [{'injected': False, 'reason': 'no webview or text selector'}]


def test_inject_text_reports_a_missing_page():
    platform = FanslyPlatform(account_id='fansly_1')
    platform._view = _View(None)
    seen: list[dict] = []
    platform._inject_text('hello', callback=seen.append)
    assert seen == [{'injected': False, 'reason': 'no page'}]


# ── Small pure helpers ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ('label', 'expected'),
    [
        ('NavigationTypeLinkClicked', 'user-click'),
        ('NavigationTypeFormSubmitted', 'form-submit'),
        ('NavigationTypeBackForward', 'history-navigation'),
        ('NavigationTypeReload', 'reload'),
        ('NavigationTypeTyped', 'typed-or-programmatic'),
        ('NavigationTypeOther', 'other-or-redirect'),
        ('NavigationTypeSomethingNew', 'unknown'),
    ],
)
def test_navigation_source_labels(label, expected):
    """Navigation provenance is how a redirect is told apart from a user's own click."""
    assert BaseWebViewPlatform._navigation_source(label) == expected


def test_enum_label_falls_back_when_there_is_no_name():
    """Qt enums normally carry .name; ints and odd values must still render."""

    class _Named:
        name = 'NavigationTypeReload'

    assert BaseWebViewPlatform._enum_label(_Named()) == 'NavigationTypeReload'
    assert BaseWebViewPlatform._enum_label(3) == '3'
    assert BaseWebViewPlatform._enum_label(None) == 'None'
