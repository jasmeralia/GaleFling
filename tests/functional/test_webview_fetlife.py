"""Functional tests for FetLife WebView posting.

Exercises the shipped ``FetLifePlatform`` adapter for text, picture, and video
composers: ``_inject_text()``, ``_attach_media()``, and ``_certify_upload_consent()``.

**Media upload:** attach is covered non-mutatingly — the file is loaded into the
composer form and the Upload button is never clicked. Mutating submit tests stay
disabled until media upload is wired into the post flow (task #417 Level B).
``_certify_upload_consent()`` selects the certification field by exact name, so
``picture[is_avatar]`` can never be toggled; the attach test asserts that directly.
"""

from __future__ import annotations

import json
import re

import pytest

from src.platforms.fetlife import FetLifePlatform
from tests.functional.conftest import fail_or_skip, mutating_post_tag, mutating_post_text
from tests.functional.webview_helpers import (
    _CONFIRM_DELETE_JS,
    attempt_delete_current_post,
    close_webview,
    create_webview,
    get_or_create_app,
    has_cookie_db,
    load_page,
    login_fetlife,
    run_js,
    wait_ms,
)

ACCOUNT_ID = 'fetlife_1'
TEXT_COMPOSER_URL = FetLifePlatform.TEXT_COMPOSER_URL
IMAGE_COMPOSER_URL = FetLifePlatform.IMAGE_COMPOSER_URL
VIDEO_COMPOSER_URL = FetLifePlatform.VIDEO_COMPOSER_URL
PICTURE_FILE_SELECTOR = FetLifePlatform.IMAGE_FILE_SELECTOR
VIDEO_FILE_SELECTOR = FetLifePlatform.VIDEO_FILE_SELECTOR

# FetLife permalinks are username-scoped (/<username>/pictures/<id>, /<username>/s/<id>).
POST_URL_PATTERN = re.compile(FetLifePlatform.SUCCESS_URL_PATTERN, re.IGNORECASE)


def _maybe_later_prompt_present(page) -> bool:
    """Whether FetLife's recurring "Maybe later" prompt is still on screen.

    The prompt is dismissed by shipped code — ``dismissMaybeLater()`` inside
    ``FetLifePlatform._inject_checkbox_fix()``, driven by a MutationObserver. Tests
    therefore *observe* it rather than dismissing it themselves: a test-side dismissal
    would keep passing even if the shipped one broke, which is the defect class Phase 5
    exists to catch.
    """
    return bool(
        run_js(
            page,
            """
            (function() {
                return Array.from(
                    document.querySelectorAll('button, a, [role="button"]')
                ).some(function(el) {
                    if ((el.textContent || '').trim().toLowerCase() !== 'maybe later') {
                        return false;
                    }
                    var style = window.getComputedStyle(el);
                    return style.display !== 'none' && style.visibility !== 'hidden';
                });
            })();
            """,
        )
    )


def _read_status_text(page) -> dict:
    """Read the status composer textarea after platform text injection."""
    return run_js(
        page,
        f"""
        (function() {{
            var box = document.querySelector({json.dumps(FetLifePlatform.TEXT_SELECTOR)});
            if (!box) return {{found: false}};
            var say = Array.from(document.querySelectorAll('button, input[type="submit"]'))
                .find(function(b) {{
                    return ((b.textContent || b.value || '').trim()
                        === {json.dumps(FetLifePlatform.TEXT_SUBMIT_LABEL)});
                }});
            return {{
                found: true,
                content: box.value.substring(0, 200),
                submitFound: !!say,
                submitDisabled: say ? !!say.disabled : null
            }};
        }})();
        """,
    )


def _status_exists_in_feed(page, tag: str) -> dict:
    """Whether a status carrying *tag* is present on the current page."""
    return run_js(
        page,
        f"""
        (function() {{
            var body = document.body ? document.body.innerText : '';
            var idx = body.indexOf({json.dumps(tag)});
            return {{
                found: idx !== -1,
                url: location.href,
                context: idx === -1 ? null
                    : body.substring(Math.max(0, idx - 60), idx + 60)
            }};
        }})();
        """,
        timeout_ms=10000,
    )


def _ensure_session(page, credentials: dict) -> None:
    """Verify we have a valid FetLife session, logging in if needed."""
    ok, final_url = load_page(page, TEXT_COMPOSER_URL, timeout_ms=20000)
    if not ok:
        wait_ms(2000)
        ok, final_url = load_page(page, TEXT_COMPOSER_URL, timeout_ms=20000)
    if not ok:
        fail_or_skip(f'FetLife page load failed: {final_url}')

    if '/login' in final_url.lower():
        success = login_fetlife(page, credentials['email'], credentials['password'])
        if not success:
            fail_or_skip('FetLife login failed — check credentials in .env')
        ok, final_url = load_page(page, TEXT_COMPOSER_URL, timeout_ms=20000)
        if not ok or '/login' in final_url.lower():
            fail_or_skip('FetLife composer unreachable after login')
    wait_ms(1000)  # let the shipped MutationObserver dismiss the recurring prompt
    assert not _maybe_later_prompt_present(page), (
        'FetLife "Maybe later" prompt is still showing — the shipped '
        'dismissMaybeLater() in FetLifePlatform._inject_checkbox_fix() did not fire'
    )


def _call_platform(method, *args, timeout_ms: int = 20000) -> dict:
    """Call a platform method whose result arrives via an async runJavaScript callback."""
    state: dict = {'done': False, 'value': None}

    def callback(value):
        state['done'] = True
        state['value'] = value

    method(*args, callback=callback)

    elapsed = 0
    while not state['done'] and elapsed < timeout_ms:
        wait_ms(100)
        elapsed += 100

    value = state['value']
    if isinstance(value, dict):
        return value
    return {'timed_out': not state['done'], 'raw': value}


def _wait_for_attachment(platform, timeout_ms: int = 15000) -> dict:
    """Poll until the upload form reports a file, or the timeout expires.

    FetLife's picture composer moves the file from the picker to the hidden
    ``picture[attachments][]`` field asynchronously, so acceptance cannot be read
    back synchronously from the attach call.
    """
    elapsed = 0
    state: dict = {}
    while elapsed < timeout_ms:
        state = _call_platform(platform._media_attachment_state)
        if state.get('attached'):
            return state
        wait_ms(500)
        elapsed += 500
    return state


def _composer_elements(page, file_selector: str, submit_label: str) -> dict:
    """Report the file input and upload button on an open upload composer."""
    return run_js(
        page,
        f"""
        (function() {{
            var fileInput = document.querySelector({json.dumps(file_selector)});
            var submitBtn = Array.from(
                document.querySelectorAll('button[type="submit"]')
            ).find(function(b) {{
                return b.textContent.includes({json.dumps(submit_label)});
            }});
            return {{
                fileInputFound: !!fileInput,
                fileInputAccept: fileInput ? fileInput.accept : null,
                submitFound: !!submitBtn,
                submitDisabled: submitBtn ? submitBtn.disabled : null
            }};
        }})();
        """,
    )


def _upload_form_state(page, composer_path: str) -> dict:
    """Report where an attached file landed and whether any side-effect box was set."""
    return run_js(
        page,
        f"""
        (function() {{
            var named = document.querySelector(
                'input[type="file"][name="picture[attachments][]"]'
            );
            var avatar = document.querySelector(
                'input[type="checkbox"][name="picture[is_avatar]"]'
            );
            var total = 0;
            document.querySelectorAll('input[type="file"]').forEach(function(el) {{
                if (el.files) total += el.files.length;
            }});
            return {{
                stillOnComposer: window.location.href.includes({json.dumps(composer_path)}),
                totalFiles: total,
                namedFieldFiles: named && named.files ? named.files.length : 0,
                avatarChecked: avatar ? avatar.checked : false
            }};
        }})();
        """,
    )


def _delete_status_by_tag(page, tag: str) -> dict:
    """Delete the feed status carrying *tag* via its own dropdown Delete entry.

    Scoped to the ``<article>`` that owns the tag, so no other status can be removed.
    The tag text sits in a leaf ``<p>`` several levels below the article, and only the
    article carries the controls — walking to the *deepest* node containing the tag
    finds an element with no controls at all.

    **This does not currently work, and the test reports that honestly.** Investigated
    against a live status on 2026-08-11: the Delete entry is an ``<a href="#0">`` whose
    only payload is a ``data`` attribute that stringifies to ``[object Object]`` — no
    ``data-method``, no ``data-turbo-confirm``, no delete endpoint, and the status
    permalink page (``/<username>/s/<id>``) offers the same control rather than a form.
    The handler is bound in JavaScript, so a synthetic ``.click()`` never reaches it and
    no confirmation dialog is raised.

    Automating it needs a *trusted* click — ``QTest.mouseClick`` at the element's
    viewport coordinates, opening the "More options" dropdown first. That is exactly the
    pattern ``docs/testing/WEBVIEW_TEST_PLAN.md`` Phase 6 prescribes for telling "our JS
    set the property" apart from "a user's click reached the control", and is the right
    next step. Until then, mutating runs leave a status behind and print its tag.
    """
    run_js(page, 'window.confirm = function() { return true; };')
    clicked = run_js(
        page,
        f"""
        (function() {{
            var leaf = Array.from(document.querySelectorAll('*')).filter(function(el) {{
                return el.children.length === 0
                    && (el.textContent || '').indexOf({json.dumps(tag)}) !== -1;
            }})[0];
            if (!leaf) return {{clicked: false, reason: 'status not on page'}};
            var host = leaf.closest('article');
            if (!host) return {{clicked: false, reason: 'no article ancestor for the status'}};
            var del = Array.from(host.querySelectorAll('a, button, [role="button"]')).find(
                function(c) {{ return (c.textContent || '').trim().toLowerCase() === 'delete'; }}
            );
            if (!del) return {{clicked: false, reason: 'no Delete entry in the article'}};
            del.click();
            return {{clicked: true}};
        }})();
        """,
    )
    if not (isinstance(clicked, dict) and clicked.get('clicked')):
        return {'deleted': False, 'detail': clicked}

    wait_ms(2000)
    confirm = run_js(page, _CONFIRM_DELETE_JS)
    wait_ms(2500)

    # Only the status leaving the feed counts as deleted.
    load_page(page, TEXT_COMPOSER_URL, timeout_ms=20000)
    wait_ms(3000)
    gone = not _status_exists_in_feed(page, tag).get('found')
    return {'deleted': gone, 'confirm': confirm}


def _own_profile_href(page) -> str | None:
    """Resolve the logged-in account's profile path (e.g. /Jasmeralia)."""
    return run_js(
        page,
        """
        (function() {
            var a = Array.from(document.querySelectorAll('a[href^="/"]')).find(function(x) {
                return /view profile/i.test(x.textContent || '');
            });
            return a ? a.getAttribute('href').split('?')[0] : null;
        })();
        """,
        timeout_ms=10000,
    )


def _wait_for_media_in_gallery(page, kind: str, tag: str, timeout_ms: int = 180000) -> dict:
    """Poll the account's own gallery until media carrying *tag* appears.

    Uploads are asynchronous — FetLife stays on the composer while the file transfers
    and transcodes — so the composer URL never changes and cannot signal success.
    """
    profile = _own_profile_href(page)
    if not profile:
        load_page(page, TEXT_COMPOSER_URL, timeout_ms=20000)
        wait_ms(2500)
        profile = _own_profile_href(page)
    if not profile:
        return {'found': False, 'reason': 'could not resolve own profile path'}

    gallery = f'https://fetlife.com{profile}/{kind}'
    elapsed = 0
    while elapsed <= timeout_ms:
        load_page(page, gallery, timeout_ms=25000)
        wait_ms(3000)
        hit = _status_exists_in_feed(page, tag)
        if hit.get('found'):
            return {'found': True, 'gallery': gallery, 'context': hit.get('context')}
        wait_ms(7000)
        elapsed += 10000
    return {'found': False, 'gallery': gallery, 'waited_ms': elapsed}


def _wait_for_enabled_submit(page, label: str, timeout_ms: int = 60000) -> dict:
    """Poll until an exactly-labelled submit button is enabled, then click it.

    Both upload buttons start disabled and enable only once the form is satisfied
    (file attached, consent certified), so clicking immediately does nothing.
    """
    elapsed = 0
    status: dict = {}
    while elapsed <= timeout_ms:
        status = run_js(
            page,
            f"""
            (function() {{
                var btn = Array.from(document.querySelectorAll(
                    'button[type="submit"], input[type="submit"]'
                )).find(function(b) {{
                    return (b.textContent || b.value || '').trim()
                        .indexOf({json.dumps(label)}) === 0;
                }});
                return {{
                    found: !!btn,
                    disabled: btn ? !!btn.disabled : null
                }};
            }})();
            """,
        )
        if isinstance(status, dict) and status.get('found') and not status.get('disabled'):
            return _click_submit_button(page, label)
        wait_ms(1500)
        elapsed += 1500
    return {'clicked': False, 'reason': 'submit stayed disabled', 'detail': status}


def _avatar_checkbox_state(page) -> dict:
    """Report picture[is_avatar] — it must never be set by GaleFling or its tests."""
    return run_js(
        page,
        f"""
        (function() {{
            var cb = document.querySelector({json.dumps(FetLifePlatform.AVATAR_CHECKBOX_SELECTOR)});
            return {{present: !!cb, checked: cb ? !!cb.checked : false}};
        }})();
        """,
    )


def _click_submit_button(page, label_fragments: str | list[str]) -> dict:
    """Click a submit control matching one of *label_fragments* (case-insensitive)."""
    if isinstance(label_fragments, str):
        fragments = [label_fragments]
    else:
        fragments = label_fragments
    return run_js(
        page,
        f"""
        (function() {{
            var needles = {json.dumps([f.lower() for f in fragments])};
            var controls = Array.from(document.querySelectorAll(
                'button[type="submit"], input[type="submit"], button, [role="button"]'
            ));
            var btn = controls.find(function(el) {{
                var label = (el.textContent || el.value || '').trim().toLowerCase();
                return needles.some(function(needle) {{ return label.includes(needle); }});
            }});
            if (!btn) {{
                return {{
                    clicked: false,
                    reason: 'Button not found',
                    labels: controls.slice(0, 8).map(function(el) {{
                        return (el.textContent || el.value || '').trim();
                    }}).filter(Boolean)
                }};
            }}
            if (btn.disabled) return {{clicked: false, reason: 'Button disabled'}};
            btn.click();
            return {{
                clicked: true,
                label: (btn.textContent || btn.value || '').trim()
            }};
        }})();
        """,
    )


@pytest.mark.functional
@pytest.mark.non_mutating
class TestFetLifeConnection:
    """Session and platform adapter checks — fail fast before posting tests."""

    def test_has_valid_session(self, galefling_data_dir):
        """Cookie database must exist and pass has_valid_session()."""
        if not has_cookie_db(galefling_data_dir, ACCOUNT_ID):
            pytest.skip('No FetLife cookie database — log in via Settings first')
        platform = FetLifePlatform(account_id=ACCOUNT_ID)
        assert platform.has_valid_session(), 'FetLife session invalid or expired'

    def test_authenticate(self, galefling_data_dir):
        """WebView platforms report authenticate() success when cookies exist."""
        if not has_cookie_db(galefling_data_dir, ACCOUNT_ID):
            pytest.skip('No FetLife cookie database')
        platform = FetLifePlatform(account_id=ACCOUNT_ID)
        ok, err = platform.authenticate()
        assert ok, f'authenticate() failed: {err}'
        assert err is None

    def test_connection(self, galefling_data_dir, fetlife_credentials):
        """Platform test_connection() after loading the shared WebView profile."""
        if not has_cookie_db(galefling_data_dir, ACCOUNT_ID):
            pytest.skip('No FetLife cookie database')
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            ok, err = platform.test_connection()
            if not ok and err == 'WV-SESSION-EXPIRED':
                _ensure_session(page, fetlife_credentials)
                ok, err = platform.test_connection()
            assert ok, f'test_connection() failed: {err}'
            assert err is None
        finally:
            close_webview(view, page, platform)

    def test_composer_url_routing(self, tmp_path):
        """get_composer_url() must route text, image, and video composers."""
        platform = FetLifePlatform(account_id=ACCOUNT_ID)
        assert platform.get_composer_url() == TEXT_COMPOSER_URL

        platform._image_path = tmp_path / 'photo.jpg'
        assert platform.get_composer_url() == IMAGE_COMPOSER_URL

        platform._image_path = tmp_path / 'clip.mp4'
        assert platform.get_composer_url() == VIDEO_COMPOSER_URL


@pytest.mark.functional
class TestFetLifeTextPost:
    """FetLife text post via FetLifePlatform._inject_text()."""

    @pytest.mark.non_mutating
    def test_composer_loads(self, galefling_data_dir, fetlife_credentials):
        """Verify the text composer page loads in an authenticated state."""
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fetlife_credentials)
            final_url = page.url().toString()
            assert '/login' not in final_url.lower(), f'Redirected to login: {final_url}'

            composer = _read_status_text(page)
            assert composer.get('found'), f'Status composer textarea not found: {composer}'
            assert composer.get('submitFound'), (
                f'"{FetLifePlatform.TEXT_SUBMIT_LABEL}" button not found: {composer}'
            )
        finally:
            close_webview(view, page, platform)

    @pytest.mark.non_mutating
    def test_text_injection_via_platform(self, galefling_data_dir, fetlife_credentials):
        """Verify FetLifePlatform._inject_text() fills the Lexxy editor."""
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fetlife_credentials)
            wait_ms(2000)

            test_text = mutating_post_tag()
            platform._inject_text(test_text)
            wait_ms(500)

            result = _read_status_text(page)
            assert isinstance(result, dict), f'JS returned: {result}'
            assert result.get('found'), 'Lexxy editor not found'
            assert test_text in result.get('content', ''), f'Text not injected: {result}'
        finally:
            close_webview(view, page, platform)

    @pytest.mark.mutating
    def test_text_post_submit_and_delete(self, galefling_data_dir, fetlife_credentials):
        """Post a status, prove it exists on the feed, then attempt deletion.

        The post-condition is deliberately the status appearing on the feed, not a URL
        change.  FetLife stays on / returns to the feed either way, so asserting on the
        URL cannot distinguish a published status from a rejected submit — an earlier
        version of this test passed while creating nothing at all.
        """
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fetlife_credentials)
            wait_ms(3000)

            test_text = mutating_post_text()
            platform._inject_text(test_text)
            wait_ms(1000)

            inject_check = _read_status_text(page)
            assert inject_check.get('found') and test_text in inject_check.get('content', ''), (
                f'Text injection failed: {inject_check}'
            )
            assert inject_check.get('submitFound'), (
                f'"{FetLifePlatform.TEXT_SUBMIT_LABEL}" button not found: {inject_check}'
            )
            assert not inject_check.get('submitDisabled'), (
                f'"{FetLifePlatform.TEXT_SUBMIT_LABEL}" still disabled after injection — '
                f'the composer did not register the text: {inject_check}'
            )

            submit_result = _click_submit_button(page, FetLifePlatform.TEXT_SUBMIT_LABEL)
            assert isinstance(submit_result, dict) and submit_result.get('clicked'), (
                f'Submit failed: {submit_result}'
            )

            wait_ms(8000)
            posted = _status_exists_in_feed(page, test_text)
            if not posted.get('found'):
                load_page(page, TEXT_COMPOSER_URL, timeout_ms=20000)
                wait_ms(3000)
                posted = _status_exists_in_feed(page, test_text)
            assert posted.get('found'), (
                f'Status {test_text} is not on the feed after submit — nothing was posted: {posted}'
            )

            print(f'\n  FetLife status posted (tag {test_text})')
            post_url = page.url().toString()
            if POST_URL_PATTERN.search(post_url):
                delete_outcome = attempt_delete_current_post(page)
            else:
                delete_outcome = _delete_status_by_tag(page, test_text)
            print(f'  Delete attempt: {delete_outcome}')
            if not delete_outcome.get('deleted'):
                print(f'  MANUAL CLEANUP NEEDED — status {test_text} is still on the feed')
        finally:
            close_webview(view, page, platform)


@pytest.mark.functional
class TestFetLifePicturePost:
    """FetLife picture upload via FetLifePlatform._attach_media()."""

    @pytest.mark.non_mutating
    def test_picture_composer_loads(self, galefling_data_dir, fetlife_credentials):
        """Verify the picture composer loads with file input, submit button, and consent."""
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fetlife_credentials)

            ok, final_url = load_page(page, IMAGE_COMPOSER_URL, timeout_ms=20000)
            assert ok, f'Page load failed: {final_url}'
            assert '/login' not in final_url.lower(), f'Session expired: {final_url}'
            wait_ms(2000)

            result = _composer_elements(page, PICTURE_FILE_SELECTOR, 'Upload Your Picture')
            assert isinstance(result, dict), f'JS returned: {result}'
            assert result.get('fileInputFound'), 'File input not found'
            assert result.get('submitFound'), 'Upload button not found'
            assert 'image' in (result.get('fileInputAccept') or ''), (
                'File input does not accept images'
            )

            consent = _call_platform(platform._certify_upload_consent)
            assert consent.get('certified'), f'Consent certification not set: {consent}'
            assert consent.get('names') == ['picture[is_certified]'], (
                f'Unexpected certification fields: {consent}'
            )
        finally:
            close_webview(view, page, platform)

    @pytest.mark.non_mutating
    def test_picture_attach_via_platform(
        self, galefling_data_dir, fetlife_credentials, sample_jpeg
    ):
        """FetLifePlatform._attach_media() must load a file into the picture form.

        The picture composer exposes two file inputs: a hidden picker carrying the
        ``accept`` list, and the real ``picture[attachments][]`` field.  FetLife's own
        JS moves the file from the first to the second and clears the picker, so the
        attach is verified on the form as a whole.  Never submits.
        """
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fetlife_credentials)

            ok, final_url = load_page(page, IMAGE_COMPOSER_URL, timeout_ms=20000)
            assert ok and '/login' not in final_url.lower(), f'Session lost: {final_url}'
            wait_ms(2000)

            platform._image_path = sample_jpeg
            assert platform.get_media_file_selector() == PICTURE_FILE_SELECTOR

            attach = _call_platform(platform._attach_media, sample_jpeg)
            assert attach.get('dispatched'), f'Attach failed: {attach}'

            state = _wait_for_attachment(platform)
            assert state.get('attached'), f'Form never accepted the file: {state}'
            assert 'picture[attachments][]' in state.get('holders', []), (
                f'File did not reach the named form field: {state}'
            )

            consent = _call_platform(platform._certify_upload_consent)
            assert consent.get('certified'), f'Consent certification not set: {consent}'

            page_state = _upload_form_state(page, 'pictures/new')
            assert page_state.get('stillOnComposer'), 'Must not navigate away without submit'
            assert not page_state.get('avatarChecked'), (
                f'picture[is_avatar] must never be toggled: {page_state}'
            )
        finally:
            close_webview(view, page, platform)

    @pytest.mark.mutating
    def test_picture_upload_creates_a_post(
        self, galefling_data_dir, fetlife_credentials, sample_jpeg
    ):
        """Upload a real picture and prove the post exists.

        Cleanup is manual by decision — the run prints the caption tag. Deletion is not
        attempted; see _delete_status_by_tag for why FetLife's delete control resists
        automation.
        """
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fetlife_credentials)
            ok, final_url = load_page(page, IMAGE_COMPOSER_URL, timeout_ms=20000)
            assert ok and '/login' not in final_url.lower(), f'Session lost: {final_url}'
            wait_ms(2000)

            tag = mutating_post_text()
            platform._image_path = sample_jpeg

            attach = _call_platform(platform._attach_media, sample_jpeg)
            assert attach.get('dispatched'), f'Attach failed: {attach}'
            state = _wait_for_attachment(platform)
            assert state.get('attached'), f'Form never accepted the file: {state}'

            caption = _call_platform(platform._inject_media_caption, tag)
            assert caption.get('caption'), f'Caption not filled: {caption}'

            consent = _call_platform(platform._certify_upload_consent)
            assert consent.get('certified'), f'Consent not certified: {consent}'

            avatar = _avatar_checkbox_state(page)
            assert avatar.get('present'), f'Avatar checkbox missing — form changed: {avatar}'
            assert not avatar.get('checked'), (
                'picture[is_avatar] is checked; refusing to submit and replace the account avatar'
            )

            submit = _wait_for_enabled_submit(page, FetLifePlatform.IMAGE_SUBMIT_LABEL)
            assert submit.get('clicked'), f'Upload not clicked: {submit}'

            wait_ms(15000)
            post_url = page.url().toString()
            posted = _status_exists_in_feed(page, tag)
            assert POST_URL_PATTERN.search(post_url) or posted.get('found'), (
                f'No picture post after upload — url={post_url}, caption not found: {posted}'
            )
            print(f'\n  FetLife picture uploaded (tag {tag}) -> {post_url}')
            print(f'  MANUAL CLEANUP NEEDED — delete the picture tagged {tag}')
        finally:
            close_webview(view, page, platform)


@pytest.mark.functional
class TestFetLifeVideoPost:
    """FetLife video upload via FetLifePlatform._attach_media()."""

    @pytest.mark.non_mutating
    def test_video_composer_loads(self, galefling_data_dir, fetlife_credentials):
        """Verify the video composer loads with file input, submit button, and consent."""
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fetlife_credentials)

            ok, final_url = load_page(page, VIDEO_COMPOSER_URL, timeout_ms=20000)
            assert ok, f'Page load failed: {final_url}'
            assert '/login' not in final_url.lower(), f'Session expired: {final_url}'
            wait_ms(2000)

            result = _composer_elements(page, VIDEO_FILE_SELECTOR, 'Upload Your Video')
            assert isinstance(result, dict), f'JS returned: {result}'
            assert result.get('fileInputFound'), 'File input not found'
            assert result.get('submitFound'), 'Upload button not found'
            assert 'video' in (result.get('fileInputAccept') or ''), (
                'File input does not accept video'
            )

            consent = _call_platform(platform._certify_upload_consent)
            assert consent.get('certified'), f'Consent certification not set: {consent}'
            assert consent.get('names') == ['video[is_certified]'], (
                f'Unexpected certification fields: {consent}'
            )
        finally:
            close_webview(view, page, platform)

    @pytest.mark.non_mutating
    def test_video_attach_via_platform(self, galefling_data_dir, fetlife_credentials, sample_video):
        """FetLifePlatform._attach_media() must load a file into the video form."""
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fetlife_credentials)

            ok, final_url = load_page(page, VIDEO_COMPOSER_URL, timeout_ms=20000)
            assert ok and '/login' not in final_url.lower(), f'Session lost: {final_url}'
            wait_ms(2000)

            platform._image_path = sample_video
            assert platform.get_media_file_selector() == VIDEO_FILE_SELECTOR

            attach = _call_platform(platform._attach_media, sample_video)
            assert attach.get('dispatched'), f'Attach failed: {attach}'

            state = _wait_for_attachment(platform)
            assert state.get('attached'), f'Form never accepted the file: {state}'

            consent = _call_platform(platform._certify_upload_consent)
            assert consent.get('certified'), f'Consent certification not set: {consent}'

            page_state = _upload_form_state(page, 'videos/new')
            assert page_state.get('stillOnComposer'), 'Must not navigate away without submit'
        finally:
            close_webview(view, page, platform)

    @pytest.mark.mutating
    def test_video_upload_creates_a_post(
        self, galefling_data_dir, fetlife_credentials, sample_video
    ):
        """Upload a real video and prove it appears in the account's video gallery.

        The composer URL does not change on success — FetLife transfers and transcodes
        in place — so the gallery is the only honest post-condition. Cleanup is manual;
        the run prints the tag.
        """
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fetlife_credentials)
            ok, final_url = load_page(page, VIDEO_COMPOSER_URL, timeout_ms=20000)
            assert ok and '/login' not in final_url.lower(), f'Session lost: {final_url}'
            wait_ms(2000)

            tag = mutating_post_text()
            platform._image_path = sample_video

            attach = _call_platform(platform._attach_media, sample_video)
            assert attach.get('dispatched'), f'Attach failed: {attach}'
            state = _wait_for_attachment(platform)
            assert state.get('attached'), f'Form never accepted the file: {state}'

            caption = _call_platform(platform._inject_media_caption, tag)
            assert caption.get('caption'), f'Description not filled: {caption}'
            assert caption.get('title'), f'video[title] not filled: {caption}'

            consent = _call_platform(platform._certify_upload_consent)
            assert consent.get('certified'), f'Consent not certified: {consent}'

            submit = _wait_for_enabled_submit(page, FetLifePlatform.VIDEO_SUBMIT_LABEL)
            assert submit.get('clicked'), f'Upload not clicked: {submit}'

            # The composer URL never changes: FetLife transfers and transcodes the
            # video asynchronously in place, so navigation cannot signal success.
            # Only the gallery proves the video landed.
            wait_ms(20000)
            posted = _wait_for_media_in_gallery(page, 'videos', tag)
            assert posted.get('found'), (
                f'Video {tag} never appeared in the gallery after upload: {posted}'
            )
            print(f'\n  FetLife video uploaded (tag {tag}) -> {posted.get("gallery")}')
            print(f'  MANUAL CLEANUP NEEDED — delete the video tagged {tag}')
        finally:
            close_webview(view, page, platform)
