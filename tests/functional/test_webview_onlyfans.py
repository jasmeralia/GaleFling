"""Functional tests for OnlyFans WebView posting.

OnlyFans support is disabled in the product (`ONLYFANS_SPECS.available = False`),
paused 2026-08-16 at Rin's request: OnlyFans is aggressive about detecting and
banning automation, and supports post scheduling — a stronger automation signal
than a one-off manual post. See `docs/platforms/ONLYFANS.md`.

These tests are retained for reference but are **skipped by default** so they do
not affect routine functional runs, or exercise automation against the live
platform while support is paused. To opt in:

    pytest tests/functional/test_webview_onlyfans.py --run-disabled-platforms -v

OnlyFans composer requires click interaction to expand. Session expiry is
detected via inline login form detection (OnlyFans does not redirect to /login).

Requires a valid session in ``GALEFLING_DATA_DIR/webprofiles/onlyfans_1/`` or
``ONLYFANS_AUTH_JSON`` pointing at an exported auth.json file. Automated
username/password login is not supported — see docs/platforms/ONLYFANS_SESSION_IMPORT.md.
"""

import json
import os

import pytest

from src.platforms.onlyfans import OnlyFansPlatform
from tests.functional.conftest import ONLYFANS_ACCOUNT_ID, fail_or_skip, mutating_post_tag
from tests.functional.webview_helpers import (
    close_webview,
    create_webview,
    get_or_create_app,
    load_page,
    run_js,
    wait_ms,
)

pytestmark = [pytest.mark.disabled_platform]


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
        view, page, platform = create_webview(galefling_data_dir, ONLYFANS_ACCOUNT_ID)
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
            close_webview(view, page, platform)

    def test_composer_accessible(self, galefling_data_dir, onlyfans_session):
        """Expand the composer, then inject through OnlyFansPlatform._inject_text().

        Injection goes through the shipped platform so a regression in ``_inject_text``
        or ``TEXT_SELECTOR`` fails here. The composer selector is read from the platform
        rather than copied, for the same reason (Phase 5).
        """
        assert onlyfans_session == ONLYFANS_ACCOUNT_ID
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ONLYFANS_ACCOUNT_ID)
        try:
            _ensure_authenticated_page(page)
            wait_ms(5000)

            selector = json.dumps(OnlyFansPlatform.TEXT_SELECTOR)

            # The composer may need a click to expand before it exists in the DOM.
            result = run_js(
                page,
                f"""
                (function() {{
                    var composer = document.querySelector({selector});
                    if (composer) return {{composerFound: true, clicked: false}};

                    var placeholder = document.querySelector(
                        '.b-make-post__placeholder, .b-make-post, '
                        + '[data-post-create], .b-write-post, '
                        + '.post-create, .create-post'
                    );
                    if (placeholder) {{
                        placeholder.click();
                        return {{
                            composerFound: false,
                            clicked: true,
                            selector: placeholder.className
                        }};
                    }}

                    var candidates = Array.from(document.querySelectorAll(
                        'div[class*="make-post"], div[class*="write-post"], '
                        + 'div[class*="create-post"], div[class*="compose"]'
                    ));
                    if (candidates.length > 0) {{
                        candidates[0].click();
                        return {{
                            composerFound: false,
                            clicked: true,
                            selector: candidates[0].className
                        }};
                    }}

                    return {{
                        composerFound: false,
                        clicked: false,
                        editableCount: document.querySelectorAll('[contenteditable="true"]').length
                    }};
                }})();
                """,
            )
            assert isinstance(result, dict)

            if result.get('clicked') and not result.get('composerFound'):
                wait_ms(2000)
                recheck = run_js(
                    page,
                    f"""
                    (function() {{
                        return {{
                            composerFound: !!document.querySelector({selector}),
                            editableCount: document.querySelectorAll(
                                '[contenteditable="true"]'
                            ).length
                        }};
                    }})();
                    """,
                )
                if isinstance(recheck, dict):
                    result = recheck

            if not result.get('composerFound'):
                qt_platform = os.environ.get('QT_QPA_PLATFORM', 'default')
                fail_or_skip(
                    f'OnlyFans composer not found after click attempt '
                    f'(platform={qt_platform}, '
                    f'editables={result.get("editableCount", 0)}, '
                    f'selector={OnlyFansPlatform.TEXT_SELECTOR}). '
                    'May require full browser rendering.'
                )

            test_text = mutating_post_tag()
            platform._inject_text(test_text)
            wait_ms(1000)

            inject_result = run_js(
                page,
                f"""
                (function() {{
                    var el = document.querySelector({selector});
                    if (!el) return {{found: false}};
                    return {{
                        found: true,
                        content: (el.textContent || el.value || '').substring(0, 100)
                    }};
                }})();
                """,
            )
            assert isinstance(inject_result, dict), f'JS returned: {inject_result}'
            assert inject_result.get('found'), 'Composer disappeared after detection'
            assert test_text in inject_result.get('content', ''), (
                f'Text not injected: {inject_result}'
            )
        finally:
            close_webview(view, page, platform)
