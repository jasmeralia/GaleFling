"""Threads platform implementation using WebView.

SETUP INCOMPLETE — placeholders require empirical verification.
See AGENTS.md § "Threads Platform — Data Collection Required" before
enabling this platform for production use.
"""

from src.platforms.base_webview import BaseWebViewPlatform
from src.utils.constants import THREADS_SPECS, PlatformSpecs


class ThreadsPlatform(BaseWebViewPlatform):
    """Threads posting via embedded WebView.

    Auth: Instagram/Meta session cookies persisted in the WebView profile.
    Post flow: user navigates to threads.net, GaleFling pre-fills text, user
    attaches media manually (if any) and clicks Post.
    """

    COMPOSER_URL = 'https://www.threads.net/'

    # THREADS_PLACEHOLDER: Verify by opening threads.net in a browser with DevTools,
    # clicking the composer, and running:
    #   document.activeElement.tagName + ' / ' + document.activeElement.getAttribute('data-lexical-editor')
    # Likely candidates: '[data-lexical-editor="true"]', '[contenteditable="true"][role="textbox"]',
    # or 'div[aria-label*="thread"]'. Update TEXT_SELECTOR once confirmed.
    TEXT_SELECTOR = '[data-lexical-editor="true"]'

    # Threads post URLs look like: https://www.threads.net/@username/post/ABC123
    # This pattern is a good candidate for URL capture; verify against a live post.
    SUCCESS_URL_PATTERN = r'https://www\.threads\.net/@[\w.]+/post/[\w-]+'

    LOGIN_URL = 'https://www.threads.net/login'

    COOKIE_DOMAINS = ['threads.net']

    # THREADS_PLACEHOLDER: Verify by opening DevTools → Application → Cookies on
    # threads.net after logging in. Look for session/auth cookies. Instagram's
    # 'sessionid' cookie is shared across Meta properties (instagram.com, threads.net).
    # Update AUTH_COOKIE_NAMES once confirmed which cookies are present.
    AUTH_COOKIE_NAMES = ['sessionid']

    PREFILL_DELAY_MS = 500  # SPA hydration delay; increase if pre-fill misses

    def get_platform_name(self) -> str:
        if self._profile_name:
            return f'Threads ({self._profile_name})'
        return 'Threads'

    def get_specs(self) -> PlatformSpecs:
        return THREADS_SPECS
