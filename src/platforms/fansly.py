"""Fansly platform implementation using WebView."""

import json
from collections.abc import Callable

from src.core.logger import get_logger
from src.platforms.base_webview import BaseWebViewPlatform
from src.utils.constants import FANSLY_SPECS, PlatformSpecs


class FanslyPlatform(BaseWebViewPlatform):
    """Fansly posting via embedded WebView (Cloudflare-protected)."""

    LOGIN_URL = 'https://fansly.com/'
    COMPOSER_URL = 'https://fansly.com/home'
    TEXT_SELECTOR = 'textarea'
    # The composer's submit is a <div>Post</div>, not a button — it carries no
    # type=submit and no role=button, so a button-oriented lookup will not find it.
    # It only becomes usable once the textarea flips ng-invalid -> ng-valid.
    TEXT_SUBMIT_LABEL = 'Post'
    # Single multi-accept file input on the feed composer (images, video and audio).
    #
    # Writing to it directly does not attach anything: neither a synthetic
    # DataTransfer nor a picker-supplied selection reaches Fansly's uploader, which
    # never consults this input's change event.  Media attaches only by driving the
    # composer's own dropdown — image icon > "Upload New" > Upload media modal — so
    # that Fansly's uploader is in the call stack.  See docs/platforms/FANSLY.md.
    MEDIA_FILE_SELECTOR = 'input[type="file"]'
    # Fansly greets a session with <app-web-push-enable-modal> ("Enable Push
    # Notifications") behind a full-page backdrop.  The backdrop covers the whole
    # composer and swallows the first click anywhere on the page — including the
    # user's own.  Dismissed after load by dismiss_blocking_overlay().
    #
    # The dialog is a *sibling* of the backdrop, not a child, and offers "Yes, Enable"
    # directly above "Maybe Later" — 41px apart.  Declining is therefore an exact
    # label match, never a keyword one.
    BLOCKING_OVERLAY_SELECTOR = 'div.xdModal.back-drop'
    BLOCKING_OVERLAY_DISMISS_LABELS = ['Maybe Later']
    SUCCESS_URL_PATTERN = ''  # SPA — URL capture unlikely
    SUCCESS_SELECTOR = ''
    COOKIE_DOMAINS = ['fansly.com']
    AUTH_COOKIE_NAMES = [
        'fansly-d',
        'CloudFront-Key-Pair-Id',
        'CloudFront-Policy',
        'CloudFront-Signature',
    ]
    SESSION_EXPIRED_SELECTORS = [
        '.nav-content-wrapper.not-logged-in',
        'input[autocomplete="password"]',
    ]
    SESSION_EXPIRED_CHECK_DELAY_MS = 5000
    PREFILL_DELAY_MS = 1500  # Cloudflare challenge + SPA hydration
    POLL_INTERVAL_MS = 1000
    MEDIA_PREFILL_ENABLED = True
    MEDIA_STEP_POLL_INTERVAL_MS = 1000
    MEDIA_STEP_CALLBACK_TIMEOUT_MS = 610000
    MEDIA_MENU_TIMEOUT_MS = 10000
    MEDIA_MODAL_TIMEOUT_MS = 20000
    # Small JPEGs and videos took ~5 s, but large uploads have not been measured.
    MEDIA_UPLOAD_TIMEOUT_MS = 600000
    MEDIA_POST_READY_TIMEOUT_MS = 600000

    # The icon itself does nothing. :has() selects its dropdown-title parent, while
    # `.fa-image` is a CSS class-token match and therefore cannot hit `.fa-images`.
    MEDIA_MENU_SELECTOR = 'div.dropdown-title:has(i.fa-image.hover-effect)'
    UPLOAD_NEW_MARKER_SELECTOR = '[data-galefling-media-target="upload-new"]'
    UPLOAD_BUTTON_MARKER_SELECTOR = '[data-galefling-media-target="upload-button"]'

    def get_platform_name(self) -> str:
        if self._profile_name:
            return f'Fansly ({self._profile_name})'
        return 'Fansly'

    def get_specs(self) -> PlatformSpecs:
        return FANSLY_SPECS

    def _prefill_media(self) -> None:
        """Drive Fansly's picker and upload modal, stopping before Post."""
        path = self._image_path
        if not path or not self._view or not self._view.page():
            get_logger().error(
                f'{self.get_platform_name()}: media pre-fill aborted before start: '
                'missing media path or WebView page'
            )
            return

        state: dict[str, int] = {'before_count': -1}

        def dismiss_overlay(done) -> None:
            def handled(result: dict) -> None:
                overlay = result if isinstance(result, dict) else {'raw': result}
                ok = not overlay.get('present') or bool(overlay.get('dismissed'))
                done(ok, 'blocking overlay still covers the composer', overlay)

            self.dismiss_blocking_overlay(callback=handled)

        def inject_text(done) -> None:
            def handled(result: dict) -> None:
                text_state = result if isinstance(result, dict) else {'raw': result}
                done(
                    bool(text_state.get('injected')),
                    text_state.get('reason', 'composer text was not injected'),
                    text_state,
                )

            self._inject_text(self._text, callback=handled)

        def read_baseline(done) -> None:
            def handled(result: dict) -> None:
                media_state = result if isinstance(result, dict) else {'raw': result}
                count = media_state.get('mediaCount')
                if not isinstance(count, int):
                    done(False, 'media upload container was not found', media_state)
                    return
                state['before_count'] = count
                done(True, '', media_state)

            self._fansly_composer_media_state(handled)

        def stage(done) -> None:
            self.stage_media_for_picker(path)
            done(True, '', {'file': path.name})

        def click_menu(done) -> None:
            def handled(result: dict) -> None:
                click_state = result if isinstance(result, dict) else {'raw': result}
                done(
                    bool(click_state.get('clicked')),
                    click_state.get('reason', 'media dropdown control was not clicked'),
                    click_state,
                )

            self.trusted_click(self.MEDIA_MENU_SELECTOR, callback=handled)

        def wait_for_upload_new(done) -> None:
            self._poll_media_step(
                self._mark_fansly_upload_new,
                lambda result: bool(result.get('found')),
                self.MEDIA_MENU_TIMEOUT_MS,
                'Upload New never became visible after opening the media dropdown',
                done,
            )

        def choose_upload_new(done) -> None:
            # Clicking Fansly's bare input bypasses its uploader, so there is no
            # direct-input fallback here: Upload New itself must open the picker.
            self._activate_staged_media_picker(
                self.UPLOAD_NEW_MARKER_SELECTOR,
                path,
                done,
                fallback_to_input=False,
            )

        def wait_for_modal(done) -> None:
            self._poll_media_step(
                self._fansly_upload_modal_state,
                lambda result: bool(result.get('visible')),
                self.MEDIA_MODAL_TIMEOUT_MS,
                'Upload media modal never appeared after the picker selection',
                done,
            )

        def apply_permissions(done) -> None:
            def handled(result: dict) -> None:
                permission_state = result if isinstance(result, dict) else {'raw': result}
                done(
                    bool(permission_state.get('ok')),
                    'Fansly media permissions do not match the no-paywall policy',
                    permission_state,
                )

            self.apply_media_permissions(callback=handled)

        def wait_for_upload_button(done) -> None:
            self._poll_media_step(
                self._mark_fansly_upload_button,
                lambda result: bool(result.get('found')) and not result.get('disabled'),
                self.MEDIA_MODAL_TIMEOUT_MS,
                'enabled Upload control was not found in the media modal',
                done,
            )

        def click_upload(done) -> None:
            def handled(result: dict) -> None:
                click_state = result if isinstance(result, dict) else {'raw': result}
                done(
                    bool(click_state.get('clicked')),
                    click_state.get('reason', 'Upload control was not clicked'),
                    click_state,
                )

            self.trusted_click(self.UPLOAD_BUTTON_MARKER_SELECTOR, callback=handled)

        def wait_for_attachment(done) -> None:
            self._poll_media_step(
                self._fansly_composer_media_state,
                lambda result: (
                    isinstance(result.get('mediaCount'), int)
                    and result['mediaCount'] > state['before_count']
                ),
                self.MEDIA_UPLOAD_TIMEOUT_MS,
                'uploaded media never reached the Fansly composer',
                done,
            )

        def wait_for_post_ready(done) -> None:
            self._poll_media_step(
                self._fansly_post_control_state,
                lambda result: bool(result.get('found')) and not result.get('disabled'),
                self.MEDIA_POST_READY_TIMEOUT_MS,
                'Post control remained disabled after media reached the composer',
                done,
            )

        steps = [('dismiss blocking overlay', dismiss_overlay)]
        if self._text:
            steps.append(('fill composer text', inject_text))
        steps.extend(
            [
                ('read composer media baseline', read_baseline),
                ('stage picker file', stage),
                ('open media dropdown', click_menu),
                ('wait for exact Upload New control', wait_for_upload_new),
                ('choose Upload New and open picker', choose_upload_new),
                ('wait for Upload media modal', wait_for_modal),
                ('apply no-paywall media permissions', apply_permissions),
                ('wait for enabled Upload control', wait_for_upload_button),
                ('confirm media upload', click_upload),
                ('wait for composer attachment', wait_for_attachment),
                ('wait for Post control to enable', wait_for_post_ready),
            ]
        )
        self._run_media_sequence(steps)

    def _run_fansly_javascript(self, script: str, callback: Callable[[dict], None]) -> None:
        """Run a media-flow probe and always return a reasoned result."""
        if not self._view or not self._view.page():
            callback({'found': False, 'reason': 'no WebView page'})
            return
        page = self._view.page()
        if not page:
            callback({'found': False, 'reason': 'no WebView page'})
            return
        page.runJavaScript(script, callback)

    def _mark_fansly_upload_new(self, callback: Callable[[dict], None]) -> None:
        """Mark the visible leaf whose exact text is ``Upload New``."""
        self._run_fansly_javascript(
            """
            (function() {
                var marker = 'data-galefling-media-target';
                document.querySelectorAll('[' + marker + ']').forEach(function(el) {
                    el.removeAttribute(marker);
                });
                function shown(el) {
                    if (!el) return false;
                    var r = el.getBoundingClientRect();
                    var s = getComputedStyle(el);
                    return r.width > 0 && r.height > 0
                        && s.display !== 'none' && s.visibility !== 'hidden';
                }
                var target = Array.from(document.querySelectorAll('*')).filter(function(el) {
                    return el.children.length === 0 && shown(el)
                        && (el.textContent || '').trim() === 'Upload New';
                })[0];
                if (!target) return {found: false, reason: 'exact Upload New leaf not visible'};
                target.setAttribute(marker, 'upload-new');
                return {found: true};
            })();
            """,
            callback,
        )

    def _fansly_upload_modal_state(self, callback: Callable[[dict], None]) -> None:
        """Report whether the exact ``Upload media`` modal heading is visible."""
        self._run_fansly_javascript(
            """
            (function() {
                function shown(el) {
                    if (!el) return false;
                    var r = el.getBoundingClientRect();
                    var s = getComputedStyle(el);
                    return r.width > 0 && r.height > 0
                        && s.display !== 'none' && s.visibility !== 'hidden';
                }
                var heading = Array.from(document.querySelectorAll('*')).filter(function(el) {
                    return el.children.length === 0 && shown(el)
                        && (el.textContent || '').trim() === 'Upload media';
                })[0];
                return {visible: !!heading};
            })();
            """,
            callback,
        )

    def _mark_fansly_upload_button(self, callback: Callable[[dict], None]) -> None:
        """Mark the modal's exact ``Upload`` control and report disabled state."""
        self._run_fansly_javascript(
            """
            (function() {
                var marker = 'data-galefling-media-target';
                document.querySelectorAll('[' + marker + ']').forEach(function(el) {
                    el.removeAttribute(marker);
                });
                function shown(el) {
                    if (!el) return false;
                    var r = el.getBoundingClientRect();
                    var s = getComputedStyle(el);
                    return r.width > 0 && r.height > 0
                        && s.display !== 'none' && s.visibility !== 'hidden';
                }
                var target = Array.from(
                    document.querySelectorAll('button, div[class*="btn"]')
                ).filter(function(el) {
                    return shown(el) && (el.textContent || '').trim() === 'Upload';
                })[0];
                if (!target) return {found: false, reason: 'exact Upload control not visible'};
                target.setAttribute(marker, 'upload-button');
                return {
                    found: true,
                    disabled: !!target.disabled || target.classList.contains('disabled')
                };
            })();
            """,
            callback,
        )

    def _fansly_composer_media_state(self, callback: Callable[[dict], None]) -> None:
        """Count only children of the composer's media upload container."""
        self._run_fansly_javascript(
            """
            (function() {
                var container = document.querySelector('[class*="media-upload-container"]');
                return {
                    found: !!container,
                    mediaCount: container ? container.children.length : null
                };
            })();
            """,
            callback,
        )

    def _fansly_post_control_state(self, callback: Callable[[dict], None]) -> None:
        """Observe the Post div without clicking it."""
        self._run_fansly_javascript(
            """
            (function() {
                function shown(el) {
                    if (!el) return false;
                    var r = el.getBoundingClientRect();
                    var s = getComputedStyle(el);
                    return r.width > 0 && r.height > 0
                        && s.display !== 'none' && s.visibility !== 'hidden';
                }
                var post = Array.from(document.querySelectorAll('div.new-post-btn')).filter(
                    function(el) {
                        return shown(el) && (el.textContent || '').trim() === 'Post';
                    }
                )[0];
                return {
                    found: !!post,
                    disabled: !!(post && post.classList.contains('disabled'))
                };
            })();
            """,
            callback,
        )

    # Media Permissions rows in the "Upload media" modal. Each is an Angular
    # <app-xd-checkbox> wrapping <div class="checkbox">; "selected" on that inner div
    # is the checked state. There is no <input type="checkbox"> anywhere in the modal.
    MEDIA_PERMISSION_POLICY = {
        # GaleFling posts are never paywalled — see AGENTS.md "Critical Conventions".
        # Fansly checks Require Subscription by default; it must be cleared.
        'Require Subscription': False,
        'Require Follow': True,
    }

    def apply_media_permissions(self, callback: 'Callable[[dict], None] | None' = None) -> None:
        """Set the upload modal's permissions so the post is not paywalled.

        Clears **Require Subscription** (Fansly checks it by default, "Any Tier") and
        sets **Require Follow**. Advanced Permissions and Require Purchase are left
        exactly as found — this touches only the rows named in
        ``MEDIA_PERMISSION_POLICY``.

        Rows are matched by their exact label text, never by keyword. These controls
        govern monetization and sit beside each other, so a fuzzy match here is the
        same hazard class as FetLife's ``picture[is_avatar]``.
        """
        if not self._view:
            return
        page = self._view.page()
        if not page:
            return

        js = f"""
        (function() {{
            var policy = {json.dumps(self.MEDIA_PERMISSION_POLICY)};
            var result = {{applied: [], missing: [], unchanged: []}};

            Object.keys(policy).forEach(function(label) {{
                var leaf = Array.from(document.querySelectorAll('*')).filter(function(e) {{
                    return e.children.length === 0
                        && (e.textContent || '').trim() === label;
                }})[0];
                if (!leaf) {{ result.missing.push(label); return; }}

                var row = leaf.parentElement;
                for (var d = 0; d < 3 && row && !row.querySelector('app-xd-checkbox'); d++) {{
                    row = row.parentElement;
                }}
                var host = row && row.querySelector('app-xd-checkbox');
                var box = host && host.querySelector('div.checkbox');
                if (!box) {{ result.missing.push(label); return; }}

                var isOn = box.classList.contains('selected');
                if (isOn === policy[label]) {{ result.unchanged.push(label); return; }}
                host.click();
                result.applied.push(label);
            }});

            // Read the state back rather than trusting the clicks.
            result.state = {{}};
            Object.keys(policy).forEach(function(label) {{
                var leaf = Array.from(document.querySelectorAll('*')).filter(function(e) {{
                    return e.children.length === 0
                        && (e.textContent || '').trim() === label;
                }})[0];
                if (!leaf) return;
                var row = leaf.parentElement;
                for (var d = 0; d < 3 && row && !row.querySelector('app-xd-checkbox'); d++) {{
                    row = row.parentElement;
                }}
                var box = row && row.querySelector('app-xd-checkbox div.checkbox');
                if (box) result.state[label] = box.classList.contains('selected');
            }});
            result.ok = Object.keys(policy).every(function(label) {{
                return result.state[label] === policy[label];
            }});
            return result;
        }})();
        """
        if callback:
            page.runJavaScript(js, callback)
        else:
            page.runJavaScript(js)
