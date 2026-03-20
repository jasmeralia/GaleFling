"""Snapchat platform implementation using WebView."""

from PyQt6.QtCore import QTimer, QUrl

from src.platforms.base_webview import BaseWebViewPlatform
from src.utils.constants import SNAPCHAT_SPECS, PlatformSpecs


class SnapchatPlatform(BaseWebViewPlatform):
    """Snapchat posting via embedded WebView at web.snapchat.com."""

    COMPOSER_URL = 'https://web.snapchat.com/'
    TEXT_SELECTOR = 'div[contenteditable="true"]'
    SUCCESS_URL_PATTERN = ''  # SPA — URL capture unlikely
    COOKIE_DOMAINS = ['snapchat.com']
    AUTH_COOKIE_NAMES = ['__Host-sc-a-auth-session']
    PREFILL_DELAY_MS = 500  # Snapchat SPA loads slowly

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set when the user visits accounts.snapchat.com (the login page).
        # Used to detect the post-login redirect back to www.snapchat.com/web
        # and replace it with a safe navigation to web.snapchat.com.
        self._visited_accounts_page = False

    def _is_login_redirect_url(self, url_string: str) -> bool:
        """Detect session expiry via subdomain: authenticated app lives at
        web.snapchat.com; expired sessions redirect to www.snapchat.com."""
        if url_string:
            host = QUrl(url_string).host().strip().lower()
            # Any snapchat.com URL that isn't the web app host means expired.
            if host.endswith('snapchat.com') and host != 'web.snapchat.com':
                return True
        return super()._is_login_redirect_url(url_string)

    def _on_url_changed(self, url: QUrl):
        """Intercept navigations to www.snapchat.com/web* that crash the renderer.

        www.snapchat.com/web (the marketing landing page) loads GPU-heavy
        authenticated Next.js that causes an ACCESS_VIOLATION crash (exit code
        -1073741819) in Qt's Chromium renderer whenever Snapchat cookies are
        present — whether on the initial expired-session redirect or on the
        post-login return redirect.

        Strategy:
        - If we have NOT visited accounts.snapchat.com yet (initial redirect):
          navigate directly to the Snapchat SSO login so the user can log in
          without loading the crashing marketing page.
        - If we HAVE visited accounts.snapchat.com (post-login redirect):
          navigate directly to web.snapchat.com (the actual web app).
        """
        host = url.host().lower()
        path = url.path().lower()

        if host == 'accounts.snapchat.com':
            self._visited_accounts_page = True
        elif host == 'www.snapchat.com' and path.startswith('/web') and self._view:
            view = self._view
            if self._visited_accounts_page:
                # Post-login redirect → go straight to the web app.
                self._visited_accounts_page = False
                dest = 'https://web.snapchat.com/'
            else:
                # Initial expired-session redirect → go straight to login,
                # bypassing the crashing marketing page entirely.
                dest = (
                    'https://accounts.snapchat.com/accounts/sso'
                    '?client_id=web-calling-corp--prod'
                    '&referrer=https%3A%2F%2Fweb.snapchat.com%2F'
                )
            QTimer.singleShot(0, lambda: view.load(QUrl(dest)))

        super()._on_url_changed(url)

    def get_platform_name(self) -> str:
        if self._profile_name:
            return f'Snapchat ({self._profile_name})'
        return 'Snapchat'

    def get_specs(self) -> PlatformSpecs:
        return SNAPCHAT_SPECS
