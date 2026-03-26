"""Threads platform implementation using WebView.

SETUP INCOMPLETE — placeholders require empirical verification.
See AGENTS.md § "Threads Platform — Data Collection Required" before
enabling this platform for production use.
"""

from src.core.logger import get_logger
from src.platforms.base_webview import BaseWebViewPlatform
from src.utils.constants import THREADS_SPECS, PlatformSpecs


class ThreadsPlatform(BaseWebViewPlatform):
    """Threads posting via embedded WebView.

    Auth: Instagram/Meta session cookies persisted in the WebView profile.
    Post flow: user navigates to threads.com, GaleFling pre-fills text, user
    attaches media manually (if any) and clicks Post.
    """

    COMPOSER_URL = 'https://www.threads.com/'

    # THREADS_PLACEHOLDER: Verify by opening threads.com in a browser with DevTools,
    # clicking the composer, and running:
    #   document.activeElement.tagName + ' / ' + document.activeElement.getAttribute('data-lexical-editor')
    # Likely candidates: '[data-lexical-editor="true"]', '[contenteditable="true"][role="textbox"]',
    # or 'div[aria-label*="thread"]'. Update TEXT_SELECTOR once confirmed.
    TEXT_SELECTOR = '[data-lexical-editor="true"]'

    # Threads post URLs look like: https://www.threads.com/@username/post/ABC123
    # This pattern is a good candidate for URL capture; verify against a live post.
    SUCCESS_URL_PATTERN = r'https://www\.threads\.com/@[\w.]+/post/[\w-]+'

    LOGIN_URL = 'https://www.threads.com/login'

    COOKIE_DOMAINS = ['threads.com', 'threads.net']

    # THREADS_PLACEHOLDER: Verify by opening DevTools → Application → Cookies on
    # threads.com after logging in. Look for session/auth cookies. Instagram's
    # 'sessionid' cookie is shared across Meta properties (instagram.com, threads.com).
    # Update AUTH_COOKIE_NAMES once confirmed which cookies are present.
    AUTH_COOKIE_NAMES = ['sessionid']

    PREFILL_DELAY_MS = 500  # SPA hydration delay; increase if pre-fill misses

    def get_platform_name(self) -> str:
        if self._profile_name:
            return f'Threads ({self._profile_name})'
        return 'Threads'

    def get_specs(self) -> PlatformSpecs:
        return THREADS_SPECS

    def _do_prefill(self) -> None:
        """Inject text (base behaviour) then run a DOM diagnostic pass.

        The diagnostic logs every contenteditable element, every
        [data-lexical-editor] element, and every textarea found on the
        page after the SPA hydration delay.  This data is needed to
        verify the THREADS_PLACEHOLDER selectors and should be removed
        once TEXT_SELECTOR and AUTH_COOKIE_NAMES are confirmed.
        """
        super()._do_prefill()
        self._log_composer_dom()

    def _log_composer_dom(self) -> None:
        """Run JS and log composer-relevant DOM structure for selector verification."""
        if not self._view:
            return
        page = self._view.page()
        if not page:
            return

        js = """
        (function() {
            function describeEl(el) {
                var attribs = {};
                for (var i = 0; i < el.attributes.length; i++) {
                    var a = el.attributes[i];
                    attribs[a.name] = a.value.substring(0, 100);
                }
                return {
                    tag: el.tagName,
                    id: el.id || null,
                    className: (el.className || '').substring(0, 120),
                    role: el.getAttribute('role'),
                    attribs: attribs
                };
            }
            return {
                url: window.location.href,
                editables: Array.from(
                    document.querySelectorAll('[contenteditable]')
                ).map(describeEl),
                lexical: Array.from(
                    document.querySelectorAll('[data-lexical-editor]')
                ).map(describeEl),
                textareas: Array.from(
                    document.querySelectorAll('textarea')
                ).map(describeEl)
            };
        })();
        """

        def _on_result(data: object) -> None:
            log = get_logger()
            if not isinstance(data, dict):
                log.warning('Threads DOM diagnostic: unexpected JS result type')
                return
            url = data.get('url', '?')
            editables = data.get('editables', [])
            lexical = data.get('lexical', [])
            textareas = data.get('textareas', [])
            log.info(
                f'Threads DOM diagnostic (url={url}): '
                f'{len(editables)} contenteditable, '
                f'{len(lexical)} [data-lexical-editor], '
                f'{len(textareas)} textarea'
            )
            for i, el in enumerate(editables):
                log.info(f'  Threads editable[{i}]: {el}')
            for i, el in enumerate(lexical):
                log.info(f'  Threads lexical[{i}]: {el}')
            for i, el in enumerate(textareas):
                log.info(f'  Threads textarea[{i}]: {el}')

        page.runJavaScript(js, _on_result)
