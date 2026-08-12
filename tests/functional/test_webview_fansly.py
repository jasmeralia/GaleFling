"""Functional tests for Fansly WebView posting.

Tests text injection into the Fansly composer.

Requires GALEFLING_DATA_DIR and FANSLY_EMAIL / FANSLY_PASSWORD in .env.
If the session cookie is still valid the login flow is skipped.
"""

import json

import pytest

from src.platforms.fansly import FanslyPlatform
from tests.functional.conftest import fail_or_skip, mutating_post_tag
from tests.functional.webview_helpers import (
    close_webview,
    create_webview,
    get_or_create_app,
    load_page,
    login_fansly,
    run_js,
    wait_ms,
)

ACCOUNT_ID = 'fansly_1'
COMPOSER_URL = FanslyPlatform.COMPOSER_URL
LANDING_URL = FanslyPlatform.LOGIN_URL


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
    login_check = run_js(
        page,
        """
        (function() {
            return !!document.querySelector(
                'input[type="password"], .nav-content-wrapper.not-logged-in'
            );
        })();
        """,
    )
    if '/login' in final_url.lower() or login_check:
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
            assert not run_js(
                page,
                "!!document.querySelector('.nav-content-wrapper.not-logged-in')",
            ), 'Fansly public landing page still visible after authentication'
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
