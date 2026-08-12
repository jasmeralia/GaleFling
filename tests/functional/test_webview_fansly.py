"""Functional tests for Fansly WebView posting.

Tests text injection into the Fansly composer.

Requires GALEFLING_DATA_DIR and FANSLY_EMAIL / FANSLY_PASSWORD in .env.
If the session cookie is still valid the login flow is skipped.
"""

import json

import pytest

from src.platforms.fansly import FanslyPlatform
from tests.functional.conftest import fail_or_skip, mutating_post_tag, mutating_post_text
from tests.functional.webview_helpers import (
    close_webview,
    create_webview,
    get_or_create_app,
    has_cookie_db,
    load_page,
    login_fansly,
    run_js,
    wait_ms,
)

ACCOUNT_ID = 'fansly_1'
COMPOSER_URL = FanslyPlatform.COMPOSER_URL
LANDING_URL = FanslyPlatform.LOGIN_URL
# Joined exactly as BaseWebViewPlatform._run_live_connection_test() joins them, so the
# tests detect an expired session by the same rule the app uses.  A hardcoded copy here
# had already drifted: it looked for input[type="password"] where the platform declares
# input[autocomplete="password"].
SESSION_EXPIRED_SELECTOR = ', '.join(FanslyPlatform.SESSION_EXPIRED_SELECTORS)


def _session_expired(page) -> bool:
    """Whether the shipped session-expiry selectors match the current page."""
    return bool(run_js(page, f'!!document.querySelector({json.dumps(SESSION_EXPIRED_SELECTOR)})'))


def _ensure_session(page, credentials: dict) -> None:
    """Verify we have a valid Fansly session, logging in if needed.

    Loads the Fansly home page and calls login_fansly if the session has
    expired. Reports a strict-mode failure if login cannot be completed.
    """
    ok, final_url = load_page(page, LANDING_URL, timeout_ms=20000)
    assert ok, f'Page load failed: {final_url}'

    # Wait for Cloudflare challenge + SPA hydration before checking state
    wait_ms(5000)

    # Fansly serves its public landing page at / without a URL redirect. The
    # logged-out navigation shell is therefore as authoritative as the form.
    if '/login' in final_url.lower() or _session_expired(page):
        success = login_fansly(page, credentials['email'], credentials['password'])
        if not success:
            fail_or_skip('Fansly login failed — check credentials in .env')


def _read_composer_text(page) -> dict:
    """Read back the composer element the platform targets."""
    return run_js(
        page,
        f"""
        (function() {{
            var el = document.querySelector({json.dumps(FanslyPlatform.TEXT_SELECTOR)});
            if (!el) return {{found: false}};
            return {{found: true, value: (el.value || el.textContent || '').substring(0, 100)}};
        }})();
        """,
    )


def _wait_for_attachment(platform, timeout_ms: int = 20000) -> dict:
    """Poll until the composer reports a file attached."""
    elapsed = 0
    state: dict = {}
    while elapsed < timeout_ms:
        state = _call_platform(platform._media_attachment_state)
        if state.get('attached'):
            return state
        wait_ms(500)
        elapsed += 500
    return state


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


def _trusted_click_xy(view, x: int, y: int) -> None:
    """Hover then click at viewport coordinates with real Qt mouse events."""
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtTest import QTest

    target = view.focusProxy() or view
    QTest.mouseMove(target, QPoint(x, y))
    wait_ms(350)
    QTest.mouseClick(
        target, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(x, y)
    )
    wait_ms(1200)


def _element_xy(page, js_expr: str) -> dict | None:
    """Centre coordinates of the element returned by *js_expr*, or None."""
    return run_js(
        page,
        f"""
        (function() {{
            var el = {js_expr};
            if (!el) return null;
            var r = el.getBoundingClientRect();
            if (r.width <= 0 || r.height <= 0) return null;
            return {{x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2)}};
        }})();
        """,
        timeout_ms=10000,
    )


def _open_media_menu(view, page, platform) -> bool:
    """Open the composer's media dropdown.

    The control is ``div.dropdown-title`` — the *parent* of ``i.fa-image.hover-effect``;
    clicking the icon itself does nothing.

    Fansly's modal backdrop covers the composer and swallows the first click, so the
    shipped ``dismiss_blocking_overlay()`` clears it first. Letting the menu click be
    absorbed instead would mean clicking blind into an unknown dialog at whatever
    coordinates the icon happens to occupy. The retry below is a safety net for a
    backdrop that reappears, not the mechanism.
    """
    overlay = _call_platform(platform.dismiss_blocking_overlay)
    print(f'    [attach] overlay: {overlay}', flush=True)
    for _ in range(4):
        point = _element_xy(
            page, "document.querySelector('i.fa-image.hover-effect')?.parentElement"
        )
        if point is None:
            return False
        _trusted_click_xy(view, point['x'], point['y'])
        if _element_xy(page, _UPLOAD_NEW_JS) is not None:
            return True
    return False


_UPLOAD_NEW_JS = (
    "Array.from(document.querySelectorAll('*')).filter(function(e){"
    "return e.children.length===0 && (e.textContent||'').trim()==='Upload New';})[0]"
)

_UPLOAD_BTN_JS = (
    'Array.from(document.querySelectorAll(\'button, div[class*="btn"]\')).filter(function(e){'
    "return (e.textContent||'').trim()==='Upload';})[0]"
)


def _composer_media_count(page) -> int:
    """Media items the composer is holding, scoped to its own upload container.

    Never count preview-ish classes document-wide: the surrounding feed dominates that
    number and it drifts on its own, which previously produced a false pass.
    """
    value = run_js(
        page,
        '(document.querySelector(\'[class*="media-upload-container"]\') || {children: []})'
        '.children.length',
        timeout_ms=10000,
    )
    return int(value) if isinstance(value, int) else -1


def _post_has_media(page, tag: str) -> dict:
    """Whether the published post carrying *tag* actually contains media.

    A post created before the upload finishes keeps its caption and silently drops the
    media, so asserting the caption appeared is not enough.

    Two things make this assertion mean what it says, both learned the hard way:

    **Scope to the post, by name.** A parent walk that keeps climbing until it finds an
    image escapes into ``div.feed-content`` — measured at depth 3, holding 20 images
    belonging to other posts. This anchors on the enclosing ``.feed-item`` instead and
    reports a failure if there isn't one, rather than climbing past it.

    **Exclude the author avatar.** ``div.feed-item-meta-wrapper`` carries a 56x56
    ``img.image.cover`` — the poster's avatar, present whether or not any media
    attached. It is the *first* image a walk finds, one level below the attachment, so
    an unfiltered check reports success on a post whose image silently dropped. That is
    not hypothetical: it is what this function did on the run that first passed.

    The matched media's dimensions and classes come back in the result so a pass can be
    audited rather than taken on trust.
    """
    return run_js(
        page,
        f"""
        (function() {{
            var leaf = Array.from(document.querySelectorAll('*')).filter(function(el) {{
                return el.children.length === 0
                    && (el.textContent || '').indexOf({json.dumps(tag)}) !== -1;
            }})[0];
            if (!leaf) return {{found: false, reason: 'tag not on page'}};

            var post = leaf.closest('.feed-item');
            if (!post) {{
                return {{found: true, hasMedia: false, reason: 'no .feed-item ancestor'}};
            }}

            function sourced(m) {{
                if (/^https?:|^blob:/.test(m.src || m.currentSrc || '')) return true;
                // A <video> often carries no src of its own: Fansly's video-js player
                // puts it on a <source> child, and a not-yet-playing video may only
                // have its poster. Requiring element.src alone reports "no media" on a
                // perfectly good video post.
                //
                // Note this branch is a safety net rather than the observed path: a
                // published video post renders in the feed as two poster `img.image`
                // elements (cover + contain), with no <video> until playback. The
                // player elements do exist elsewhere in the feed, which is why the
                // case is handled at all.
                if (m.tagName.toLowerCase() !== 'video') return false;
                if (/^https?:|^blob:/.test(m.getAttribute('poster') || '')) return true;
                return Array.from(m.querySelectorAll('source')).some(function(s) {{
                    return /^https?:|^blob:/.test(s.getAttribute('src') || '');
                }});
            }}

            var media = Array.from(post.querySelectorAll('img, video')).filter(function(m) {{
                if (!sourced(m)) return false;
                // The avatar in the post header is not post media.
                return !m.closest('[class*="feed-item-meta"]');
            }}).map(function(m) {{
                var r = m.getBoundingClientRect();
                return {{
                    tag: m.tagName.toLowerCase(),
                    cls: ((m.className || '') + '').trim(),
                    w: Math.round(r.width),
                    h: Math.round(r.height)
                }};
            }});

            return {{found: true, hasMedia: media.length > 0, count: media.length,
                     media: media.slice(0, 4)}};
        }})();
        """,
        timeout_ms=15000,
    )


def _attach_media_through_ui(view, page, platform, path, upload_timeout_ms: int = 45000) -> dict:
    """Drive Fansly's own media flow end to end, applying the no-paywall policy.

    icon -> Upload New -> native picker (chooseFiles) -> Upload media modal ->
    permissions -> Upload. Writing the file onto the input directly does not work:
    Fansly's uploader is never in the call stack.
    """

    def step(msg):
        # Several multi-second waits live below. Announce each, so a slow run is
        # visibly progressing rather than indistinguishable from a hang.
        print(f'    [attach] {msg}', flush=True)

    platform.suppress_native_file_dialog = True
    platform.stage_media_for_picker(path)
    before = _composer_media_count(page)
    step(f'staged {path.name}; composer holds {before} item(s)')

    if not _open_media_menu(view, page, platform):
        return {'attached': False, 'reason': 'media dropdown never opened'}
    step('media dropdown open')

    point = _element_xy(page, _UPLOAD_NEW_JS)
    if point is None:
        return {'attached': False, 'reason': '"Upload New" not visible'}
    _trusted_click_xy(view, point['x'], point['y'])

    elapsed = 0
    while elapsed < 20000:
        if run_js(page, '/Upload media/.test(document.body.innerText)', timeout_ms=10000):
            break
        wait_ms(1000)
        elapsed += 1000
    else:
        return {
            'attached': False,
            'reason': 'Upload media modal never opened',
            'picker_invocations': platform.picker_invocations,
        }

    step(f'modal open (picker fired {platform.picker_invocations}x)')

    perms = _call_platform(platform.apply_media_permissions)
    if not perms.get('ok'):
        return {'attached': False, 'reason': f'permissions not applied: {perms}'}

    step(f'permissions applied: {perms.get("state")}')

    point = _element_xy(page, _UPLOAD_BTN_JS)
    if point is None:
        return {'attached': False, 'reason': 'Upload button not found', 'permissions': perms}
    _trusted_click_xy(view, point['x'], point['y'])

    elapsed = 0
    while elapsed < upload_timeout_ms:
        if _composer_media_count(page) > before:
            return {
                'attached': True,
                'permissions': perms,
                'mediaCount': _composer_media_count(page),
            }
        wait_ms(2000)
        elapsed += 2000
    return {
        'attached': False,
        'reason': 'media never reached the composer',
        'permissions': perms,
        'before': before,
    }


def _own_profile_href(page) -> str | None:
    """Resolve the logged-in account's profile path from the feed's own links."""
    return run_js(
        page,
        """
        (function() {
            var a = document.querySelector('a.username-wrapper[href^="/"]')
                || Array.from(document.querySelectorAll('a[href^="/"]')).find(function(x) {
                    return /username-wrapper/.test(x.className || '');
                });
            return a ? a.getAttribute('href').split('?')[0] : null;
        })();
        """,
        timeout_ms=10000,
    )


def _text_on_page(page, needle: str) -> bool:
    """Whether *needle* appears in the rendered page text."""
    return bool(
        run_js(
            page,
            f'(document.body ? document.body.innerText : "").indexOf({json.dumps(needle)}) !== -1',
            timeout_ms=10000,
        )
    )


def _post_permalinks(page) -> list:
    """Permalinks visible on the current page. Fansly posts live at /post/<id>."""
    links = run_js(
        page,
        """
        Array.from(document.querySelectorAll('a[href*="/post/"]'))
            .map(function(a) { return a.getAttribute('href'); })
            .filter(function(h) { return /\\/post\\/\\d+/.test(h || ''); })
            .slice(0, 5);
        """,
        timeout_ms=10000,
    )
    return links if isinstance(links, list) else []


def _wait_for_post(page, tag: str, timeout_ms: int = 60000) -> dict:
    """Poll until *tag* is visible, in place first and only then via reloads.

    Fansly sets neither SUCCESS_URL_PATTERN nor SUCCESS_SELECTOR — the app cannot
    confirm a post automatically either — so finding the text is the only proof that
    anything was created.

    The SPA prepends a new post to the page it is already on, so checking in place
    catches it in seconds. Reloading first instead wasted the whole budget on page
    loads and let a *successful* image post fail verification.
    """
    elapsed = 0
    while elapsed < 20000:
        if _text_on_page(page, tag):
            return {'found': True, 'where': 'in place', 'permalinks': _post_permalinks(page)}
        wait_ms(2500)
        elapsed += 2500

    profile = _own_profile_href(page)
    targets = [COMPOSER_URL] + ([f'https://fansly.com{profile}'] if profile else [])
    while elapsed <= timeout_ms:
        for url in targets:
            load_page(page, url, timeout_ms=20000)
            wait_ms(5000)
            if _text_on_page(page, tag):
                return {'found': True, 'where': url, 'permalinks': _post_permalinks(page)}
        elapsed += 25000
    return {'found': False, 'profile': profile, 'tried': targets, 'waited_ms': elapsed}


# Resolve the composer's submit control, shared by the state probe and the click so
# the two can never disagree about which element they mean.
#
# It is a ``<div>`` carrying a ``btn`` class, not a ``<button>`` — it has no
# ``type="submit"`` and no ``role="button"``, so a button-oriented lookup finds
# nothing. It also has element children, so it is not a leaf node. Candidates are
# ranked innermost-first so we land on the control itself rather than a wrapper that
# happens to contain the same text.
_RESOLVE_POST_JS = f"""
(function() {{
    var label = {json.dumps(FanslyPlatform.TEXT_SUBMIT_LABEL)};
    var ta = document.querySelector({json.dumps(FanslyPlatform.TEXT_SELECTOR)});
    if (!ta) return {{el: null, reason: 'composer textarea not found'}};

    var scope = ta;
    for (var d = 0; d < 8 && scope.parentElement; d++) {{
        scope = scope.parentElement;
        var hits = Array.from(scope.querySelectorAll(
            'button, app-button, [role="button"], '
            + 'div[class*="btn"], span[class*="btn"], a[class*="btn"]'
        )).filter(function(el) {{
            return (el.textContent || '').trim() === label;
        }});
        if (!hits.length) continue;
        // Innermost match: fewest descendants.
        hits.sort(function(a, b) {{
            return a.querySelectorAll('*').length - b.querySelectorAll('*').length;
        }});
        return {{el: hits[0], depth: d, candidates: hits.length}};
    }}
    return {{
        el: null,
        reason: 'no ' + label + ' control near the composer',
        textareaClass: ta.className
    }};
}})()
"""


def _post_control_state(page) -> dict:
    """Report whether the composer's submit control is currently enabled.

    ``disabled`` is a **class** on a ``<div>``, not the DOM property, so it is read
    through ``classList`` — a whole-token test. A substring match would also fire on
    any future class that merely contains the word.
    """
    return run_js(
        page,
        f"""
        (function() {{
            var found = {_RESOLVE_POST_JS};
            if (!found.el) return {{found: false, reason: found.reason}};
            return {{
                found: true,
                disabled: found.el.classList.contains('disabled'),
                tag: found.el.tagName.toLowerCase(),
                cls: (found.el.className || '').toString().substring(0, 60),
                depth: found.depth,
                candidates: found.candidates
            }};
        }})();
        """,
    )


def _click_post_control(page) -> dict:
    """Click the composer's submit control, refusing to click it while disabled.

    Fansly disables the control by adding a ``disabled`` **class** to a ``<div>``.
    Nothing about a ``<div>`` stops ``.click()`` being delivered, so clicking one in
    that state reports success and publishes nothing — the exact false positive that
    made Fansly media posting look intermittently broken. Refusing here means
    ``clicked`` is evidence of a click that could act, not merely one that was sent.
    """
    return run_js(
        page,
        f"""
        (function() {{
            var found = {_RESOLVE_POST_JS};
            if (!found.el) {{
                return {{
                    clicked: false,
                    reason: found.reason,
                    textareaClass: found.textareaClass
                }};
            }}
            var target = found.el;
            var cls = (target.className || '').toString().substring(0, 60);
            if (target.classList.contains('disabled')) {{
                return {{clicked: false, reason: 'post control disabled', cls: cls}};
            }}
            target.click();
            return {{
                clicked: true,
                tag: target.tagName.toLowerCase(),
                cls: cls,
                depth: found.depth,
                candidates: found.candidates
            }};
        }})();
        """,
    )


def _click_post_when_enabled(page, timeout_ms: int = 60000) -> dict:
    """Wait for the submit control to leave its disabled state, then click it.

    With media attached the control stays disabled while Fansly finishes processing
    the upload — measured at ~5 s after the composer first shows the attachment, and
    still disabled at the 2 s mark where the click used to happen. The composer
    reporting a child in ``media-upload-container`` is therefore not the same as being
    ready to post.
    """
    elapsed = 0
    state: dict = {}
    while elapsed <= timeout_ms:
        state = _post_control_state(page)
        if state.get('found') and not state.get('disabled'):
            result = _click_post_control(page)
            result['enabled_after_ms'] = elapsed
            return result
        wait_ms(1000)
        elapsed += 1000
    return {'clicked': False, 'reason': 'post control never left disabled', 'detail': state}


@pytest.mark.functional
@pytest.mark.non_mutating
class TestFanslyConnection:
    """Session and platform adapter checks — fail fast before composer tests."""

    def test_has_valid_session(self, galefling_data_dir):
        """Cookie database must exist and pass has_valid_session()."""
        if not has_cookie_db(galefling_data_dir, ACCOUNT_ID):
            pytest.skip('No Fansly cookie database — log in via Settings first')
        platform = FanslyPlatform(account_id=ACCOUNT_ID)
        assert platform.has_valid_session(), 'Fansly session invalid or expired'

    def test_authenticate(self, galefling_data_dir):
        """WebView platforms report authenticate() success when cookies exist."""
        if not has_cookie_db(galefling_data_dir, ACCOUNT_ID):
            pytest.skip('No Fansly cookie database')
        platform = FanslyPlatform(account_id=ACCOUNT_ID)
        ok, err = platform.authenticate()
        assert ok, f'authenticate() failed: {err}'
        assert err is None

    def test_connection(self, galefling_data_dir, fansly_credentials):
        """Platform test_connection() drives the shipped SESSION_EXPIRED_SELECTORS check.

        This is the only test that exercises expired-session detection through shipped
        code rather than re-querying the selectors itself.
        """
        if not has_cookie_db(galefling_data_dir, ACCOUNT_ID):
            pytest.skip('No Fansly cookie database')
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            ok, err = platform.test_connection()
            if not ok and err == 'WV-SESSION-EXPIRED':
                _ensure_session(page, fansly_credentials)
                ok, err = platform.test_connection()
            assert ok, f'test_connection() failed: {err}'
            assert err is None
        finally:
            close_webview(view, page, platform)


_DECLINE_LABELS = [
    label.strip().lower() for label in FanslyPlatform.BLOCKING_OVERLAY_DISMISS_LABELS
]


def _push_prompt_state(page) -> dict:
    """Observe Fansly's push-notification greeting and what it is covering.

    Deliberately observation only — the dismissal is shipped code
    (``dismiss_blocking_overlay``). A test that dismissed the prompt itself would keep
    passing after the shipped one broke, which is the defect class these tests exist
    to catch.
    """
    return run_js(
        page,
        f"""
        (function() {{
            function shown(el) {{
                if (!el) return false;
                var r = el.getBoundingClientRect();
                var s = getComputedStyle(el);
                return r.width > 0 && r.height > 0
                    && s.display !== 'none' && s.visibility !== 'hidden';
            }}
            var wanted = {json.dumps(_DECLINE_LABELS)};
            var controls = Array.from(document.querySelectorAll(
                'button, a, [role="button"], div[class*="btn"], span[class*="btn"]'
            )).filter(shown);

            // The media icon is the composer control the backdrop covers.
            var icon = document.querySelector('i.fa-image.hover-effect');
            var host = icon ? icon.parentElement : null;
            var covered = null;
            if (host) {{
                var r = host.getBoundingClientRect();
                var hit = document.elementFromPoint(
                    Math.round(r.left + r.width / 2), Math.round(r.top + r.height / 2));
                covered = !!hit && hit !== host && !host.contains(hit);
            }}
            return {{
                backdrop: shown(document.querySelector(
                    {json.dumps(FanslyPlatform.BLOCKING_OVERLAY_SELECTOR)})),
                declineVisible: controls.some(function(b) {{
                    return wanted.indexOf((b.textContent || '').trim().toLowerCase()) !== -1;
                }}),
                affirmativeVisible: controls.some(function(b) {{
                    return (b.textContent || '').trim().toLowerCase() === 'yes, enable';
                }}),
                iconCovered: covered
            }};
        }})();
        """,
        timeout_ms=15000,
    )


@pytest.mark.functional
@pytest.mark.non_mutating
class TestFanslyGreetingPrompt:
    """Fansly's "Enable Push Notifications" greeting must be cleared by shipped code."""

    def test_shipped_dismissal_clears_the_prompt_and_uncovers_the_composer(
        self, galefling_data_dir, fansly_credentials
    ):
        """The backdrop covers the whole composer until something clears it.

        Asserts the artifact — prompt gone and the media icon reachable by a real
        click — rather than that a dismissal was merely attempted.
        """
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fansly_credentials)
            ok, final_url = load_page(page, COMPOSER_URL, timeout_ms=30000)
            assert ok, f'Composer load failed: {final_url}'
            wait_ms(8000)

            before = _push_prompt_state(page)
            if not before.get('backdrop'):
                pytest.skip(f'Fansly showed no greeting prompt this session: {before}')

            result = _call_platform(platform.dismiss_blocking_overlay)
            # 'via' records whether the named decline control or the backdrop fallback
            # cleared it — without it a pass cannot distinguish the two paths.
            print(f'\n  dismissed via {result.get("via")}: {result.get("text")}', flush=True)
            assert result.get('dismissed'), f'Shipped dismissal did not clear it: {result}'

            wait_ms(1500)
            after = _push_prompt_state(page)
            assert not after.get('backdrop'), f'Backdrop survived: {after}'
            assert not after.get('declineVisible'), f'Prompt still on screen: {after}'
            assert not after.get('affirmativeVisible'), f'Prompt still on screen: {after}'
            assert after.get('iconCovered') is False, (
                f'Composer still covered after dismissal: {after}'
            )
        finally:
            close_webview(view, page, platform)


@pytest.mark.functional
@pytest.mark.non_mutating
class TestFanslyTextInjection:
    """Fansly text injection: verify text can be entered into the composer."""

    def test_composer_loads(self, galefling_data_dir, fansly_credentials):
        """Verify the Fansly home/composer page loads in an authenticated state."""
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fansly_credentials)
            # Confirm no login redirect after session is established
            assert '/login' not in page.url().toString().lower(), (
                f'Still on login page after authentication: {page.url().toString()}'
            )
            assert not _session_expired(page), (
                'Fansly still matches its own SESSION_EXPIRED_SELECTORS after authentication'
            )
        finally:
            close_webview(view, page, platform)

    def test_text_injection_via_platform(self, galefling_data_dir, fansly_credentials):
        """Verify FanslyPlatform._inject_text() fills the composer.

        Drives the shipped injection rather than a copy of it, so a regression in
        ``_inject_text`` or ``TEXT_SELECTOR`` fails here (Phase 5).
        """
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fansly_credentials)
            ok, final_url = load_page(page, COMPOSER_URL, timeout_ms=20000)
            assert ok, f'Composer load failed: {final_url}'
            wait_ms(5000)  # Extra wait for SPA to fully hydrate after login

            test_text = mutating_post_tag()
            platform._inject_text(test_text)
            wait_ms(1000)

            result = _read_composer_text(page)
            assert isinstance(result, dict), f'JS returned: {result}'
            assert result.get('found'), (
                f'Composer element not found for {FanslyPlatform.TEXT_SELECTOR!r}: {result}'
            )
            assert test_text in result.get('value', ''), f'Text not injected: {result}'
        finally:
            close_webview(view, page, platform)


@pytest.mark.functional
class TestFanslyPost:
    """Fansly posting — the only coverage that proves a post is created at all."""

    @pytest.mark.non_mutating
    def test_composer_elements_present(self, galefling_data_dir, fansly_credentials):
        """The composer textarea and its media input must both exist.

        `test_composer_loads` only proves the session is authenticated; this asserts
        the elements GaleFling actually depends on are on the page.
        """
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fansly_credentials)
            ok, final_url = load_page(page, COMPOSER_URL, timeout_ms=30000)
            assert ok, f'Composer load failed: {final_url}'
            wait_ms(8000)

            state = run_js(
                page,
                f"""
                (function() {{
                    var ta = document.querySelector(
                        {json.dumps(FanslyPlatform.TEXT_SELECTOR)}
                    );
                    var file = document.querySelector(
                        {json.dumps(FanslyPlatform.MEDIA_FILE_SELECTOR)}
                    );
                    return {{
                        textareaCount: document.querySelectorAll('textarea').length,
                        textareaFound: !!ta,
                        maxlength: ta ? ta.getAttribute('maxlength') : null,
                        fileFound: !!file,
                        accept: file ? file.getAttribute('accept') : null
                    }};
                }})();
                """,
            )
            assert isinstance(state, dict), f'JS returned: {state}'
            assert state.get('textareaFound'), f'Composer textarea missing: {state}'
            # TEXT_SELECTOR is the bare tag name, so a second textarea would make
            # querySelector ambiguous and could silently retarget the app.
            assert state.get('textareaCount') == 1, (
                f'TEXT_SELECTOR {FanslyPlatform.TEXT_SELECTOR!r} is ambiguous — '
                f'{state.get("textareaCount")} textareas on the page: {state}'
            )
            assert state.get('fileFound'), f'Composer media input missing: {state}'
            assert str(state.get('maxlength')) == str(
                FanslyPlatform().get_specs().max_text_length
            ), (
                f'Composer maxlength {state.get("maxlength")} disagrees with '
                f'FANSLY_SPECS.max_text_length: {state}'
            )
        finally:
            close_webview(view, page, platform)

    @pytest.mark.mutating
    def test_text_post_creates_a_post(self, galefling_data_dir, fansly_credentials):
        """Post real text and prove it exists.

        Fansly has neither SUCCESS_URL_PATTERN nor SUCCESS_SELECTOR, so the app cannot
        confirm a post automatically either — a user marks it done by hand. Finding the
        text is therefore the only evidence available that anything was created.

        Cleanup is manual: the run prints the tag.
        """
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fansly_credentials)
            ok, final_url = load_page(page, COMPOSER_URL, timeout_ms=30000)
            assert ok, f'Composer load failed: {final_url}'
            wait_ms(8000)

            tag = mutating_post_text()

            print(f'\n  posting tag {tag} — delete this if the run fails')
            platform._inject_text(tag)
            wait_ms(2000)

            injected = _read_composer_text(page)
            assert injected.get('found') and tag in injected.get('value', ''), (
                f'Text injection failed: {injected}'
            )

            submit = _click_post_when_enabled(page)
            assert submit.get('clicked'), f'Post control not clicked: {submit}'

            wait_ms(8000)
            posted = _wait_for_post(page, tag)
            assert posted.get('found'), (
                f'Fansly post {tag} not found after submit — nothing was created: {posted}'
            )
            print(f'\n  Fansly post created (tag {tag}) -> {posted.get("where")}')
            print(f'  MANUAL CLEANUP NEEDED — delete the Fansly post tagged {tag}')
        finally:
            close_webview(view, page, platform)

    @pytest.mark.mutating
    def test_image_post_creates_a_post_with_media(
        self, galefling_data_dir, fansly_credentials, sample_jpeg
    ):
        """Post a real image through Fansly's own upload flow and prove media landed.

        Asserts the *published* post contains media, not merely that the caption
        reached the feed — a post created before the upload completes keeps its text
        and silently drops the image.
        """
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            print('\n  [1/5] establishing session', flush=True)
            _ensure_session(page, fansly_credentials)
            ok, final_url = load_page(page, COMPOSER_URL, timeout_ms=30000)
            assert ok, f'Composer load failed: {final_url}'
            wait_ms(8000)

            print('  [2/5] attaching media through the composer UI', flush=True)
            attached = _attach_media_through_ui(view, page, platform, sample_jpeg)
            assert attached.get('attached'), f'Media never attached: {attached}'

            perms = attached.get('permissions', {})
            assert perms.get('state', {}).get('Require Subscription') is False, (
                f'Post would be paywalled: {perms}'
            )
            assert perms.get('state', {}).get('Require Follow') is True, (
                f'Require Follow not set: {perms}'
            )

            tag = mutating_post_text()
            print(f'  [3/5] posting tag {tag} — delete this if the run fails', flush=True)
            platform._inject_text(tag)
            wait_ms(2000)
            injected = _read_composer_text(page)
            assert injected.get('found') and tag in injected.get('value', ''), (
                f'Caption not in composer: {injected}'
            )

            print('  [4/5] clicking Post once it is enabled', flush=True)
            submit = _click_post_when_enabled(page)
            assert submit.get('clicked'), f'Post control not clicked: {submit}'
            print(f'    submit {submit}', flush=True)

            wait_ms(10000)
            print('  [5/5] verifying the published post', flush=True)
            posted = _wait_for_post(page, tag, timeout_ms=60000)
            assert posted.get('found'), f'Post {tag} not found after submit: {posted}'

            media = _post_has_media(page, tag)
            assert media.get('hasMedia'), f'Fansly published the caption but no image: {media}'
            print(f'\n  Fansly image post created (tag {tag}) -> {posted.get("where")}')
            print(f'  permalinks: {posted.get("permalinks")}  media: {media}')
            print(f'  MANUAL CLEANUP NEEDED — delete the Fansly post tagged {tag}')
        finally:
            close_webview(view, page, platform)

    @pytest.mark.mutating
    def test_video_post_creates_a_post_with_media(
        self, galefling_data_dir, fansly_credentials, sample_video
    ):
        """Post a real video through the same flow and prove media reached the post.

        The composer flow is identical to an image from the user's side. The timings
        turned out to be too: the submit control cleared ``disabled`` after ~5 s for a
        2 s 320x240 clip, the same figure measured for a JPEG. The budgets below stay
        generous because that is one small clip, not a characterisation of transcoding —
        a large upload is still unmeasured. The measured figure is printed on every run.

        **What this asserts is that media landed, not that it is a video.** Fansly
        renders a video post in the feed as a pair of poster ``img`` elements with no
        ``<video>`` present until playback, so there is no video-specific marker to key
        on without publishing a post to hunt one down. That is a deliberate limit: the
        realistic failure — the upload failing and the caption posting alone — produces
        no poster images and so does fail here.
        """
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            print('\n  [1/5] establishing session', flush=True)
            _ensure_session(page, fansly_credentials)
            ok, final_url = load_page(page, COMPOSER_URL, timeout_ms=30000)
            assert ok, f'Composer load failed: {final_url}'
            wait_ms(8000)

            print('  [2/5] attaching video through the composer UI', flush=True)
            attached = _attach_media_through_ui(
                view, page, platform, sample_video, upload_timeout_ms=180000
            )
            assert attached.get('attached'), f'Video never attached: {attached}'

            perms = attached.get('permissions', {})
            assert perms.get('state', {}).get('Require Subscription') is False, (
                f'Post would be paywalled: {perms}'
            )
            assert perms.get('state', {}).get('Require Follow') is True, (
                f'Require Follow not set: {perms}'
            )

            tag = mutating_post_text()
            print(f'  [3/5] posting tag {tag} — delete this if the run fails', flush=True)
            platform._inject_text(tag)
            wait_ms(2000)
            injected = _read_composer_text(page)
            assert injected.get('found') and tag in injected.get('value', ''), (
                f'Caption not in composer: {injected}'
            )

            print('  [4/5] clicking Post once it is enabled', flush=True)
            submit = _click_post_when_enabled(page, timeout_ms=240000)
            assert submit.get('clicked'), f'Post control not clicked: {submit}'
            print(f'    submit {submit}', flush=True)

            wait_ms(10000)
            print('  [5/5] verifying the published post', flush=True)
            posted = _wait_for_post(page, tag, timeout_ms=90000)
            assert posted.get('found'), f'Post {tag} not found after submit: {posted}'

            media = _post_has_media(page, tag)
            assert media.get('hasMedia'), f'Fansly published the caption but no video: {media}'
            print(f'\n  Fansly video post created (tag {tag}) -> {posted.get("where")}')
            print(f'  permalinks: {posted.get("permalinks")}  media: {media}')
            print(f'  MANUAL CLEANUP NEEDED — delete the Fansly post tagged {tag}')
        finally:
            close_webview(view, page, platform)
