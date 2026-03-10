"""Abstract base class for WebView-based social media platforms."""

import contextlib
import json
import re
import sqlite3
import time
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
    COOKIE_DOMAINS: list[str] = []
    AUTH_COOKIE_NAMES: list[str] = []
    AUTH_COOKIE_NAME_PATTERNS: list[str] = []
    PREFILL_DELAY_MS: int = 200
    POLL_INTERVAL_MS: int = 500
    POLL_TIMEOUT_MS: int = 30000
    COOKIE_DB_TIMEOUT_SECONDS: float = 0.01
    COOKIE_NAME_SCAN_LIMIT: int = 250

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
        storage_path = self._get_profile_storage_path()

        self._profile = QWebEngineProfile(storage_path.name, parent)
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

    def _get_profile_storage_path(self) -> Path:
        profile_name = self._account_id or 'default'
        return get_app_data_dir() / 'webprofiles' / profile_name

    def _get_cookie_db_path(self) -> Path:
        return self._get_profile_storage_path() / 'Cookies'

    def has_valid_session(self) -> bool:
        """Check for platform auth cookies in persisted cookies without blocking UI."""
        if not self.COOKIE_DOMAINS:
            return False
        cookie_path = self._get_cookie_db_path()
        if not cookie_path.exists():
            return False
        db_uri = f'file:{cookie_path}?mode=ro'
        try:
            with sqlite3.connect(
                db_uri,
                uri=True,
                timeout=self.COOKIE_DB_TIMEOUT_SECONDS,
            ) as conn:
                return self._has_valid_session_in_db(conn)
        except sqlite3.Error as exc:
            get_logger().debug(
                'Cookie session check failed',
                extra={
                    'platform': self.get_platform_name(),
                    'cookie_path': str(cookie_path),
                    'error': str(exc),
                },
            )
            return False

    def _has_valid_session_in_db(self, conn: sqlite3.Connection) -> bool:
        cursor = conn.cursor()
        cursor.execute('PRAGMA table_info(cookies)')
        columns = {row[1] for row in cursor.fetchall()}
        if 'host_key' not in columns:
            return False

        has_name = 'name' in columns
        has_expires = 'expires_utc' in columns
        domain_where, domain_params = self._domain_where_clause()
        if not domain_where:
            return False

        now_chrome_us = int((time.time() + 11644473600) * 1_000_000)
        expiry_where = ''
        expiry_params: tuple[object, ...] = ()
        if has_expires:
            expiry_where = ' AND (expires_utc = 0 OR expires_utc >= ?)'
            expiry_params = (now_chrome_us,)

        if not (self.AUTH_COOKIE_NAMES or self.AUTH_COOKIE_NAME_PATTERNS):
            cursor.execute(
                f'SELECT 1 FROM cookies WHERE ({domain_where}){expiry_where} LIMIT 1',
                domain_params + expiry_params,
            )
            return cursor.fetchone() is not None

        if not has_name:
            return False

        auth_names = [name.lower() for name in self.AUTH_COOKIE_NAMES]
        if auth_names:
            placeholders = ', '.join('?' for _ in auth_names)
            cursor.execute(
                (
                    f'SELECT 1 FROM cookies WHERE ({domain_where})'
                    f' AND lower(name) IN ({placeholders}){expiry_where} LIMIT 1'
                ),
                domain_params + tuple(auth_names) + expiry_params,
            )
            if cursor.fetchone() is not None:
                return True

        if not self.AUTH_COOKIE_NAME_PATTERNS:
            return False

        cursor.execute(
            (
                f'SELECT name FROM cookies WHERE ({domain_where}){expiry_where} '
                f'LIMIT {self.COOKIE_NAME_SCAN_LIMIT}'
            ),
            domain_params + expiry_params,
        )
        return any(
            self._is_auth_cookie_name(str(row[0]))
            for row in cursor.fetchall()
            if row and row[0] is not None
        )

    def _domain_where_clause(self) -> tuple[str, tuple[object, ...]]:
        where_parts: list[str] = []
        params: list[object] = []
        for domain in self.COOKIE_DOMAINS:
            normalized = domain.strip().lower().lstrip('.')
            if not normalized:
                continue
            where_parts.append('lower(host_key) LIKE ?')
            params.append(f'%{normalized}')
        return ' OR '.join(where_parts), tuple(params)

    def is_session_cookie(self, host: str, cookie_name: str) -> bool:
        """Whether a cookie should count as an authenticated session signal."""
        if not self._matches_cookie_domain(host):
            return False
        if self.AUTH_COOKIE_NAMES or self.AUTH_COOKIE_NAME_PATTERNS:
            return self._is_auth_cookie_name(cookie_name)
        return True

    def _matches_cookie_domain(self, host: str) -> bool:
        normalized_host = host.strip().lower().lstrip('.')
        if not normalized_host:
            return False
        for domain in self.COOKIE_DOMAINS:
            normalized_domain = domain.strip().lower().lstrip('.')
            if normalized_host == normalized_domain or normalized_host.endswith(
                f'.{normalized_domain}'
            ):
                return True
        return False

    def _is_auth_cookie_name(self, cookie_name: str) -> bool:
        normalized = cookie_name.strip().lower()
        if not normalized:
            return False
        if any(normalized == n.lower() for n in self.AUTH_COOKIE_NAMES):
            return True
        return any(
            re.search(pattern, normalized, flags=re.IGNORECASE)
            for pattern in self.AUTH_COOKIE_NAME_PATTERNS
        )

    def get_webview(self) -> QWebEngineView | None:
        """Return the existing WebEngineView, if created."""
        return self._view

    # ── Posting workflow ────────────────────────────────────────────

    def prepare_post(self, text: str, media_paths: list[Path] | None = None):
        """Store text and media for pre-fill after page loads."""
        self._text = text
        self._image_path = media_paths[0] if media_paths else None
        self._captured_post_url = None
        self._post_confirmed = False
        self._poll_elapsed_ms = 0

    def navigate_to_composer(self):
        """Load the composer URL in the WebView."""
        if not self._view:
            get_logger().error(f'{self.get_platform_name()}: WebView not created')
            return
        composer_url = self.get_composer_url()
        if not composer_url:
            get_logger().error(f'{self.get_platform_name()}: No COMPOSER_URL defined')
            return

        view = self._view
        page = view.page()
        if not page:
            get_logger().error(f'{self.get_platform_name()}: WebView page not available')
            return
        page.loadFinished.connect(self._on_load_finished)
        view.load(QUrl(composer_url))

    def navigate_to_login(self):
        """Load the login URL in the WebView. Defaults to composer URL."""
        self.navigate_to_composer()

    def get_composer_url(self) -> str:
        """Return the URL to use for composing a post."""
        return self.COMPOSER_URL

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
        if self.has_valid_session():
            return True, None
        return False, 'WV-SESSION-EXPIRED'

    def post(self, text: str, media_paths: list[Path] | None = None) -> PostResult:
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
