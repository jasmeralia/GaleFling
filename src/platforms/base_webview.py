"""Abstract base class for WebView-based social media platforms."""

import contextlib
import json
import re
from pathlib import Path

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QWidget

from src.core.logger import get_logger
from src.platforms.base import BasePlatform
from src.utils.constants import PostResult
from src.utils.helpers import get_app_data_dir


class BaseWebViewPlatform(BasePlatform):
    """Abstract base for platforms that use an embedded browser for posting.

    Subclasses must define:
        COMPOSER_URL: str — URL to navigate to for composing a post
        TEXT_SELECTOR: str — CSS selector for the text input element

    Subclasses may override:
        SUCCESS_URL_PATTERN: str — regex matching a post permalink URL
        SUCCESS_SELECTOR: str — CSS selector for a DOM element indicating success
        PERMALINK_SELECTOR: str — CSS selector for a permalink element after success
        PREFILL_DELAY_MS: int — delay before injecting text (for Cloudflare sites)
        POLL_INTERVAL_MS: int — interval for polling DOM success state
        POLL_TIMEOUT_MS: int — max time to poll before giving up
    """

    COMPOSER_URL: str = ''
    TEXT_SELECTOR: str = ''
    SUCCESS_URL_PATTERN: str = ''
    SUCCESS_SELECTOR: str = ''
    PERMALINK_SELECTOR: str = ''
    PREFILL_DELAY_MS: int = 200
    POLL_INTERVAL_MS: int = 500
    POLL_TIMEOUT_MS: int = 30000

    def __init__(
        self,
        account_id: str = '',
        profile_name: str = '',
    ):
        self._account_id = account_id
        self._profile_name = profile_name
        self._view: QWebEngineView | None = None
        self._profile: QWebEngineProfile | None = None
        self._captured_post_url: str | None = None
        self._post_confirmed = False
        self._text: str = ''
        self._image_path: Path | None = None
        self._poll_timer: QTimer | None = None
        self._poll_elapsed_ms: int = 0

    # ── Profile & view management ───────────────────────────────────

    def create_webview(self, parent: QWidget | None = None) -> QWebEngineView:
        """Create an isolated QWebEngineView with persistent cookies."""
        profile_name = self._account_id or 'default'
        storage_path = get_app_data_dir() / 'webprofiles' / profile_name

        self._profile = QWebEngineProfile(profile_name, parent)
        self._profile.setPersistentStoragePath(str(storage_path))
        self._profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
        )

        page = QWebEnginePage(self._profile, parent)
        self._view = QWebEngineView(parent)
        self._view.setPage(page)

        # Connect URL change monitoring
        page.urlChanged.connect(self._on_url_changed)

        return self._view

    def get_webview(self) -> QWebEngineView | None:
        """Return the existing WebEngineView, if created."""
        return self._view

    # ── Posting workflow ────────────────────────────────────────────

    def prepare_post(self, text: str, image_path: Path | None = None):
        """Store text and image for pre-fill after page loads."""
        self._text = text
        self._image_path = image_path
        self._captured_post_url = None
        self._post_confirmed = False
        self._poll_elapsed_ms = 0

    def navigate_to_composer(self):
        """Load the composer URL in the WebView."""
        if not self._view:
            get_logger().error(f'{self.get_platform_name()}: WebView not created')
            return
        if not self.COMPOSER_URL:
            get_logger().error(f'{self.get_platform_name()}: No COMPOSER_URL defined')
            return

        view = self._view
        page = view.page()
        if not page:
            get_logger().error(f'{self.get_platform_name()}: WebView page not available')
            return
        page.loadFinished.connect(self._on_load_finished)
        view.load(QUrl(self.COMPOSER_URL))

    def _on_load_finished(self, ok: bool):
        """Called when the page finishes loading."""
        if not self._view:
            return
        if not ok:
            get_logger().warning(f'{self.get_platform_name()}: Page load failed')
            return

        view = self._view
        page = view.page()
        if not page:
            return

        # Disconnect to avoid re-triggering on SPA navigations
        with contextlib.suppress(TypeError, RuntimeError):
            page.loadFinished.disconnect(self._on_load_finished)

        # Delay pre-fill for Cloudflare-protected or heavy SPA sites
        QTimer.singleShot(self.PREFILL_DELAY_MS, self._do_prefill)

    def _do_prefill(self):
        """Inject text and optionally set up image upload."""
        if self._text:
            self._inject_text(self._text)
        if self.SUCCESS_SELECTOR:
            QTimer.singleShot(500, self._inject_success_observer)

    # ── Text injection ──────────────────────────────────────────────

    def _inject_text(self, text: str):
        """Inject post text into the composer via JS."""
        if not self._view or not self.TEXT_SELECTOR:
            return
        view = self._view
        page = view.page()
        if not page:
            return
        escaped = json.dumps(text)
        selector = json.dumps(self.TEXT_SELECTOR)
        js = f"""
        (function() {{
            const el = document.querySelector({selector});
            if (el) {{
                el.focus();
                if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {{
                    el.value = {escaped};
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }} else {{
                    el.textContent = {escaped};
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                }}
            }}
        }})();
        """
        page.runJavaScript(js)

    # ── URL capture ─────────────────────────────────────────────────

    def _on_url_changed(self, url: QUrl):
        """Monitor URL changes for post-submission redirects."""
        url_string = url.toString()
        if self.SUCCESS_URL_PATTERN and re.search(self.SUCCESS_URL_PATTERN, url_string):
            self._captured_post_url = url_string
            self._post_confirmed = True
            get_logger().info(
                f'{self.get_platform_name()}: Post URL captured via urlChanged: {url_string}'
            )

    # ── DOM success observer ────────────────────────────────────────

    def _inject_success_observer(self):
        """Inject a MutationObserver to detect post success in SPA platforms."""
        if not self._view or not self.SUCCESS_SELECTOR:
            return
        view = self._view
        page = view.page()
        if not page:
            return
        success_sel = json.dumps(self.SUCCESS_SELECTOR)
        permalink_sel = json.dumps(self.PERMALINK_SELECTOR) if self.PERMALINK_SELECTOR else 'null'
        js = f"""
        (function() {{
            window._galefling_post_success = false;
            window._galefling_post_url = null;
            const observer = new MutationObserver(function() {{
                const successEl = document.querySelector({success_sel});
                if (successEl) {{
                    window._galefling_post_success = true;
                    const pSel = {permalink_sel};
                    if (pSel) {{
                        const linkEl = document.querySelector(pSel);
                        window._galefling_post_url = linkEl ? linkEl.href : null;
                    }}
                    observer.disconnect();
                }}
            }});
            observer.observe(document.body, {{ childList: true, subtree: true }});
        }})();
        """
        page.runJavaScript(js)

    def start_success_polling(self):
        """Start polling the DOM for post success signals."""
        if not self._view:
            return
        self._poll_elapsed_ms = 0
        self._poll_timer = QTimer()
        self._poll_timer.setInterval(self.POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll_for_success)
        self._poll_timer.start()

    def stop_success_polling(self):
        """Stop the DOM success polling timer."""
        if self._poll_timer:
            self._poll_timer.stop()
            self._poll_timer = None

    def _poll_for_success(self):
        """Check if the MutationObserver detected a successful post."""
        self._poll_elapsed_ms += self.POLL_INTERVAL_MS
        if self._poll_elapsed_ms >= self.POLL_TIMEOUT_MS:
            self.stop_success_polling()
            return

        if not self._view:
            self.stop_success_polling()
            return
        view = self._view
        page = view.page()
        if not page:
            self.stop_success_polling()
            return
        page.runJavaScript(
            '({success: window._galefling_post_success, url: window._galefling_post_url})',
            self._handle_poll_result,
        )

    def _handle_poll_result(self, result):
        """Process the result of a DOM success poll."""
        if not isinstance(result, dict):
            return
        if result.get('success'):
            self._post_confirmed = True
            url = result.get('url')
            if url:
                self._captured_post_url = url
                get_logger().info(
                    f'{self.get_platform_name()}: Post URL captured via DOM observer: {url}'
                )
            else:
                get_logger().info(
                    f'{self.get_platform_name()}: Post confirmed via DOM observer (no URL)'
                )
            self.stop_success_polling()

    # ── Result building ─────────────────────────────────────────────

    @property
    def is_post_confirmed(self) -> bool:
        """Whether the user has confirmed the post (URL captured or DOM success)."""
        return self._post_confirmed

    @property
    def captured_post_url(self) -> str | None:
        """The captured post URL, if any."""
        return self._captured_post_url

    def mark_confirmed(self):
        """Manually mark this platform's post as confirmed by the user."""
        self._post_confirmed = True

    def build_result(self) -> PostResult:
        """Build a PostResult based on the current state."""
        if self._post_confirmed:
            return PostResult(
                success=True,
                platform=self.get_platform_name(),
                post_url=self._captured_post_url,
                account_id=self._account_id,
                profile_name=self._profile_name,
                url_captured=self._captured_post_url is not None,
                user_confirmed=True,
            )
        return PostResult(
            success=False,
            platform=self.get_platform_name(),
            error_code='WV-SUBMIT-TIMEOUT',
            error_message='Post was not confirmed.',
            account_id=self._account_id,
            profile_name=self._profile_name,
            user_confirmed=False,
        )

    # ── BasePlatform interface ──────────────────────────────────────
    # WebView platforms don't use authenticate/test_connection/post in
    # the traditional sense. These provide minimal implementations.

    def authenticate(self) -> tuple[bool, str | None]:
        """WebView platforms authenticate via browser session cookies."""
        return True, None

    def test_connection(self) -> tuple[bool, str | None]:
        """WebView platforms can't easily test connections programmatically."""
        return True, None

    def post(self, text: str, image_path: Path | None = None) -> PostResult:
        """WebView platforms don't post programmatically.

        Use prepare_post() + navigate_to_composer() + build_result() instead.
        """
        return PostResult(
            success=False,
            platform=self.get_platform_name(),
            error_code='WV-PREFILL-FAILED',
            error_message='WebView platforms require the WebView panel for posting.',
            account_id=self._account_id,
            profile_name=self._profile_name,
        )
