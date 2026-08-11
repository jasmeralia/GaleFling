"""Functional tests for Snapchat WebView posting.

Snapchat's web app requires WebGL/GPU. Session expiry is detected by checking
that the final URL stays at web.snapchat.com (expired sessions redirect to
accounts.snapchat.com).

Requires GALEFLING_DATA_DIR and SNAPCHAT_USERNAME / SNAPCHAT_PASSWORD in .env.
If the session cookie is still valid the login flow is skipped.
"""

import json
import os
import re

import pytest

from tests.functional.conftest import fail_or_skip
from tests.functional.webview_helpers import (
    create_webview,
    get_or_create_app,
    load_page,
    login_snapchat,
    run_js,
    wait_ms,
)

ACCOUNT_ID = 'snapchat_1'


# A rendered Snapchat app has thousands of nodes; an error page has a handful.
_MIN_RENDERED_NODES = 50
_SNAPCHAT_WEB_HOSTS = ('web.snapchat.com', 'www.snapchat.com/web')


def _is_snapchat_web(url: str) -> bool:
    """Return True if *url* is the Snapchat web app (either domain variant)."""
    return any(s in url for s in _SNAPCHAT_WEB_HOSTS)


def _assert_app_rendered(page) -> None:
    """Fail unless the Snapchat web application actually rendered.

    Snapchat serves error pages from the web-app URL itself — a rate-limited
    request returns an HTTP status code as the document title with a handful of
    DOM nodes. Those satisfy a plain "URL looks right, JS runs" check, so
    without this the suite reports a throttled session as a working one and
    every DOM assertion afterwards silently measures the error page instead.
    """
    state = run_js(
        page,
        """
        JSON.stringify({
            title: document.title,
            nodes: document.querySelectorAll('*').length
        })
        """,
    )
    if not state:
        return
    parsed = json.loads(state)
    title = (parsed.get('title') or '').strip()
    nodes = parsed.get('nodes') or 0
    if re.fullmatch(r'\d{3}', title) or nodes < _MIN_RENDERED_NODES:
        fail_or_skip(
            f'Snapchat served an error page instead of the web app '
            f'(title={title!r}, nodes={nodes}). A 429 title means the session or '
            f'account is being rate limited — wait before retrying.'
        )


def _ensure_session(page, credentials: dict) -> None:
    """Verify we have a valid Snapchat session, logging in if needed.

    Loads web.snapchat.com and calls login_snapchat if the session has
    expired. Reports a strict-mode failure if login cannot be completed.

    Note: Snapchat now redirects web.snapchat.com → www.snapchat.com/web/;
    both are accepted as authenticated endpoints.
    """
    ok, final_url = load_page(page, 'https://web.snapchat.com/', timeout_ms=20000)
    assert ok, f'Page load failed: {final_url}'
    wait_ms(5000)

    # Only the settled URL indicates whether a session exists.  A logged-out
    # load still *finishes* on web.snapchat.com and is bounced to the marketing
    # page by client-side JS afterwards, so trusting the load-time URL made this
    # check pass while logged out and skip the login entirely.
    if not _is_snapchat_web(page.url().toString()):
        success, reason = login_snapchat(page, credentials['username'], credentials['password'])
        if not success:
            fail_or_skip(f'Snapchat login failed — {reason}')


@pytest.mark.functional
@pytest.mark.non_mutating
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
                fail_or_skip(
                    f'Snapchat JS execution failed (platform={platform}). '
                    'Requires a real display with WebGL — try running with '
                    'DISPLAY=:0 or xvfb-run.'
                )
            current_url = page.url().toString()
            if not _is_snapchat_web(current_url):
                # Snapchat may redirect away from /web when WebGL is unavailable.
                qt_platform = os.environ.get('QT_QPA_PLATFORM', 'default')
                fail_or_skip(
                    f'Snapchat redirected away from web app (platform={qt_platform}, '
                    f'url={current_url}). Requires a real display with WebGL.'
                )
            _assert_app_rendered(page)
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
                fail_or_skip('JS execution unavailable — needs real display with WebGL')

            # Wait for SPA to fully render
            wait_ms(3000)
            _assert_app_rendered(page)

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
                fail_or_skip(
                    f'Snapchat video upload mechanism not found in DOM '
                    f'(fileInputs={result.get("fileInputCount", 0)}, '
                    f'uploadTriggers={result.get("uploadTriggerCount", 0)}). '
                    'App may not have fully rendered.'
                )
            assert has_upload, f'No video upload mechanism found: {result}'
        finally:
            page.deleteLater()
            profile.deleteLater()
