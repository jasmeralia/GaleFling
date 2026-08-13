"""Unit coverage for the JavaScript the WebView platforms inject.

These methods build a script and hand it to Chromium, so what is worth asserting is the
*content* of that script: the selector it targets, the guard it applies, and the order of
the two. A composer selector that silently stops matching, or a guard that moves after the
action it is meant to gate, is exactly the class of regression the functional suite cannot
catch on a machine with no display and no live session.

They are covered here rather than functionally because none of them need a browser: each
one is a pure string built from the platform's own constants. The live behaviour they
drive is covered by ``tests/functional/``.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.platforms.fansly import FanslyPlatform
from src.platforms.fetlife import FetLifePlatform
from src.platforms.onlyfans import OnlyFansPlatform


class _RecordingPage:
    """Records every script handed to runJavaScript, answering with *reply*."""

    def __init__(self, reply=None):
        self.js_calls: list[str] = []
        self._reply = reply

    def runJavaScript(self, script, callback=None):  # noqa: N802 - mirrors Qt API
        self.js_calls.append(script)
        if callback is not None:
            callback(self._reply)


class _RecordingView:
    def __init__(self, page):
        self._page = page

    def page(self):
        return self._page


class _ScriptCollection:
    """Stands in for QWebEngineScriptCollection."""

    def __init__(self):
        self.inserted: list[object] = []

    def find(self, name):
        return [s for s in self.inserted if getattr(s, 'name', lambda: '')() == name]

    def insert(self, script):
        self.inserted.append(script)


class _ProfileWithScripts:
    def __init__(self):
        self._scripts = _ScriptCollection()

    def scripts(self):
        return self._scripts


def _with_page(platform_cls, account_id, reply=None):
    platform = platform_cls(account_id=account_id)
    page = _RecordingPage(reply)
    platform._view = _RecordingView(page)
    return platform, page


# ── FetLife ─────────────────────────────────────────────────────────────


def test_fetlife_checkbox_fix_is_injected_once_per_profile():
    """Re-injecting on every create_webview() would stack duplicate observers."""
    platform = FetLifePlatform(account_id='fetlife_1')
    platform._profile = _ProfileWithScripts()

    platform._inject_checkbox_fix()
    platform._inject_checkbox_fix()

    assert len(platform._profile.scripts().inserted) == 1


def test_fetlife_checkbox_fix_is_inert_without_a_profile():
    """The profile is absent until create_webview() runs; injection must not raise."""
    platform = FetLifePlatform(account_id='fetlife_1')
    platform._profile = None
    platform._inject_checkbox_fix()


def test_fetlife_avatar_state_reports_without_changing_anything():
    """Reading the avatar checkbox must never toggle it.

    ``picture[is_avatar]`` replaces the account's avatar. The guard that refuses to
    upload when it is checked is only trustworthy if the check itself is read-only.
    """
    platform, page = _with_page(FetLifePlatform, 'fetlife_1', {'present': True, 'checked': False})
    seen: list[dict] = []
    platform._avatar_upload_state(seen.append)

    script = page.js_calls[0]
    assert json.dumps(FetLifePlatform.AVATAR_CHECKBOX_SELECTOR) in script
    assert '.checked = ' not in script, 'the avatar probe must not assign to checked'
    assert 'click()' not in script
    assert seen == [{'present': True, 'checked': False}]


def test_fetlife_avatar_state_without_a_page_reports_unchecked_with_a_reason():
    platform = FetLifePlatform(account_id='fetlife_1')
    platform._view = None
    seen: list[dict] = []
    platform._avatar_upload_state(seen.append)
    assert seen == [{'checked': False, 'reason': 'no WebView page'}]


def test_fetlife_attach_control_is_matched_by_exact_label():
    """A substring match would also hit "Choose Files" or unrelated controls."""
    platform, page = _with_page(FetLifePlatform, 'fetlife_1', {'found': True})
    seen: list[dict] = []
    platform._mark_fetlife_attach_control(seen.append)

    script = page.js_calls[0]
    assert 'data-galefling-media-target' in script
    assert 'removeAttribute' in script, 'a stale marker must be cleared before re-marking'
    assert seen == [{'found': True}]


def test_fetlife_attach_control_without_a_page_reports_failure():
    platform = FetLifePlatform(account_id='fetlife_1')
    platform._view = None
    seen: list[dict] = []
    platform._mark_fetlife_attach_control(seen.append)
    assert seen == [{'found': False, 'reason': 'no WebView page'}]


def test_fetlife_video_caption_also_fills_the_title():
    """A titleless video upload is rejected, so the title is derived from the caption."""
    platform, page = _with_page(FetLifePlatform, 'fetlife_1', {'injected': True})
    platform._image_path = Path('/tmp/clip.mp4')
    platform._inject_media_caption('first line\nsecond line')

    script = page.js_calls[0]
    assert json.dumps(FetLifePlatform.VIDEO_CAPTION_SELECTOR) in script
    assert json.dumps(FetLifePlatform.VIDEO_TITLE_SELECTOR) in script
    # The caption keeps the whole body; the title is only ever the first line.
    assert json.dumps('first line\nsecond line') in script
    assert json.dumps('first line') in script
    assert json.dumps('second line') not in script


def test_fetlife_image_caption_uses_the_image_selector():
    platform, page = _with_page(FetLifePlatform, 'fetlife_1', {'injected': True})
    platform._image_path = Path('/tmp/photo.jpg')
    platform._inject_media_caption('a caption')

    script = page.js_calls[0]
    assert json.dumps(FetLifePlatform.IMAGE_CAPTION_SELECTOR) in script


def test_fetlife_media_caption_is_inert_without_a_view():
    platform = FetLifePlatform(account_id='fetlife_1')
    platform._view = None
    platform._inject_media_caption('text')


def test_fetlife_consent_is_selected_by_exact_name():
    """Ticking every checkbox on the picture form would also tick is_avatar."""
    platform, page = _with_page(FetLifePlatform, 'fetlife_1', {'certified': True})
    platform._certify_upload_consent()

    script = page.js_calls[0]
    assert json.dumps(FetLifePlatform.CONSENT_CHECKBOX_SELECTOR) in script
    assert 'is_avatar' not in script


def test_fetlife_consent_is_inert_without_a_view():
    platform = FetLifePlatform(account_id='fetlife_1')
    platform._view = None
    platform._certify_upload_consent()


def test_fetlife_media_prefill_aborts_without_a_media_path():
    """No path means nothing to attach; the flow must stop before touching the page."""
    platform, page = _with_page(FetLifePlatform, 'fetlife_1')
    platform._image_path = None
    platform._prefill_media()
    assert page.js_calls == []


def test_fetlife_media_prefill_aborts_without_a_view():
    platform = FetLifePlatform(account_id='fetlife_1')
    platform._image_path = Path('/tmp/photo.jpg')
    platform._view = None
    platform._prefill_media()


# ── Fansly ──────────────────────────────────────────────────────────────


def test_fansly_media_prefill_aborts_without_a_media_path():
    platform, page = _with_page(FanslyPlatform, 'fansly_1')
    platform._image_path = None
    platform._prefill_media()
    assert page.js_calls == []


def test_fansly_media_prefill_aborts_without_a_view():
    platform = FanslyPlatform(account_id='fansly_1')
    platform._image_path = Path('/tmp/photo.jpg')
    platform._view = None
    platform._prefill_media()


def test_fansly_upload_marker_clears_a_stale_marker_first():
    """A marker left from a previous attempt would aim the click at a dead element."""
    platform, page = _with_page(FanslyPlatform, 'fansly_1', {'found': True})
    seen: list[dict] = []
    platform._mark_fansly_upload_new(seen.append)

    script = page.js_calls[0]
    assert 'removeAttribute' in script
    assert seen == [{'found': True}]


def test_fansly_upload_modal_state_is_read_only():
    platform, page = _with_page(FanslyPlatform, 'fansly_1', {'open': False})
    seen: list[dict] = []
    platform._fansly_upload_modal_state(seen.append)

    script = page.js_calls[0]
    assert 'click()' not in script, 'a state probe must not act on the page'
    assert seen == [{'open': False}]


def test_fansly_post_control_state_is_read_only():
    platform, page = _with_page(FanslyPlatform, 'fansly_1', {'enabled': False})
    seen: list[dict] = []
    platform._fansly_post_control_state(seen.append)

    assert 'click()' not in page.js_calls[0]
    assert seen == [{'enabled': False}]


def test_fansly_composer_media_state_is_read_only():
    platform, page = _with_page(FanslyPlatform, 'fansly_1', {'attached': 0})
    seen: list[dict] = []
    platform._fansly_composer_media_state(seen.append)

    assert 'click()' not in page.js_calls[0]
    assert seen == [{'attached': 0}]


def test_fansly_javascript_helper_reports_a_missing_page():
    """Every Fansly probe funnels through here, so its no-page path is load-bearing.

    It reports ``found: False`` with a reason rather than raising or staying silent, so a
    caller waiting on the callback is not left hanging when the view has gone away.
    """
    platform = FanslyPlatform(account_id='fansly_1')
    platform._view = None
    seen: list[dict] = []
    platform._run_fansly_javascript('1;', seen.append)
    assert seen == [{'found': False, 'reason': 'no WebView page'}]


# ── OnlyFans ────────────────────────────────────────────────────────────


def test_onlyfans_checkbox_fix_is_injected_once_per_profile():
    platform = OnlyFansPlatform(account_id='onlyfans_1')
    platform._profile = _ProfileWithScripts()

    platform._inject_2fa_checkbox_fix()
    platform._inject_2fa_checkbox_fix()

    assert len(platform._profile.scripts().inserted) == 1


def test_onlyfans_checkbox_fix_is_inert_without_a_profile():
    platform = OnlyFansPlatform(account_id='onlyfans_1')
    platform._profile = None
    platform._inject_2fa_checkbox_fix()


def test_onlyfans_checkbox_fix_writes_through_the_prototype_setter():
    """Vue owns the instance property; a direct assignment is reverted on re-render.

    The script has to use the prototype setter and then dispatch input+change, or the
    checkbox visually toggles and the framework never records it.
    """
    platform = OnlyFansPlatform(account_id='onlyfans_1')
    platform._profile = _ProfileWithScripts()
    platform._inject_2fa_checkbox_fix()

    source = platform._profile.scripts().inserted[0].sourceCode()
    assert 'getOwnPropertyDescriptor' in source
    assert 'HTMLInputElement.prototype' in source
    assert "dispatchEvent(new Event('input'" in source
    assert "dispatchEvent(new Event('change'" in source
