"""Fansly platform implementation using WebView."""

import json
from collections.abc import Callable

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
    # NOTE: media cannot currently be attached to this composer by any automated
    # means we have found.  Verified 2026-08-12 against the live composer:
    #
    #   synthetic DataTransfer  ignored outright — the input clears and the composer
    #                           subtree is byte-identical twelve seconds later.
    #   chooseFiles() picker    the picker fires and Chromium hands over a genuine
    #                           selection, yet media-upload-container stays empty
    #                           (0 children, 14 bytes of innerHTML) for 20s+.
    #
    # Posting regardless publishes the caption with no media attached, so there are
    # deliberately no Fansly media tests.  Whatever Fansly binds its uploader to, it is
    # not this input's change event.  Finding it needs fresh investigation — likely
    # drag-and-drop, or a wrapper component that never consults the input at all.
    MEDIA_FILE_SELECTOR = 'input[type="file"]'
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

    def get_platform_name(self) -> str:
        if self._profile_name:
            return f'Fansly ({self._profile_name})'
        return 'Fansly'

    def get_specs(self) -> PlatformSpecs:
        return FANSLY_SPECS

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
