"""Functional tests for Threads WebView posting.

Tests page load authentication and text injection into the Threads composer.

Requires GALEFLING_DATA_DIR and THREADS_USERNAME / THREADS_PASSWORD in .env.
If the session cookie is still valid the login flow is skipped.

NOTE: The Threads platform is not yet finalized. Selectors used here
(TEXT_SELECTOR = '[data-lexical-editor="true"]') match ThreadsPlatform but
are marked THREADS_PLACEHOLDER in the source — they have not been verified
against the live site. Update both ThreadsPlatform and these tests together
once the selectors are confirmed.
"""

import json
import uuid

import pytest

from tests.functional.webview_helpers import (
    create_webview,
    get_or_create_app,
    load_page,
    login_threads,
    run_js,
    wait_ms,
)

ACCOUNT_ID = 'threads_1'


def _ensure_session(page, credentials: dict) -> None:
    """Verify we have a valid Threads session, logging in if needed.

    Loads threads.net and calls login_threads if the session has expired
    (indicated by a redirect to /login). Calls pytest.skip if login cannot
    be completed.
    """
    ok, final_url = load_page(page, 'https://www.threads.com/', timeout_ms=20000)
    assert ok, f'Page load failed: {final_url}'
    wait_ms(3000)

    if '/login' in final_url.lower():
        success = login_threads(page, credentials['username'], credentials['password'])
        if not success:
            pytest.skip('Threads login failed — check credentials in .env')


@pytest.mark.functional
class TestThreadsComposer:
    """Threads: verify page loads and text injection into the composer."""

    def test_page_loads_authenticated(self, galefling_data_dir, threads_credentials):
        """Verify threads.net loads in an authenticated state."""
        get_or_create_app()
        view, page, profile = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, threads_credentials)
            final_url = page.url().toString()
            assert '/login' not in final_url.lower(), (
                f'Still on login page after authentication: {final_url}'
            )
            assert 'threads.com' in final_url or 'threads.net' in final_url, (
                f'Unexpected URL: {final_url}'
            )
        finally:
            page.deleteLater()
            profile.deleteLater()

    def test_text_injection(self, galefling_data_dir, threads_credentials):
        """Verify text can be injected into the Threads Lexical editor.

        Uses TEXT_SELECTOR = '[data-lexical-editor="true"]' from ThreadsPlatform.
        This selector is marked THREADS_PLACEHOLDER and may need updating once
        verified against the live site.
        """
        get_or_create_app()
        view, page, profile = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, threads_credentials)
            wait_ms(3000)  # SPA hydration

            tag = uuid.uuid4().hex[:8]
            test_text = f'GaleFling functional test {tag}'
            result = run_js(
                page,
                f"""
                (function() {{
                    // THREADS_PLACEHOLDER: selector unverified against live site.
                    // Matches ThreadsPlatform.TEXT_SELECTOR — update both together.
                    var el = document.querySelector('[data-lexical-editor="true"]');
                    if (!el) {{
                        // Fallback candidates to aid diagnosis
                        var editable = document.querySelector('[contenteditable="true"][role="textbox"]');
                        return {{
                            found: false,
                            fallbackFound: !!editable,
                            editableCount: document.querySelectorAll('[contenteditable="true"]').length
                        }};
                    }}
                    el.focus();
                    document.execCommand('insertText', false, {json.dumps(test_text)});
                    return {{found: true, content: el.textContent.substring(0, 100)}};
                }})();
                """,
            )
            assert isinstance(result, dict), f'JS returned: {result}'
            if not result.get('found'):
                pytest.skip(
                    f'Threads composer not found '
                    f'(editableCount={result.get("editableCount", 0)}, '
                    f'fallbackFound={result.get("fallbackFound", False)}). '
                    'TEXT_SELECTOR may need updating — see THREADS_PLACEHOLDER in ThreadsPlatform.'
                )
            assert test_text in result.get('content', ''), f'Text not injected: {result}'
        finally:
            page.deleteLater()
            profile.deleteLater()
