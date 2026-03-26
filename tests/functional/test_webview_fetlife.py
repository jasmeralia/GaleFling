"""Functional tests for FetLife WebView posting.

Tests the three FetLife composer types (text, picture, video):
- Text: inject text into ProseMirror editor, submit, capture post URL
- Picture: verify file input and upload button are present
- Video: verify file input and upload button are present

Requires GALEFLING_DATA_DIR and FETLIFE_EMAIL / FETLIFE_PASSWORD in .env.
If the session cookie is still valid the login flow is skipped.
"""

import json
import re
import uuid

import pytest

from tests.functional.webview_helpers import (
    create_webview,
    get_or_create_app,
    load_page,
    login_fetlife,
    run_js,
    wait_ms,
)

ACCOUNT_ID = 'fetlife_1'


def _ensure_session(page, credentials: dict) -> None:
    """Verify we have a valid FetLife session, logging in if needed.

    Navigates to the text composer page (which redirects to /login when the
    session is expired) and calls login_fetlife if authentication is required.
    Calls pytest.skip if login cannot be completed.
    """
    ok, final_url = load_page(page, 'https://fetlife.com/posts/new?source=Feed')
    if not ok:
        pytest.skip(f'FetLife page load failed: {final_url}')

    if '/login' in final_url.lower():
        success = login_fetlife(page, credentials['email'], credentials['password'])
        if not success:
            pytest.skip('FetLife login failed — check credentials in .env')
        # After login, navigate back to the composer
        ok, final_url = load_page(page, 'https://fetlife.com/posts/new?source=Feed')
        if not ok or '/login' in final_url.lower():
            pytest.skip('FetLife composer unreachable after login')


@pytest.mark.functional
class TestFetLifeTextPost:
    """FetLife text post: inject text, submit form, capture URL, delete."""

    def test_composer_loads(self, galefling_data_dir, fetlife_credentials):
        """Verify the text composer page loads in an authenticated state."""
        get_or_create_app()
        view, page, profile = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fetlife_credentials)
            final_url = page.url().toString()
            assert '/login' not in final_url.lower(), f'Redirected to login: {final_url}'
            assert 'posts/new' in final_url, f'Unexpected URL: {final_url}'
        finally:
            page.deleteLater()
            profile.deleteLater()

    def test_text_injection(self, galefling_data_dir, fetlife_credentials):
        """Verify text can be injected into the ProseMirror editor."""
        get_or_create_app()
        view, page, profile = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fetlife_credentials)
            wait_ms(2000)

            tag = uuid.uuid4().hex[:8]
            test_text = f'GaleFling functional test {tag}'
            result = run_js(
                page,
                f"""
                (function() {{
                    var el = document.querySelector('div.tiptap.ProseMirror[contenteditable="true"]');
                    if (!el) return {{found: false}};
                    el.focus();
                    document.execCommand('insertText', false, {json.dumps(test_text)});
                    return {{found: true, content: el.textContent.substring(0, 100)}};
                }})();
                """,
            )
            assert isinstance(result, dict), f'JS returned: {result}'
            assert result.get('found'), 'ProseMirror editor not found'
            assert test_text in result.get('content', ''), f'Text not injected: {result}'
        finally:
            page.deleteLater()
            profile.deleteLater()

    def test_text_post_submit_and_delete(self, galefling_data_dir, fetlife_credentials):
        """Submit a text post, capture the URL, then attempt deletion."""
        get_or_create_app()
        view, page, profile = create_webview(galefling_data_dir, ACCOUNT_ID)
        post_url = None
        try:
            _ensure_session(page, fetlife_credentials)
            wait_ms(3000)

            # Inject text
            tag = uuid.uuid4().hex[:8]
            test_text = f'GaleFling functional test {tag} — safe to delete'
            inject_result = run_js(
                page,
                f"""
                (function() {{
                    var el = document.querySelector('div.tiptap.ProseMirror[contenteditable="true"]');
                    if (!el) return {{found: false}};
                    el.focus();
                    document.execCommand('insertText', false, {json.dumps(test_text)});
                    el.dispatchEvent(new Event('input', {{bubbles: true}}));
                    return {{found: true, content: el.textContent.substring(0, 150)}};
                }})();
                """,
            )
            assert isinstance(inject_result, dict) and inject_result.get('found'), (
                f'Text injection failed: {inject_result}'
            )

            # Click "Express Yourself" submit button
            wait_ms(500)
            submit_result = run_js(
                page,
                """
                (function() {
                    var buttons = Array.from(document.querySelectorAll('button[type="submit"]'));
                    var btn = buttons.find(function(b) {
                        return b.textContent.trim().includes('Express Yourself');
                    });
                    if (!btn) return {clicked: false, reason: 'Button not found'};
                    if (btn.disabled) return {clicked: false, reason: 'Button disabled'};
                    btn.click();
                    return {clicked: true};
                })();
                """,
            )
            assert isinstance(submit_result, dict) and submit_result.get('clicked'), (
                f'Submit failed: {submit_result}'
            )

            # Wait for navigation after submit
            wait_ms(8000)
            post_url = page.url().toString()

            # Verify we navigated away from the composer (post was submitted)
            assert 'posts/new' not in post_url, f'Still on composer after submit: {post_url}'

            # Check if we landed on a specific post page or the posts feed
            specific_post = re.search(r'fetlife\.com/(?:users/\d+/)?posts/(\d+)', post_url)
            if specific_post:
                print(f'\n  FetLife post created: {post_url}')
                # Attempt deletion from the post page
                self._attempt_delete(page)
            else:
                # Redirected to feed — post was created but no direct URL captured
                print(f'\n  FetLife post submitted (redirected to: {post_url})')
                print('  Manual cleanup needed — check recent posts')

        finally:
            page.deleteLater()
            profile.deleteLater()

    @staticmethod
    def _attempt_delete(page):
        """Best-effort deletion of the current post page."""
        wait_ms(2000)
        delete_result = run_js(
            page,
            """
            (function() {
                var links = Array.from(document.querySelectorAll('a, button'));
                var deleteLink = links.find(function(el) {
                    var text = el.textContent.trim().toLowerCase();
                    return text === 'delete' || text === 'remove'
                        || text.includes('delete this');
                });
                if (deleteLink) {
                    deleteLink.click();
                    return {found: true, text: deleteLink.textContent.trim()};
                }
                var menuBtn = links.find(function(el) {
                    var label = (el.getAttribute('aria-label') || '').toLowerCase();
                    return label.includes('more') || label.includes('option')
                        || label.includes('menu');
                });
                if (menuBtn) {
                    menuBtn.click();
                    return {found: false, menu_opened: true};
                }
                return {found: false, menu_opened: false};
            })();
            """,
        )
        if (
            isinstance(delete_result, dict)
            and delete_result.get('menu_opened')
            and not delete_result.get('found')
        ):
            wait_ms(1000)
            delete_result2 = run_js(
                page,
                """
                (function() {
                    var items = Array.from(document.querySelectorAll(
                        'a, button, [role="menuitem"]'
                    ));
                    var del_item = items.find(function(el) {
                        return el.textContent.trim().toLowerCase().includes('delete');
                    });
                    if (del_item) { del_item.click(); return {clicked: true}; }
                    return {clicked: false};
                })();
                """,
            )
            if isinstance(delete_result2, dict) and delete_result2.get('clicked'):
                wait_ms(2000)
                run_js(
                    page,
                    """
                    var btn = document.querySelector(
                        'button[type="submit"], .confirm-delete, [data-confirm]'
                    );
                    if (btn) btn.click();
                    """,
                )
                wait_ms(2000)


@pytest.mark.functional
class TestFetLifePictureComposer:
    """FetLife picture composer: verify page loads and elements are present."""

    def test_picture_composer_loads(self, galefling_data_dir, fetlife_credentials):
        """Verify the picture composer loads with file input and submit button."""
        get_or_create_app()
        view, page, profile = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            # Establish session via the text composer (handles login redirect)
            _ensure_session(page, fetlife_credentials)

            # Now navigate to the picture composer
            ok, final_url = load_page(
                page, 'https://fetlife.com/pictures/new?source=Main+Navigation'
            )
            assert ok, f'Page load failed: {final_url}'
            assert '/login' not in final_url.lower(), f'Session expired: {final_url}'
            wait_ms(2000)

            result = run_js(
                page,
                """
                (function() {
                    var fileInput = document.querySelector(
                        'input[type="file"][name="picture[attachments]"]'
                    );
                    var submitBtn = Array.from(
                        document.querySelectorAll('button[type="submit"]')
                    ).find(function(b) {
                        return b.textContent.includes('Upload Your Picture');
                    });
                    return {
                        fileInputFound: !!fileInput,
                        fileInputAccept: fileInput ? fileInput.accept : null,
                        submitFound: !!submitBtn,
                        submitDisabled: submitBtn ? submitBtn.disabled : null
                    };
                })();
                """,
            )
            assert isinstance(result, dict), f'JS returned: {result}'
            assert result.get('fileInputFound'), 'File input not found'
            assert result.get('submitFound'), 'Upload button not found'
            assert 'image' in (result.get('fileInputAccept') or ''), (
                'File input does not accept images'
            )
        finally:
            page.deleteLater()
            profile.deleteLater()


@pytest.mark.functional
class TestFetLifeVideoComposer:
    """FetLife video composer: verify page loads and elements are present."""

    def test_video_composer_loads(self, galefling_data_dir, fetlife_credentials):
        """Verify the video composer loads with file input and submit button."""
        get_or_create_app()
        view, page, profile = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            # Establish session via the text composer (handles login redirect)
            _ensure_session(page, fetlife_credentials)

            # Now navigate to the video composer
            ok, final_url = load_page(page, 'https://fetlife.com/videos/new?source=Main+Navigation')
            assert ok, f'Page load failed: {final_url}'
            assert '/login' not in final_url.lower(), f'Session expired: {final_url}'
            wait_ms(2000)

            result = run_js(
                page,
                """
                (function() {
                    var fileInput = document.querySelector(
                        'input[type="file"][name="video[video]"]'
                    );
                    var submitBtn = Array.from(
                        document.querySelectorAll('button[type="submit"]')
                    ).find(function(b) {
                        return b.textContent.includes('Upload Your Video');
                    });
                    return {
                        fileInputFound: !!fileInput,
                        fileInputAccept: fileInput ? fileInput.accept : null,
                        submitFound: !!submitBtn,
                        submitDisabled: submitBtn ? submitBtn.disabled : null
                    };
                })();
                """,
            )
            assert isinstance(result, dict), f'JS returned: {result}'
            assert result.get('fileInputFound'), 'File input not found'
            assert result.get('submitFound'), 'Upload button not found'
            assert 'video' in (result.get('fileInputAccept') or ''), (
                'File input does not accept video'
            )
        finally:
            page.deleteLater()
            profile.deleteLater()
