"""Functional tests for OnlyFans WebView posting.

OnlyFans composer requires click interaction to expand. Session expiry is
detected via inline login form detection (OnlyFans does not redirect to /login).

Requires a valid session in ``GALEFLING_DATA_DIR/webprofiles/onlyfans_1/`` or
``ONLYFANS_AUTH_JSON`` pointing at an exported auth.json file. Automated
username/password login is not supported — see docs/platforms/ONLYFANS_SESSION_IMPORT.md.
"""

import json
import os
import uuid

import pytest

from tests.functional.conftest import ONLYFANS_ACCOUNT_ID, fail_or_skip
from tests.functional.webview_helpers import (
    close_webview,
    create_webview,
    get_or_create_app,
    load_page,
    run_js,
    wait_ms,
)


def _login_form_present(page) -> bool:
    """Return True when OnlyFans is showing its inline login form."""
    result = run_js(
        page,
        """
        (function() {
            return !!document.querySelector(
                '.b-loginreg__form, .b-login-wrapper, input[type="password"]'
            );
        })();
        """,
    )
    return bool(result)


def _ensure_authenticated_page(page) -> None:
    """Load OnlyFans and fail/skip when the persisted session is not active."""
    ok, final_url = load_page(page, 'https://onlyfans.com/', timeout_ms=20000)
    assert ok, f'Page load failed: {final_url}'

    # OnlyFans uses Vue.js — wait for the SPA + Cloudflare to hydrate before
    # checking whether the login form is present.
    wait_ms(8000)

    if _login_form_present(page):
        fail_or_skip(
            'OnlyFans login form present — session expired or missing. '
            'Import auth.json via Settings or set ONLYFANS_AUTH_JSON in .env '
            '(see docs/platforms/ONLYFANS_SESSION_IMPORT.md).'
        )


@pytest.mark.functional
@pytest.mark.non_mutating
class TestOnlyFansComposer:
    """OnlyFans: verify page loads and attempt composer interaction."""

    def test_page_loads_authenticated(self, galefling_data_dir, onlyfans_session):
        """Verify OnlyFans home page loads in an authenticated state."""
        assert onlyfans_session == ONLYFANS_ACCOUNT_ID
        get_or_create_app()
        view, page, profile = create_webview(galefling_data_dir, ONLYFANS_ACCOUNT_ID)
        try:
            _ensure_authenticated_page(page)

            result = run_js(
                page,
                """
                (function() {
                    var loginForm = document.querySelector(
                        '.b-loginreg__form, .b-login-wrapper, input[type="email"], input[type="password"]'
                    );
                    return {
                        title: document.title,
                        hasBody: document.body.innerHTML.length > 100,
                        hasLoginForm: !!loginForm
                    };
                })();
                """,
            )
            assert isinstance(result, dict)
            assert result.get('hasBody'), 'Page body is empty'
            assert not result.get('hasLoginForm'), (
                'OnlyFans login form still present after authentication'
            )
        finally:
            close_webview(view, page, profile)

    def test_composer_accessible(self, galefling_data_dir, onlyfans_session):
        """Check if the composer is present and attempt text injection."""
        assert onlyfans_session == ONLYFANS_ACCOUNT_ID
        get_or_create_app()
        view, page, profile = create_webview(galefling_data_dir, ONLYFANS_ACCOUNT_ID)
        try:
            _ensure_authenticated_page(page)
            wait_ms(5000)

            # Try to find the composer — it may need a click to expand
            result = run_js(
                page,
                """
                (function() {
                    var composer = document.querySelector(
                        'div[contenteditable="true"].b-make-post__text'
                    );
                    if (composer) return {composerFound: true, clicked: false};

                    // Composer not in DOM yet — click the placeholder/compose area to expand it
                    var placeholder = document.querySelector(
                        '.b-make-post__placeholder, .b-make-post, '
                        + '[data-post-create], .b-write-post, '
                        + '.post-create, .create-post'
                    );
                    if (placeholder) {
                        placeholder.click();
                        return {composerFound: false, clicked: true, selector: placeholder.className};
                    }

                    // Try clicking any element that looks like a compose trigger
                    var candidates = Array.from(document.querySelectorAll(
                        'div[class*="make-post"], div[class*="write-post"], '
                        + 'div[class*="create-post"], div[class*="compose"]'
                    ));
                    if (candidates.length > 0) {
                        candidates[0].click();
                        return {composerFound: false, clicked: true, selector: candidates[0].className};
                    }

                    return {
                        composerFound: false,
                        clicked: false,
                        editableCount: document.querySelectorAll('[contenteditable="true"]').length
                    };
                })();
                """,
            )
            assert isinstance(result, dict)

            if result.get('clicked') and not result.get('composerFound'):
                # Clicked the compose area — wait for the editor to appear
                wait_ms(2000)
                recheck = run_js(
                    page,
                    """
                    (function() {
                        var composer = document.querySelector(
                            'div[contenteditable="true"].b-make-post__text'
                        );
                        return {
                            composerFound: !!composer,
                            editableCount: document.querySelectorAll(
                                '[contenteditable="true"]'
                            ).length
                        };
                    })();
                    """,
                )
                if isinstance(recheck, dict):
                    result = recheck

            if not result.get('composerFound'):
                platform = os.environ.get('QT_QPA_PLATFORM', 'default')
                fail_or_skip(
                    f'OnlyFans composer not found after click attempt '
                    f'(platform={platform}, '
                    f'editables={result.get("editableCount", 0)}, '
                    'selector=div[contenteditable="true"].b-make-post__text). '
                    'May require full browser rendering.'
                )

            # Composer found — inject text
            tag = uuid.uuid4().hex[:8]
            test_text = f'GaleFling functional test {tag}'
            inject_result = run_js(
                page,
                f"""
                (function() {{
                    var el = document.querySelector(
                        'div[contenteditable="true"].b-make-post__text'
                    );
                    if (!el) return {{found: false}};
                    el.focus();
                    document.execCommand('insertText', false, {json.dumps(test_text)});
                    return {{found: true, content: el.textContent.substring(0, 100)}};
                }})();
                """,
            )
            assert isinstance(inject_result, dict), f'JS returned: {inject_result}'
            assert inject_result.get('found'), 'Composer disappeared after detection'
            assert test_text in inject_result.get('content', ''), (
                f'Text not injected: {inject_result}'
            )
        finally:
            close_webview(view, page, profile)
