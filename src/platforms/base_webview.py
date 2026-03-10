"""Abstract base class for WebView-based social media platforms."""

import contextlib
import json
import logging
import re
import sqlite3
import time
from pathlib import Path

from PyQt6.QtCore import QEventLoop, QTimer, QUrl
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication, QWidget

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
    LOGIN_URL: str = ''
    LOGIN_URL_PATTERNS: list[str] = [
        r'/login(?:[/?#]|$)',
        r'/sign[-_]?in(?:[/?#]|$)',
        r'/auth(?:[/?#]|$)',
    ]
    COOKIE_DOMAINS: list[str] = []
    AUTH_COOKIE_NAMES: list[str] = []
    AUTH_COOKIE_NAME_PATTERNS: list[str] = []
    PREFILL_DELAY_MS: int = 200
    POLL_INTERVAL_MS: int = 500
    POLL_TIMEOUT_MS: int = 30000
    CONNECTION_TEST_TIMEOUT_MS: int = 12000
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
        self._last_url: str = ''
        self._pending_nav_target: str | None = None
        self._pending_nav_source: str = 'unknown'
        self._pending_nav_type: str = 'unknown'

    # ── Profile & view management ───────────────────────────────────

    def create_webview(self, parent: QWidget | None = None) -> QWebEngineView:
        """Create an isolated QWebEngineView with persistent cookies."""
        storage_path = self._get_profile_storage_path()

        self._profile = QWebEngineProfile(storage_path.name, parent)
        self._profile.setPersistentStoragePath(str(storage_path))
        self._profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
        )

        page = _LoggingWebEnginePage(self._profile, self, parent)
        self._configure_webview_page(page)
        self._view = QWebEngineView(parent)
        self._view.setPage(page)

        # Connect WebView lifecycle and navigation monitoring
        page.urlChanged.connect(self._on_url_changed)
        page.loadStarted.connect(self._on_page_load_started)
        page.loadProgress.connect(self._on_page_load_progress)
        page.loadFinished.connect(self._on_page_load_finished_debug)
        page.renderProcessTerminated.connect(self._on_render_process_terminated)
        page.windowCloseRequested.connect(self._on_page_window_close_requested)
        with contextlib.suppress(AttributeError, TypeError):
            page.renderProcessPidChanged.connect(self._on_render_process_pid_changed)
        with contextlib.suppress(AttributeError, TypeError):
            self._view.renderProcessTerminated.connect(self._on_view_render_process_terminated)

        self._log_webview_debug(
            'WebView created',
            account_id=self._account_id or 'default',
            profile_path=str(storage_path),
        )

        return self._view

    def _log_webview_debug(self, message: str, **fields: object):
        logger = get_logger()
        if not logger.isEnabledFor(logging.DEBUG):
            return
        suffix = ''
        if fields:
            details = ' '.join(f'{key}={value!r}' for key, value in fields.items())
            suffix = f' {details}'
        logger.debug(f'{self.get_platform_name()} [webview]: {message}{suffix}')

    @staticmethod
    def _enum_label(value) -> str:
        name = getattr(value, 'name', None)
        if isinstance(name, str) and name:
            return name
        try:
            return str(int(value))
        except Exception:
            return str(value)

    @staticmethod
    def _navigation_source(nav_type_label: str) -> str:
        if nav_type_label == 'NavigationTypeLinkClicked':
            return 'user-click'
        if nav_type_label == 'NavigationTypeFormSubmitted':
            return 'form-submit'
        if nav_type_label == 'NavigationTypeBackForward':
            return 'history-navigation'
        if nav_type_label == 'NavigationTypeReload':
            return 'reload'
        if nav_type_label == 'NavigationTypeTyped':
            return 'typed-or-programmatic'
        if nav_type_label == 'NavigationTypeOther':
            return 'other-or-redirect'
        return 'unknown'

    def _on_navigation_request(
        self,
        url: QUrl,
        nav_type,
        is_main_frame: bool,
        accepted: bool,
    ):
        url_string = url.toString()
        nav_label = self._enum_label(nav_type)
        nav_source = self._navigation_source(nav_label)

        if is_main_frame and accepted:
            self._pending_nav_target = url_string
            self._pending_nav_source = nav_source
            self._pending_nav_type = nav_label

        self._log_webview_debug(
            'Navigation request',
            accepted=accepted,
            main_frame=is_main_frame,
            type=nav_label,
            source=nav_source,
            from_url=self._last_url or '(none)',
            to_url=url_string,
        )

    def _on_page_load_started(self):
        self._log_webview_debug(
            'Page load started',
            url=self._pending_nav_target or self._last_url or '(unknown)',
            source=self._pending_nav_source,
        )

    def _on_page_load_progress(self, progress: int):
        if progress in {0, 25, 50, 75, 100}:
            self._log_webview_debug('Page load progress', progress_percent=progress)

    def _on_page_load_finished_debug(self, ok: bool):
        current_url = self._view.url().toString() if self._view else ''
        self._log_webview_debug(
            'Page load finished',
            ok=ok,
            url=current_url,
            source=self._pending_nav_source,
        )

    def _on_page_window_close_requested(self):
        current_url = self._view.url().toString() if self._view else ''
        self._log_webview_debug(
            'Page requested window close',
            url=current_url,
        )

    def _on_render_process_terminated(self, termination_status, exit_code: int):
        status = self._enum_label(termination_status)
        current_url = self._view.url().toString() if self._view else ''
        get_logger().error(
            f'{self.get_platform_name()} [webview]: Render process terminated '
            f'(status={status}, exit_code={exit_code}, url="{current_url}")'
        )

    def _on_view_render_process_terminated(self, termination_status, exit_code: int):
        status = self._enum_label(termination_status)
        current_url = self._view.url().toString() if self._view else ''
        get_logger().error(
            f'{self.get_platform_name()} [webview]: View render process terminated '
            f'(status={status}, exit_code={exit_code}, url="{current_url}")'
        )

    def _on_render_process_pid_changed(self, pid: int):
        self._log_webview_debug('Render process PID changed', pid=pid)

    def _get_profile_storage_path(self) -> Path:
        profile_name = self._account_id or 'default'
        return get_app_data_dir() / 'webprofiles' / profile_name

    def _configure_webview_page(self, page: QWebEnginePage) -> None:
        """Allow subclasses to tweak per-page WebEngine settings."""
        return

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

    def _get_connection_test_url(self) -> str:
        """Return a representative composer URL for live session testing."""
        return self.COMPOSER_URL or self.get_composer_url()

    @staticmethod
    def _sanitize_url_for_log(url_string: str) -> str:
        """Return a privacy-safe URL string for logs (no query values or fragments)."""
        if not url_string:
            return ''
        parsed = QUrl(url_string)
        scheme = parsed.scheme().strip()
        host = parsed.host().strip()
        path = parsed.path().strip() or '/'
        if not scheme or not host:
            return url_string
        base = f'{scheme}://{host}{path}'
        if parsed.hasQuery():
            return f'{base}?...'
        return base

    def _is_login_redirect_url(self, url_string: str) -> bool:
        """Return True when URL appears to be a login page for this platform."""
        if not url_string:
            return False
        candidate = QUrl(url_string)
        host = candidate.host().strip().lower()
        login_host = QUrl(self.LOGIN_URL).host().strip().lower() if self.LOGIN_URL else ''
        if (
            host
            and not self._matches_cookie_domain(host)
            and (not login_host or host != login_host)
        ):
            return False

        normalized = url_string.lower()
        login_url = self.LOGIN_URL.strip().lower()
        if login_url and normalized.startswith(login_url):
            return True

        path_and_query = f'{candidate.path()}?{candidate.query()}#{candidate.fragment()}'.lower()
        return any(re.search(pattern, path_and_query) for pattern in self.LOGIN_URL_PATTERNS)

    def _run_live_connection_test(self) -> tuple[bool, str | None]:
        """Load a composer page with persisted cookies and ensure no login redirect occurs."""
        test_url = self._get_connection_test_url()
        if not test_url:
            return False, 'WV-LOAD-FAILED'

        storage_path = self._get_profile_storage_path()
        profile = QWebEngineProfile(f'{storage_path.name}_conn_test', None)
        profile.setPersistentStoragePath(str(storage_path))
        profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
        )
        page = _LoggingWebEnginePage(profile, self, None)

        state: dict[str, object] = {
            'ok': False,
            'error': 'WV-LOAD-FAILED',
            'redirected_to_login': False,
            'final_url': '',
        }
        loop = QEventLoop()
        timeout = QTimer()
        timeout.setSingleShot(True)

        def _finish(ok: bool, error: str | None):
            state['ok'] = ok
            state['error'] = error
            if loop.isRunning():
                loop.quit()

        def _on_timeout():
            get_logger().warning(
                f'{self.get_platform_name()} connection test timed out '
                f'(url={self._sanitize_url_for_log(test_url)}, timeout_ms={self.CONNECTION_TEST_TIMEOUT_MS})'
            )
            self._log_webview_debug(
                'Live connection test timed out',
                url=test_url,
                timeout_ms=self.CONNECTION_TEST_TIMEOUT_MS,
            )
            _finish(False, 'WV-LOAD-FAILED')

        def _on_url_changed(url: QUrl):
            current = url.toString()
            state['final_url'] = current
            get_logger().info(
                f'{self.get_platform_name()} connection test page hit: '
                f'{self._sanitize_url_for_log(current)}'
            )
            if self._is_login_redirect_url(current):
                state['redirected_to_login'] = True
                get_logger().warning(
                    f'{self.get_platform_name()} connection test redirected to login: '
                    f'{self._sanitize_url_for_log(current)}'
                )
                self._log_webview_debug(
                    'Live connection test detected login redirect',
                    url=current,
                )
                _finish(False, 'WV-SESSION-EXPIRED')

        def _on_load_finished(ok: bool):
            current = page.url().toString()
            state['final_url'] = current
            if not ok:
                _finish(False, 'WV-LOAD-FAILED')
                return
            if bool(state.get('redirected_to_login')) or self._is_login_redirect_url(current):
                _finish(False, 'WV-SESSION-EXPIRED')
                return
            _finish(True, None)

        page.urlChanged.connect(_on_url_changed)
        page.loadFinished.connect(_on_load_finished)
        timeout.timeout.connect(_on_timeout)

        try:
            get_logger().info(
                f'{self.get_platform_name()} connection test starting '
                f'(target={self._sanitize_url_for_log(test_url)})'
            )
            self._log_webview_debug('Live connection test started', url=test_url)
            timeout.start(self.CONNECTION_TEST_TIMEOUT_MS)
            page.load(QUrl(test_url))
            loop.exec()
            get_logger().info(
                f'{self.get_platform_name()} connection test finished '
                f'(ok={bool(state["ok"])}, error={state["error"]}, '
                f'final_url={self._sanitize_url_for_log(str(state["final_url"]))})'
            )
            self._log_webview_debug(
                'Live connection test finished',
                ok=bool(state['ok']),
                error=state['error'],
                final_url=state['final_url'],
            )
            return bool(state['ok']), state['error'] if isinstance(state['error'], str) else None
        finally:
            timeout.stop()
            with contextlib.suppress(TypeError, RuntimeError):
                page.urlChanged.disconnect(_on_url_changed)
            with contextlib.suppress(TypeError, RuntimeError):
                page.loadFinished.disconnect(_on_load_finished)
            with contextlib.suppress(TypeError, RuntimeError):
                timeout.timeout.disconnect(_on_timeout)
            page.deleteLater()
            profile.deleteLater()

    def _can_run_live_connection_test(self) -> bool:
        """Whether a live WebEngine-based connection test can run in this process."""
        app = QApplication.instance()
        return app is not None and hasattr(app, 'processEvents')

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
            current_url = self._view.url().toString()
            get_logger().warning(
                f'{self.get_platform_name()}: Page load failed '
                f'(url="{current_url}", source={self._pending_nav_source})'
            )
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
        prev_url = self._last_url
        source = self._pending_nav_source
        nav_type = self._pending_nav_type
        if self._pending_nav_target and self._pending_nav_target != url_string:
            source = f'redirect-or-script-after-{self._pending_nav_source}'

        self._log_webview_debug(
            'URL changed',
            from_url=prev_url or '(none)',
            to_url=url_string,
            source=source,
            type=nav_type,
        )

        self._last_url = url_string
        self._pending_nav_target = None
        self._pending_nav_source = 'unknown'
        self._pending_nav_type = 'unknown'

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
            # In the running GUI app, perform a real page-load probe using stored cookies.
            if not self._can_run_live_connection_test():
                self._log_webview_debug(
                    'Skipping live connection test (no QApplication instance available)'
                )
                return True, None
            return self._run_live_connection_test()
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


class _LoggingWebEnginePage(QWebEnginePage):
    """QWebEnginePage that forwards navigation/console events for debug logging."""

    def __init__(
        self,
        profile: QWebEngineProfile,
        platform: BaseWebViewPlatform,
        parent: QWidget | None = None,
    ):
        super().__init__(profile, parent)
        self._platform = platform

    def acceptNavigationRequest(  # noqa: N802
        self,
        url: QUrl,
        nav_type: QWebEnginePage.NavigationType,
        is_main_frame: bool,
    ) -> bool:
        accepted = super().acceptNavigationRequest(url, nav_type, is_main_frame)
        self._platform._on_navigation_request(url, nav_type, is_main_frame, accepted)
        return accepted

    def javaScriptConsoleMessage(  # noqa: N802
        self,
        level: QWebEnginePage.JavaScriptConsoleMessageLevel,
        message: str | None,
        line_number: int,
        source_id: str | None,
    ):
        level_name = BaseWebViewPlatform._enum_label(level)
        self._platform._log_webview_debug(
            'JavaScript console',
            level=level_name,
            source=source_id,
            line=line_number,
            console_message=message,
        )
        super().javaScriptConsoleMessage(level, message, line_number, source_id)
