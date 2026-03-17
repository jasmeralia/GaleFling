"""Functional tests for Snapchat WebView posting.

Snapchat's web app depends on WebGL/GPU. In offscreen mode (no display) JS
execution fails. With a real display (WSLg, Xvfb, native X) the full app loads.

Requires GALEFLING_DATA_DIR in .env with a valid Snapchat session (snapchat_1).
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

ACCOUNT_ID = 'snapchat_1'


def _skip_if_no_session(data_dir):
    if not has_cookie_db(data_dir, ACCOUNT_ID):
        pytest.skip('No Snapchat cookie database found')


@pytest.mark.functional
class TestSnapchatComposer:
    """Snapchat: verify page loads, check JS execution, attempt text injection."""

    def test_page_loads(self, galefling_data_dir):
        """Verify Snapchat web loads and JS executes."""
        _skip_if_no_session(galefling_data_dir)
        get_or_create_app()
        view, page, profile = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            ok, final_url = load_page(page, 'https://web.snapchat.com/', timeout_ms=20000)
            assert ok, f'Page load failed: {final_url}'
            wait_ms(5000)

            result = run_js(page, 'document.title')
            if result is None:
                platform = os.environ.get('QT_QPA_PLATFORM', 'default')
                pytest.skip(
                    f'Snapchat JS execution failed (platform={platform}). '
                    'Requires a real display with WebGL — try running with '
                    'DISPLAY=:0 or xvfb-run.'
                )
            if '/accounts/login' in final_url.lower():
                pytest.fail(f'Snapchat session expired: {final_url}')
        finally:
            page.deleteLater()
            profile.deleteLater()

    def test_text_injection(self, galefling_data_dir):
        """Verify text can be injected into the Snapchat composer."""
        _skip_if_no_session(galefling_data_dir)
        get_or_create_app()
        view, page, profile = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            ok, final_url = load_page(page, 'https://web.snapchat.com/', timeout_ms=20000)
            assert ok, f'Page load failed: {final_url}'
            wait_ms(5000)

            # Verify JS execution works
            title = run_js(page, 'document.title')
            if title is None:
                pytest.skip('JS execution unavailable — needs real display')

            if '/accounts/login' in final_url.lower():
                pytest.fail(f'Snapchat session expired: {final_url}')

            # Look for composer elements
            wait_ms(3000)
            tag = uuid.uuid4().hex[:8]
            test_text = f'GaleFling functional test {tag}'
            result = run_js(
                page,
                f"""
                (function() {{
                    // Snapchat uses contenteditable divs for text input
                    var editors = document.querySelectorAll(
                        '[contenteditable="true"], textarea, input[type="text"]'
                    );
                    if (editors.length === 0) return {{found: false, editorCount: 0}};
                    var el = editors[0];
                    el.focus();
                    if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {{
                        el.value = {json.dumps(test_text)};
                        el.dispatchEvent(new Event('input', {{bubbles: true}}));
                    }} else {{
                        document.execCommand('insertText', false, {json.dumps(test_text)});
                    }}
                    return {{
                        found: true,
                        editorCount: editors.length,
                        tagName: el.tagName,
                        content: (el.value || el.textContent || '').substring(0, 100)
                    }};
                }})();
                """,
            )
            assert isinstance(result, dict), f'JS returned: {result}'
            if not result.get('found'):
                pytest.skip('Snapchat composer element not found in DOM')
            assert test_text in result.get('content', ''), f'Text not injected: {result}'
        finally:
            page.deleteLater()
            profile.deleteLater()
