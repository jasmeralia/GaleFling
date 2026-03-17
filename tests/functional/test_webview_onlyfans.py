"""Functional tests for OnlyFans WebView posting.

OnlyFans composer requires click interaction to expand, so full text injection
is not possible in offscreen mode. These tests verify session authentication only.

Requires GALEFLING_DATA_DIR in .env with a valid OnlyFans session (onlyfans_1).
"""

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
    """OnlyFans: verify page loads (composer not accessible in offscreen mode)."""

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
                    return {
                        title: document.title,
                        hasBody: document.body.innerHTML.length > 100,
                        composerFound: !!document.querySelector(
                            'div[contenteditable="true"].b-make-post__text'
                        )
                    };
                })();
                """,
            )
            assert isinstance(result, dict)
            assert result.get('hasBody'), 'Page body is empty'
            if not result.get('composerFound'):
                pytest.skip(
                    'OnlyFans composer not accessible in offscreen mode '
                    '(requires click interaction to expand)'
                )
        finally:
            page.deleteLater()
            profile.deleteLater()
