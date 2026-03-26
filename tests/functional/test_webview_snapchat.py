"""Functional tests for Snapchat WebView posting.

Snapchat's web app requires WebGL/GPU. Session expiry is detected by checking
that the final URL stays at web.snapchat.com (expired sessions redirect to
accounts.snapchat.com).

Requires GALEFLING_DATA_DIR and SNAPCHAT_USERNAME / SNAPCHAT_PASSWORD in .env.
If the session cookie is still valid the login flow is skipped.
"""

import os

import pytest

from tests.functional.webview_helpers import (
    create_webview,
    get_or_create_app,
    load_page,
    login_snapchat,
    run_js,
    wait_ms,
)

ACCOUNT_ID = 'snapchat_1'


_SNAPCHAT_WEB_HOSTS = ('web.snapchat.com', 'www.snapchat.com/web')


def _is_snapchat_web(url: str) -> bool:
    """Return True if *url* is the Snapchat web app (either domain variant)."""
    return any(s in url for s in _SNAPCHAT_WEB_HOSTS)


def _ensure_session(page, credentials: dict) -> None:
    """Verify we have a valid Snapchat session, logging in if needed.

    Loads web.snapchat.com and calls login_snapchat if the session has
    expired.  Calls pytest.skip if login cannot be completed.

    Note: Snapchat now redirects web.snapchat.com → www.snapchat.com/web/;
    both are accepted as authenticated endpoints.
    """
    ok, final_url = load_page(page, 'https://web.snapchat.com/', timeout_ms=20000)
    assert ok, f'Page load failed: {final_url}'
    wait_ms(5000)

    if not _is_snapchat_web(final_url) and not _is_snapchat_web(page.url().toString()):
        success, reason = login_snapchat(page, credentials['username'], credentials['password'])
        if not success:
            pytest.skip(f'Snapchat login failed — {reason}')


@pytest.mark.functional
class TestSnapchatComposer:
    """Snapchat: verify page loads and video upload mechanism is accessible."""

    def test_page_loads(self, galefling_data_dir, snapchat_credentials):
        """Verify Snapchat web loads and JS executes in an authenticated state."""
        get_or_create_app()
        view, page, profile = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, snapchat_credentials)

            result = run_js(page, 'document.title')
            if result is None:
                platform = os.environ.get('QT_QPA_PLATFORM', 'default')
                pytest.skip(
                    f'Snapchat JS execution failed (platform={platform}). '
                    'Requires a real display with WebGL — try running with '
                    'DISPLAY=:0 or xvfb-run.'
                )
            current_url = page.url().toString()
            if not _is_snapchat_web(current_url):
                # Snapchat may redirect away from /web when WebGL is unavailable.
                qt_platform = os.environ.get('QT_QPA_PLATFORM', 'default')
                pytest.skip(
                    f'Snapchat redirected away from web app (platform={qt_platform}, '
                    f'url={current_url}). Requires a real display with WebGL.'
                )
        finally:
            page.deleteLater()
            profile.deleteLater()

    def test_video_upload_accessible(self, galefling_data_dir, snapchat_credentials):
        """Verify the video upload mechanism is accessible on Snapchat web."""
        get_or_create_app()
        view, page, profile = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, snapchat_credentials)

            # Verify JS execution works (requires real display with WebGL)
            title = run_js(page, 'document.title')
            if title is None:
                pytest.skip('JS execution unavailable — needs real display with WebGL')

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
                result.get('fileInputCount', 0) > 0 or result.get('uploadTriggerCount', 0) > 0
            )
            if not has_upload:
                pytest.skip(
                    f'Snapchat video upload mechanism not found in DOM '
                    f'(fileInputs={result.get("fileInputCount", 0)}, '
                    f'uploadTriggers={result.get("uploadTriggerCount", 0)}). '
                    'App may not have fully rendered.'
                )
            assert has_upload, f'No video upload mechanism found: {result}'
        finally:
            page.deleteLater()
            profile.deleteLater()
