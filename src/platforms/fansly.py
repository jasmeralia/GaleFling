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
    # NOTE: the inherited _attach_media() does NOT work here.  Fansly's Angular uploader
    # ignores a synthetic DataTransfer + change event outright — verified 2026-08-12
    # against the live composer: the input clears, and twelve seconds later the composer
    # subtree is byte-identical (no preview, no app-media, textarea still ng-pristine
    # ng-invalid).  It presumably requires a trusted file selection.  Attaching media
    # here needs a QWebEnginePage.chooseFiles() override (task #417 Level B), which is
    # the same mechanism recommended for FetLife.
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
