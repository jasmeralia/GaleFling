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


def _wait_for_post(page, tag: str, timeout_ms: int = 90000) -> dict:
    """Poll the feed, then the account's own profile, until *tag* is visible.

    Fansly sets no SUCCESS_URL_PATTERN and no SUCCESS_SELECTOR — the SPA does not
    navigate on post — so finding the text is the only available proof that anything
    was created.
    """
    profile = _own_profile_href(page)
    targets = [COMPOSER_URL]
    if profile:
        targets.append(f'https://fansly.com{profile}')

    elapsed = 0
    while elapsed <= timeout_ms:
        for url in targets:
            load_page(page, url, timeout_ms=30000)
            wait_ms(6000)  # Cloudflare + SPA hydration
            if _text_on_page(page, tag):
                return {'found': True, 'where': url, 'profile': profile}
        elapsed += 20000
    return {'found': False, 'profile': profile, 'tried': targets, 'waited_ms': elapsed}


def _click_post_control(page) -> dict:
    """Click the composer's submit control.

    It is a ``<div>`` carrying a ``btn`` class, not a ``<button>`` — it has no
    ``type="submit"`` and no ``role="button"``, so a button-oriented lookup finds
    nothing. It also has element children, so it is not a leaf node. Candidates are
    ranked innermost-first so the click lands on the control itself rather than a
    wrapper that happens to contain the same text.
    """
    return run_js(
        page,
        f"""
        (function() {{
            var label = {json.dumps(FanslyPlatform.TEXT_SUBMIT_LABEL)};
            var ta = document.querySelector({json.dumps(FanslyPlatform.TEXT_SELECTOR)});
            if (!ta) return {{clicked: false, reason: 'composer textarea not found'}};

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
                var target = hits[0];
                target.click();
                return {{
                    clicked: true,
                    tag: target.tagName.toLowerCase(),
                    cls: (target.className || '').toString().substring(0, 60),
                    depth: d,
                    candidates: hits.length
                }};
            }}
            return {{
                clicked: false,
                reason: 'no ' + label + ' control near the composer',
                textareaClass: ta.className
            }};
        }})();
        """,
    )


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
            platform._inject_text(tag)
            wait_ms(2000)

            injected = _read_composer_text(page)
            assert injected.get('found') and tag in injected.get('value', ''), (
                f'Text injection failed: {injected}'
            )

            submit = _click_post_control(page)
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
