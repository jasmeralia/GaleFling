"""Functional tests for Fansly WebView posting.

Tests text injection into the Fansly composer.

Requires GALEFLING_DATA_DIR and FANSLY_EMAIL / FANSLY_PASSWORD in .env.
If the session cookie is still valid the login flow is skipped.
"""

import json
import uuid

import pytest

from tests.functional.webview_helpers import (
    create_webview,
    get_or_create_app,
    load_page,
    login_fansly,
    run_js,
    wait_ms,
)

ACCOUNT_ID = 'fansly_1'


def _ensure_session(page, credentials: dict) -> None:
    """Verify we have a valid Fansly session, logging in if needed.

    Loads the Fansly home page and calls login_fansly if the session has
    expired. Calls pytest.skip if login cannot be completed.
    """
    ok, final_url = load_page(page, 'https://fansly.com/', timeout_ms=20000)
    assert ok, f'Page load failed: {final_url}'

    # Wait for Cloudflare challenge + SPA hydration before checking state
    wait_ms(5000)

    if '/login' in final_url.lower():
        success = login_fansly(page, credentials['email'], credentials['password'])
        if not success:
            pytest.skip('Fansly login failed — check credentials in .env')
        return

    # Also check for login form that may appear without a URL redirect
    login_check = run_js(
        page,
        """
        (function() {
            return !!document.querySelector('input[type="password"]');
        })();
        """,
    )
    if login_check:
        success = login_fansly(page, credentials['email'], credentials['password'])
        if not success:
            pytest.skip('Fansly login failed — check credentials in .env')


@pytest.mark.functional
class TestFanslyTextInjection:
    """Fansly text injection: verify text can be entered into the composer."""

    def test_composer_loads(self, galefling_data_dir, fansly_credentials):
        """Verify the Fansly home/composer page loads in an authenticated state."""
        get_or_create_app()
        view, page, profile = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fansly_credentials)
            # Confirm no login redirect after session is established
            assert '/login' not in page.url().toString().lower(), (
                f'Still on login page after authentication: {page.url().toString()}'
            )
        finally:
            page.deleteLater()
            profile.deleteLater()

    def test_text_injection(self, galefling_data_dir, fansly_credentials):
        """Verify text can be injected into the Fansly textarea."""
        get_or_create_app()
        view, page, profile = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fansly_credentials)
            wait_ms(5000)  # Extra wait for SPA to fully hydrate after login

            tag = uuid.uuid4().hex[:8]
            test_text = f'GaleFling functional test {tag}'
            result = run_js(
                page,
                f"""
                (function() {{
                    var el = document.querySelector('textarea');
                    if (!el) return {{found: false}};
                    el.focus();
                    el.value = {json.dumps(test_text)};
                    el.dispatchEvent(new Event('input', {{bubbles: true}}));
                    el.dispatchEvent(new Event('change', {{bubbles: true}}));
                    return {{found: true, value: el.value.substring(0, 100)}};
                }})();
                """,
            )
            assert isinstance(result, dict), f'JS returned: {result}'
            assert result.get('found'), 'Textarea not found'
            assert test_text in result.get('value', ''), f'Text not injected: {result}'
        finally:
            page.deleteLater()
            profile.deleteLater()
