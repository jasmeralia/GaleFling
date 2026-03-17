"""Functional tests for Snapchat WebView posting.

Snapchat's web app depends on WebGL/GPU which is unavailable in offscreen mode.
These tests verify page loading and detect whether JS execution is possible.

Requires GALEFLING_DATA_DIR in .env with a valid Snapchat session (snapchat_1).
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

ACCOUNT_ID = 'snapchat_1'


def _skip_if_no_session(data_dir):
    if not has_cookie_db(data_dir, ACCOUNT_ID):
        pytest.skip('No Snapchat cookie database found')


@pytest.mark.functional
class TestSnapchatComposer:
    """Snapchat: verify page loads (JS execution limited in offscreen mode)."""

    def test_page_loads(self, galefling_data_dir):
        """Verify Snapchat web loads and check if JS executes."""
        _skip_if_no_session(galefling_data_dir)
        get_or_create_app()
        view, page, profile = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            ok, final_url = load_page(page, 'https://web.snapchat.com/', timeout_ms=20000)
            assert ok, f'Page load failed: {final_url}'
            wait_ms(5000)

            result = run_js(page, 'document.title')
            if result is None:
                pytest.skip(
                    'Snapchat JS execution fails in offscreen mode '
                    '(requires WebGL/GPU which is unavailable)'
                )
            if '/accounts/login' in final_url.lower():
                pytest.fail(f'Snapchat session expired: {final_url}')
        finally:
            page.deleteLater()
            profile.deleteLater()
