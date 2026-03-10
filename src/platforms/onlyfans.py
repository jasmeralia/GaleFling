"""OnlyFans platform implementation using WebView."""

from src.platforms.base_webview import BaseWebViewPlatform
from src.utils.constants import ONLYFANS_SPECS, PlatformSpecs


class OnlyFansPlatform(BaseWebViewPlatform):
    """OnlyFans posting via embedded WebView (Cloudflare-protected)."""

    COMPOSER_URL = 'https://onlyfans.com/'
    TEXT_SELECTOR = 'div[contenteditable="true"].b-make-post__text'
    SUCCESS_URL_PATTERN = ''  # SPA — URL capture unlikely
    SUCCESS_SELECTOR = ''
    COOKIE_DOMAINS = ['onlyfans.com']
    AUTH_COOKIE_NAMES = ['auth_id', 'sess']
    PREFILL_DELAY_MS = 1500  # Cloudflare challenge + SPA hydration
    POLL_INTERVAL_MS = 1000

    def get_platform_name(self) -> str:
        if self._profile_name:
            return f'OnlyFans ({self._profile_name})'
        return 'OnlyFans'

    def get_specs(self) -> PlatformSpecs:
        return ONLYFANS_SPECS
