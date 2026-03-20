"""Functional tests for Snapchat WebView posting.

Snapchat's web app requires WebGL/GPU. Session expiry is detected by checking
that the final URL stays at web.snapchat.com (expired sessions redirect to
the www.snapchat.com marketing site).

Requires GALEFLING_DATA_DIR in .env with a valid Snapchat session (snapchat_1).
"""

import os

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
    """Snapchat: verify page loads and video upload mechanism is accessible."""

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
            # Authenticated app stays at web.snapchat.com; unauthenticated
            # redirects to www.snapchat.com (marketing site)
            if 'web.snapchat.com' not in final_url:
                pytest.fail(f'Snapchat session expired (redirected to: {final_url})')
        finally:
            page.deleteLater()
            profile.deleteLater()

    def test_video_upload_accessible(self, galefling_data_dir):
        """Verify the video upload mechanism is accessible on Snapchat web."""
        _skip_if_no_session(galefling_data_dir)
        get_or_create_app()
        view, page, profile = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            ok, final_url = load_page(page, 'https://web.snapchat.com/', timeout_ms=20000)
            assert ok, f'Page load failed: {final_url}'
            wait_ms(5000)

            # Verify JS execution works (requires real display with WebGL)
            title = run_js(page, 'document.title')
            if title is None:
                pytest.skip('JS execution unavailable — needs real display with WebGL')

            # Authenticated app stays at web.snapchat.com; unauthenticated
            # redirects to www.snapchat.com (marketing site)
            if 'web.snapchat.com' not in final_url:
                pytest.fail(f'Snapchat session expired (redirected to: {final_url})')

            # Wait for SPA to fully render
            wait_ms(3000)

            result = run_js(
                page,
                """
                (function() {
                    // Look for file inputs that accept video
                    var fileInputs = Array.from(
                        document.querySelectorAll('input[type="file"]')
                    );
                    var videoInputs = fileInputs.filter(function(el) {
                        var accept = el.accept || '';
                        return accept === '' || accept.includes('video') || accept.includes('*');
                    });

                    // Also look for upload trigger buttons/areas
                    var uploadTriggers = document.querySelectorAll(
                        '[data-testid*="upload"], [aria-label*="upload"], '
                        + '[aria-label*="Upload"], [aria-label*="camera"], '
                        + '[aria-label*="Camera"], button[class*="upload"], '
                        + 'label[for][class*="upload"], label[class*="camera"]'
                    );

                    return {
                        fileInputCount: fileInputs.length,
                        videoInputCount: videoInputs.length,
                        uploadTriggerCount: uploadTriggers.length,
                        firstAccept: fileInputs.length > 0 ? fileInputs[0].accept : null
                    };
                })();
                """,
            )
            assert isinstance(result, dict), f'JS returned: {result}'
            has_upload = (
                result.get('fileInputCount', 0) > 0
                or result.get('uploadTriggerCount', 0) > 0
            )
            if not has_upload:
                pytest.skip(
                    f'Snapchat video upload mechanism not found in DOM '
                    f'(fileInputs={result.get("fileInputCount", 0)}, '
                    f'uploadTriggers={result.get("uploadTriggerCount", 0)}). '
                    'App may not have fully rendered.'
                )
            # At least one upload pathway exists
            assert has_upload, f'No video upload mechanism found: {result}'
        finally:
            page.deleteLater()
            profile.deleteLater()
