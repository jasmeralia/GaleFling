"""Functional tests for Fansly WebView posting.

Tests text injection into the Fansly composer. Full submission is not automatable
in offscreen mode because Fansly's SPA renders submit buttons dynamically.

Requires GALEFLING_DATA_DIR in .env with a valid Fansly session (fansly_1).
"""

import json
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

ACCOUNT_ID = 'fansly_1'


def _skip_if_no_session(data_dir):
    if not has_cookie_db(data_dir, ACCOUNT_ID):
        pytest.skip('No Fansly cookie database found')


@pytest.mark.functional
class TestFanslyTextInjection:
    """Fansly text injection: verify text can be entered into the composer."""

    def test_composer_loads(self, galefling_data_dir):
        """Verify the Fansly home/composer page loads without login redirect."""
        _skip_if_no_session(galefling_data_dir)
        get_or_create_app()
        view, page, profile = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            ok, final_url = load_page(page, 'https://fansly.com/', timeout_ms=20000)
            assert ok, f'Page load failed: {final_url}'
            assert '/login' not in final_url.lower(), f'Session expired: {final_url}'
        finally:
            page.deleteLater()
            profile.deleteLater()

    def test_text_injection(self, galefling_data_dir):
        """Verify text can be injected into the Fansly textarea."""
        _skip_if_no_session(galefling_data_dir)
        get_or_create_app()
        view, page, profile = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            ok, _ = load_page(page, 'https://fansly.com/', timeout_ms=20000)
            assert ok
            wait_ms(5000)  # Cloudflare + SPA hydration

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
