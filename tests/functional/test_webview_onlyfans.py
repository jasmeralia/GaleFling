"""Functional tests for OnlyFans WebView posting.

OnlyFans composer requires click interaction to expand. Session expiry is
detected via inline login form detection (OnlyFans does not redirect to /login).

Requires GALEFLING_DATA_DIR in .env with a valid OnlyFans session (onlyfans_1).
"""

import json
import os
import uuid

import pytest

from tests.functional.webview_helpers import (
    create_webview,
    get_or_create_app,
    has_cookie_db,
    load_page,
    run_js,
    wait_ms,
)

ACCOUNT_ID = 'onlyfans_1'


def _skip_if_no_session(data_dir):
    if not has_cookie_db(data_dir, ACCOUNT_ID):
        pytest.skip('No OnlyFans cookie database found')


@pytest.mark.functional
class TestOnlyFansComposer:
    """OnlyFans: verify page loads and attempt composer interaction."""

    def test_page_loads_authenticated(self, galefling_data_dir):
        """Verify OnlyFans home page loads without login redirect."""
        _skip_if_no_session(galefling_data_dir)
        get_or_create_app()
        view, page, profile = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            ok, final_url = load_page(page, 'https://onlyfans.com/', timeout_ms=20000)
            assert ok, f'Page load failed: {final_url}'
            if '/login' in final_url.lower():
                pytest.fail(f'OnlyFans session expired — redirected to login: {final_url}')
            wait_ms(5000)

            result = run_js(
                page,
                """
                (function() {
                    // OnlyFans shows a login form inline at / when logged out
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
            if result.get('hasLoginForm'):
                pytest.fail(
                    'OnlyFans session expired — login form present at home page '
                    '(re-authenticate via the GaleFling app)'
                )
        finally:
            page.deleteLater()
            profile.deleteLater()

    def test_composer_accessible(self, galefling_data_dir):
        """Check if the composer is present and attempt text injection."""
        _skip_if_no_session(galefling_data_dir)
        get_or_create_app()
        view, page, profile = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            ok, final_url = load_page(page, 'https://onlyfans.com/', timeout_ms=20000)
            assert ok, f'Page load failed: {final_url}'
            if '/login' in final_url.lower():
                pytest.fail(f'OnlyFans session expired — redirected to login: {final_url}')
            wait_ms(5000)

            # Detect inline login form (OnlyFans serves it at / without redirecting)
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
                pytest.fail(
                    'OnlyFans session expired — login form present at home page '
                    '(re-authenticate via the GaleFling app)'
                )
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
