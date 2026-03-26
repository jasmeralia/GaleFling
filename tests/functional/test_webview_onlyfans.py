"""Functional tests for OnlyFans WebView posting.

OnlyFans composer requires click interaction to expand. Session expiry is
detected via inline login form detection (OnlyFans does not redirect to /login).

Requires GALEFLING_DATA_DIR and ONLYFANS_EMAIL / ONLYFANS_PASSWORD in .env.
If ONLYFANS_TOTP_SECRET is also set, it is used to satisfy 2FA prompts
automatically. If the session cookie is still valid the login flow is skipped.
"""

import json
import os
import uuid

import pytest

from tests.functional.webview_helpers import (
    create_webview,
    get_or_create_app,
    load_page,
    login_onlyfans,
    run_js,
    wait_ms,
)

ACCOUNT_ID = 'onlyfans_1'


def _ensure_session(page, credentials: dict) -> None:
    """Verify we have a valid OnlyFans session, logging in if needed.

    Loads the OnlyFans home page, checks for the inline login form, and
    calls login_onlyfans if the session has expired. Calls pytest.skip if
    login cannot be completed.
    """
    ok, final_url = load_page(page, 'https://onlyfans.com/', timeout_ms=20000)
    assert ok, f'Page load failed: {final_url}'

    # OnlyFans uses Vue.js — wait for the SPA + Cloudflare to hydrate before
    # checking whether the login form is present.
    wait_ms(8000)

    login_check = run_js(
        page,
        """
        (function() {
            return !!document.querySelector(
                '.b-loginreg__form, .b-login-wrapper, input[type="password"]'
            );
        })();
        """,
    )

    if login_check:
        success = login_onlyfans(
            page,
            credentials['email'],
            credentials['password'],
            credentials.get('totp_secret'),
        )
        if not success:
            pytest.skip('OnlyFans login failed — check credentials or TOTP secret in .env')


@pytest.mark.functional
class TestOnlyFansComposer:
    """OnlyFans: verify page loads and attempt composer interaction."""

    def test_page_loads_authenticated(self, galefling_data_dir, onlyfans_credentials):
        """Verify OnlyFans home page loads in an authenticated state."""
        get_or_create_app()
        view, page, profile = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, onlyfans_credentials)

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
            page.deleteLater()
            profile.deleteLater()

    def test_composer_accessible(self, galefling_data_dir, onlyfans_credentials):
        """Check if the composer is present and attempt text injection."""
        get_or_create_app()
        view, page, profile = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, onlyfans_credentials)
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
                pytest.skip(
                    f'OnlyFans composer not found after click attempt '
                    f'(platform={platform}, '
                    f'editables={result.get("editableCount", 0)}). '
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
            page.deleteLater()
            profile.deleteLater()
