"""Fansly platform implementation using WebView."""

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
