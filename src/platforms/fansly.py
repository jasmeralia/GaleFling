"""Fansly platform implementation using WebView."""

from src.platforms.base_webview import BaseWebViewPlatform
from src.utils.constants import FANSLY_SPECS, PlatformSpecs


class FanslyPlatform(BaseWebViewPlatform):
    """Fansly posting via embedded WebView (Cloudflare-protected)."""

    COMPOSER_URL = 'https://fansly.com/'
    TEXT_SELECTOR = 'textarea'
    SUCCESS_URL_PATTERN = ''  # SPA — URL capture unlikely
    SUCCESS_SELECTOR = ''
    COOKIE_DOMAINS = ['fansly.com']
    AUTH_COOKIE_NAMES = [
        'fansly-d',
        'CloudFront-Key-Pair-Id',
        'CloudFront-Policy',
        'CloudFront-Signature',
    ]
    PREFILL_DELAY_MS = 1500  # Cloudflare challenge + SPA hydration
    POLL_INTERVAL_MS = 1000

    def get_platform_name(self) -> str:
        if self._profile_name:
            return f'Fansly ({self._profile_name})'
        return 'Fansly'

    def get_specs(self) -> PlatformSpecs:
        return FANSLY_SPECS
