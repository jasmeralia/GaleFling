"""Functional test for the trusted-click primitive that makes media upload possible.

Runs entirely against a local ``setHtml`` page — **no credentials and no live site**,
so it guards the mechanism on every functional run rather than only when a platform
session happens to be valid.

Chromium refuses to open a file picker without user activation, and JavaScript cannot
grant it. Composers hide their file inputs, so the gesture has to land on a visible
control. ``BaseWebViewPlatform.trusted_click()`` supplies it with a synthesised
``QMouseEvent``; this proves the whole chain end to end — gesture, activation, and the
picker actually receiving the staged path.

The negative case is the point. Without a prior gesture the JS still runs to completion
and Chromium swallows the refused click silently, so "the call returned" is not evidence
of anything. Both directions are asserted here for that reason.

Verified on both hosts 2026-08-12: Linux (xcb under Xvfb) and the Windows 11 VM, the
latter GPU-less. Needing no credentials is what makes running it on Windows cheap, and
Windows is where it actually has to hold.
"""

from __future__ import annotations

import pytest

from tests.functional.webview_helpers import (
    call_platform,
    close_webview,
    create_webview,
    get_or_create_app,
    run_js,
    wait_ms,
)

ACCOUNT_ID = 'fetlife_1'

# A visible control to click, and a hidden file input mirroring how real composers
# present theirs (`display:none`, no dimensions, nothing to aim at).
PROBE_HTML = """
<html><body style="margin:0">
<div id="attach" style="position:absolute;left:10px;top:10px;width:300px;height:120px;
background:#ccc">attach control</div>
<input id="pick" type="file" accept="image/*" style="display:none">
</body></html>
"""


def _load_probe(page) -> None:
    page.setHtml(PROBE_HTML)
    wait_ms(2500)


@pytest.mark.functional
@pytest.mark.non_mutating
class TestTrustedClickGrantsUserActivation:
    """The mechanism every WebView media upload depends on."""

    def test_picker_is_refused_without_a_trusted_gesture(self, galefling_data_dir, tmp_path):
        """No gesture must mean no picker — and must be *reported* as no picker.

        This is the regression that matters. Chromium logs "File chooser dialog can only
        be shown with a user activation" and drops the click; nothing observable from
        JavaScript changes. Before ``open_media_picker()`` grew its activation guard it
        returned ``opened: true`` here while the picker never fired.
        """
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            media = tmp_path / 'photo.jpg'
            media.write_bytes(b'\xff\xd8\xff\xe0stub')
            _load_probe(page)

            platform.stage_media_for_picker(media)
            before = platform.picker_invocations
            result = call_platform(platform.open_media_picker, media)

            wait_ms(800)
            assert platform.picker_invocations == before, (
                'Chromium opened a picker with no user activation — the premise of '
                'trusted_click() no longer holds and the media flow needs rechecking'
            )
            assert not result.get('opened'), (
                f'open_media_picker() reported success while the picker never fired: {result}'
            )
            assert result.get('userActivationActive') is False, f'{result}'
        finally:
            close_webview(view, page, platform)

    def test_trusted_click_grants_activation_and_opens_the_picker(
        self, galefling_data_dir, tmp_path
    ):
        """The positive path: gesture -> activation -> picker receives the staged file."""
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            media = tmp_path / 'photo.jpg'
            media.write_bytes(b'\xff\xd8\xff\xe0stub')
            _load_probe(page)

            clicked = call_platform(platform.trusted_click, '#attach')
            assert clicked.get('clicked'), f'trusted_click() found no target: {clicked}'
            wait_ms(400)

            active = run_js(
                page, '!!(navigator.userActivation && navigator.userActivation.isActive)'
            )
            assert active, (
                'A synthesised QMouseEvent did not grant user activation. Shipped media '
                'upload depends on this; see BaseWebViewPlatform.trusted_click().'
            )

            platform.stage_media_for_picker(media)
            before = platform.picker_invocations
            opened = call_platform(platform.open_media_picker, media)
            wait_ms(800)

            assert opened.get('opened'), f'Picker refused after a trusted click: {opened}'
            assert platform.picker_invocations == before + 1, (
                f'chooseFiles() never fired: {platform.picker_invocations} vs {before}'
            )
        finally:
            close_webview(view, page, platform)

    def test_hidden_elements_are_refused_rather_than_clicked_blind(self, galefling_data_dir):
        """A hidden input has no coordinates; a click at (0, 0) would land elsewhere.

        Composers hide their file inputs, so this is the realistic mistake — aiming the
        gesture at the input itself instead of at a visible control.
        """
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _load_probe(page)
            result = call_platform(platform.trusted_click, '#pick')
            assert not result.get('clicked'), f'trusted_click() clicked a hidden element: {result}'
            assert result.get('reason') == 'no visible element', f'{result}'
        finally:
            close_webview(view, page, platform)
