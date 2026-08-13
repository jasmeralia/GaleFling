"""Abstract base class for WebView-based social media platforms."""

# WebEngine process flags must be set before importing Qt WebEngine modules.
# ruff: noqa: E402

import base64
import contextlib
import json
import logging
import mimetypes
import re
import sqlite3
import time
from collections.abc import Callable, Iterable
from pathlib import Path

from src.core.webview_environment import (
    disable_conditional_passkey_ui,
)
from src.core.webview_session_import import (
    ImportedSession,
    effective_user_agent,
    load_session_metadata,
    save_session_metadata,
    session_recently_imported,
)
from src.utils.constants import VIDEO_EXTENSIONS

# Platform classes are also imported directly by tests and support tooling that
# bypass the application entry point. Keep the process-wide policy consistent.
disable_conditional_passkey_ui()

from PyQt6.QtCore import QDateTime, QEvent, QEventLoop, QPointF, Qt, QTimer, QUrl
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtNetwork import QNetworkCookie
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication, QWidget

from src.core.logger import get_logger
from src.platforms.base import BasePlatform
from src.utils.constants import PostResult
from src.utils.helpers import get_app_data_dir

_SESSION_TOKEN_SCRIPT_NAME = 'galefling_session_token'


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

    Profile sharing
    ---------------
    Cloudflare Bot Management fingerprints each Chromium browser context
    (Canvas, WebGL, TLS).  Creating a fresh QWebEngineProfile for every
    operation (login window, connection test, posting panel) produces a new
    context with a different fingerprint, causing Cloudflare to re-challenge
    even when valid session cookies are present.

    To avoid this, profiles are stored in a class-level registry keyed by
    account_id.  Every platform instance for the same account reuses the
    same QWebEngineProfile object — and therefore the same Chromium context —
    for the lifetime of the application process.  The profile is NOT parented
    to any transient widget; this also eliminates the Qt "Release of profile
    requested but WebEnginePage still not deleted" ordering warning.
    """

    # Maps account_id → QWebEngineProfile, shared across all platform instances
    # for the same account within a single process lifetime.
    _profile_registry: dict[str, 'QWebEngineProfile'] = {}

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
    # CSS selectors whose presence in the DOM after a successful page load
    # indicates an expired session (e.g. an inline login form).  Subclasses
    # that cannot rely on a URL redirect to signal session expiry should set
    # this list.  The check runs as a JS querySelector after loadFinished.
    # Composer file-input selector for platforms with a single multi-accept input.
    # Platforms with one composer per media type override get_media_file_selector().
    MEDIA_FILE_SELECTOR: str = ''
    # Selector for a modal backdrop that covers the composer and swallows the first
    # click on the page.  Set it to have dismiss_blocking_overlay() clear it after
    # load; leave it empty and no overlay handling runs.
    BLOCKING_OVERLAY_SELECTOR: str = ''
    # Exact labels of the dialog's decline control, e.g. ['Maybe Later'].  Matched
    # case-insensitively but *exactly* — never as a substring, because the affirmative
    # button ('Yes, Enable') sits directly beside it.  Empty falls back to clicking
    # the backdrop.
    BLOCKING_OVERLAY_DISMISS_LABELS: list[str] = []
    BLOCKING_OVERLAY_ATTEMPTS: int = 3
    SESSION_EXPIRED_SELECTORS: list[str] = []
    # Milliseconds to wait after loadFinished before running the
    # SESSION_EXPIRED_SELECTORS DOM check.  Set this on platforms whose login
    # form is injected by a JS framework (e.g. Vue.js) rather than server-side
    # rendered, so the framework has time to mount before the check runs.
    SESSION_EXPIRED_CHECK_DELAY_MS: int = 0
    COOKIE_DOMAINS: list[str] = []
    AUTH_COOKIE_NAMES: list[str] = []
    AUTH_COOKIE_NAME_PATTERNS: list[str] = []
    PREFILL_DELAY_MS: int = 200
    POLL_INTERVAL_MS: int = 500
    POLL_TIMEOUT_MS: int = 30000
    CONNECTION_TEST_TIMEOUT_MS: int = 12000
    # Milliseconds to wait after creating the test QWebEngineProfile before
    # issuing the first navigation.  Chromium needs time to start its browser
    # context and load the persisted cookie store from disk; navigating
    # immediately produces an unauthenticated request even though valid cookies
    # exist on disk.  800 ms is enough for a cold-start profile on Windows.
    CONNECTION_TEST_STARTUP_DELAY_MS: int = 800
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
        self._page: QWebEnginePage | None = None
        self._profile: QWebEngineProfile | None = None
        self._captured_post_url: str | None = None
        self._post_confirmed = False
        self._text: str = ''
        self._image_path: Path | None = None
        # Files handed to Chromium's file picker via _LoggingWebEnginePage.chooseFiles().
        self._staged_picker_files: list[str] = []
        self._picker_invocations = 0
        # Tests set this so an unstaged picker returns [] instead of opening a real
        # native dialog, which would block the run with nothing able to dismiss it.
        self.suppress_native_file_dialog = False
        self._poll_timer: QTimer | None = None
        self._poll_elapsed_ms: int = 0
        self._last_url: str = ''
        self._pending_nav_target: str | None = None
        self._pending_nav_source: str = 'unknown'
        self._pending_nav_type: str = 'unknown'

    # ── Profile & view management ───────────────────────────────────

    @classmethod
    def _get_or_create_profile(cls, account_id: str, storage_path: 'Path') -> 'QWebEngineProfile':
        """Return the shared QWebEngineProfile for this account, creating it if needed.

        The profile is owned by this registry (no Qt parent) so it is never
        destroyed by transient widget cleanup.  All views for the same account
        share the same Chromium browser context and therefore the same
        Cloudflare fingerprint.
        """
        key = account_id or 'default'
        if key not in cls._profile_registry:
            profile = QWebEngineProfile(storage_path.name, None)
            profile.setHttpUserAgent(effective_user_agent(storage_path, profile.httpUserAgent()))
            profile.setPersistentStoragePath(str(storage_path))
            profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
            )
            cls._install_session_token_script(profile, storage_path)
            cls._profile_registry[key] = profile
        return cls._profile_registry[key]

    @classmethod
    def _install_session_token_script(
        cls, profile: 'QWebEngineProfile', storage_path: 'Path'
    ) -> None:
        """Seed the site's device token into localStorage for an imported session.

        The OnlyFans web app reads ``bcTokenSha`` from localStorage and sends it
        as the ``x-bc`` header on every API call. Cookies alone are not enough:
        without the token that the session was issued against, the site's own
        JavaScript is treated as an anonymous client and renders a login form
        even though the session cookies are present and valid.
        """
        metadata = load_session_metadata(storage_path)
        token = (metadata or {}).get('x_bc')
        if not token or not cls.COOKIE_DOMAINS:
            return
        scripts = profile.scripts()
        if scripts is None:
            return
        for existing in scripts.find(_SESSION_TOKEN_SCRIPT_NAME):
            scripts.remove(existing)

        host = json.dumps(cls.COOKIE_DOMAINS[0].lstrip('.'))
        js = f"""
(function () {{
    try {{
        if (window.location.hostname.indexOf({host}) === -1) {{ return; }}
        window.localStorage.setItem('bcTokenSha', {json.dumps(token)});
    }} catch (e) {{ /* storage unavailable on this origin */ }}
}})();
"""

        script = QWebEngineScript()
        script.setName(_SESSION_TOKEN_SCRIPT_NAME)
        script.setSourceCode(js)
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(False)
        scripts.insert(script)

    @classmethod
    def _evict_profile(cls, account_id: str) -> None:
        """Remove the profile for this account from the registry.

        Call this when the stored session is intentionally cleared (e.g. Reset
        Session Cookies) so the next login window starts with a fresh context.
        """
        cls._profile_registry.pop(account_id or 'default', None)

    @staticmethod
    def _wait_ms(milliseconds: int) -> None:
        """Pump the Qt event loop for the given duration."""
        loop = QEventLoop()
        QTimer.singleShot(milliseconds, loop.quit)
        loop.exec()

    def import_session(self, session: ImportedSession) -> tuple[bool, str | None]:
        """Import a browser-exported session into this account's WebEngine profile."""
        storage_path = self._get_profile_storage_path()
        try:
            save_session_metadata(storage_path, session)
        except OSError:
            return (
                False,
                'GaleFling could not save the imported session. '
                'Check that the application data folder is writable and try again.',
            )

        if not self.COOKIE_DOMAINS:
            return False, 'This platform does not support session import.'

        key = self._account_id or 'default'
        if key in self._profile_registry:
            self._evict_profile(self._account_id)
            self._profile = None
            self._view = None
            self._page = None

        profile = self._get_or_create_profile(self._account_id, storage_path)
        self._profile = profile
        profile.setHttpUserAgent(session.user_agent)

        # Chromium only initialises a profile's storage backend once a page
        # exists for it.  Without one, setCookie() writes into a context that is
        # never flushed to disk, so the cookies vanish and verification below
        # fails even though the export is perfectly good.  The view is never
        # shown; it exists purely to bring the browser context up.
        if self._page is None:
            self.create_webview()
        if self._page is not None:
            self._page.load(QUrl('about:blank'))
            self._wait_ms(1000)

        expiration = QDateTime.currentDateTimeUtc().addDays(365)
        base_domain = self.COOKIE_DOMAINS[0].lstrip('.')
        domain = f'.{base_domain}'
        # Derive the origin from the platform rather than hard-coding one, so
        # this base-class helper stays correct for every WebView platform.
        origin = QUrl(f'https://{base_domain}/')
        cookie_store = profile.cookieStore()
        if cookie_store is None:
            return (
                False,
                'GaleFling could not access the browser cookie store. '
                'Restart GaleFling and try the import again.',
            )
        # Force the store to bind to its on-disk backend before writing, so the
        # injected cookies join the persisted set rather than a transient one.
        cookie_store.loadAllCookies()
        self._wait_ms(500)

        # Verify against the live cookie store, NOT has_valid_session(): that
        # reads the Chromium SQLite file, which is only flushed roughly every
        # 30 seconds.  Polling the file here would time out on a perfectly valid
        # export and tell the user it was stale — the worst possible advice,
        # since acting on it burns another session.
        accepted: set[str] = set()
        expected = set(session.cookies)
        connection = cookie_store.cookieAdded.connect(
            lambda cookie: accepted.add(bytes(cookie.name()).decode('utf-8', 'replace'))
        )

        for name, value in session.cookies.items():
            cookie = QNetworkCookie(name.encode('utf-8'), value.encode('utf-8'))
            cookie.setDomain(domain)
            cookie.setPath('/')
            cookie.setSecure(True)
            cookie.setHttpOnly(True)
            cookie.setExpirationDate(expiration)
            cookie_store.setCookie(cookie, origin)

        deadline = time.monotonic() + 5.0
        while not expected.issubset(accepted) and time.monotonic() < deadline:
            self._wait_ms(100)

        with contextlib.suppress(TypeError, RuntimeError):
            cookie_store.cookieAdded.disconnect(connection)

        if expected.issubset(accepted):
            return True, None
        rejected = sorted(expected - accepted)
        return (
            False,
            'GaleFling could not install the session cookies '
            f'({", ".join(rejected)}). Export auth.json again and re-import it.',
        )

    def create_webview(self, parent: QWidget | None = None) -> QWebEngineView:
        """Create a QWebEngineView backed by the shared persistent profile."""
        storage_path = self._get_profile_storage_path()

        # Reuse the process-lifetime profile for this account.  The profile is
        # NOT parented to `parent` so it survives the login dialog closing and
        # is available for subsequent connection tests and posting windows.
        self._profile = self._get_or_create_profile(self._account_id, storage_path)

        page = _LoggingWebEnginePage(self._profile, self, parent)
        self._configure_webview_page(page)
        self._view = QWebEngineView(parent)
        self._view.setPage(page)
        # Hold a reference to the page for the platform's lifetime.  setPage()
        # does not transfer ownership to Python, so without this the page is
        # garbage-collected as soon as create_webview() returns and the view
        # silently falls back to Qt's default off-the-record profile — which
        # never writes cookies to disk, so no session would ever persist.
        self._page = page

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
        if self._has_persisted_session():
            return True
        # A session imported moments ago is already live in Chromium's cookie
        # store — the import only succeeds once the store accepts it — but will
        # not reach the database until the next flush.  Trust it for that window
        # so a successful import is not reported to the user as expired.
        return session_recently_imported(self._get_profile_storage_path())

    def _has_persisted_session(self) -> bool:
        """Check the on-disk cookie database for a valid session."""
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
        if login_url:
            # Prefix matching is only meaningful when LOGIN_URL has a path of its own
            # (e.g. https://fetlife.com/login).  A bare origin such as Fansly's
            # https://fansly.com/ is a prefix of *every* page on the site, so prefix
            # matching there classified the whole platform as a login page and made
            # test_connection() report WV-SESSION-EXPIRED against a perfectly valid
            # session.  For a bare origin only the landing page itself counts.
            login_path = QUrl(login_url).path().strip('/')
            if login_path:
                if normalized.startswith(login_url):
                    return True
            elif normalized.rstrip('/') == login_url.rstrip('/'):
                return True

        path_and_query = f'{candidate.path()}?{candidate.query()}#{candidate.fragment()}'.lower()
        return any(re.search(pattern, path_and_query) for pattern in self.LOGIN_URL_PATTERNS)

    def _run_live_connection_test(self) -> tuple[bool, str | None]:
        """Load a composer page with persisted cookies and ensure no login redirect occurs."""
        test_url = self._get_connection_test_url()
        if not test_url:
            return False, 'WV-LOAD-FAILED'

        storage_path = self._get_profile_storage_path()
        # Always use the shared registry profile so the connection test runs
        # in the same Chromium browser context as the login window and posting
        # panel.  This ensures Cloudflare sees the same fingerprint it already
        # accepted during login, rather than treating each test as a new bot.
        profile = self._get_or_create_profile(self._account_id, storage_path)
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
            selectors = self.SESSION_EXPIRED_SELECTORS
            if not selectors:
                _finish(True, None)
                return
            combined = json.dumps(', '.join(selectors))

            def _run_dom_check():
                def _dom_result(found):
                    if found:
                        self._log_webview_debug(
                            'Live connection test: expired session detected via DOM selector'
                        )
                        get_logger().warning(
                            f'{self.get_platform_name()} connection test: '
                            'expired session detected via DOM (inline login form present)'
                        )
                        _finish(False, 'WV-SESSION-EXPIRED')
                    else:
                        _finish(True, None)

                page.runJavaScript(f'!!document.querySelector({combined})', _dom_result)

            delay = self.SESSION_EXPIRED_CHECK_DELAY_MS
            if delay > 0:
                QTimer.singleShot(delay, _run_dom_check)
            else:
                _run_dom_check()

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
            # Defer the first navigation so Chromium has time to start its
            # browser context and load persisted cookies from disk.  Without
            # this delay the cookie store is empty and every request is
            # unauthenticated regardless of what is stored on disk.
            QTimer.singleShot(
                self.CONNECTION_TEST_STARTUP_DELAY_MS,
                lambda: page.load(QUrl(test_url)),
            )
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
        if self.BLOCKING_OVERLAY_SELECTOR:
            self.dismiss_blocking_overlay()
        if self._text:
            self._inject_text(self._text)
        if self.SUCCESS_SELECTOR:
            QTimer.singleShot(500, self._inject_success_observer)

    # ── Blocking overlays ───────────────────────────────────────────

    def dismiss_blocking_overlay(
        self, callback: 'Callable[[dict], None] | None' = None, _attempt: int = 1
    ) -> None:
        """Dismiss a modal covering the composer, if one is present.

        Some platforms greet a session with a dialog — a notifications prompt, a
        promo — behind a full-page backdrop that swallows the first click anywhere on
        the page. Left in place it costs the *user* a click too, and any automation
        that clicks blind through it is aiming at whatever coordinates it wanted with
        an unknown dialog in front.

        Dismissal prefers the dialog's **own decline control**, matched by exact label
        against ``BLOCKING_OVERLAY_DISMISS_LABELS`` — the same rule FetLife's shipped
        "Maybe later" dismissal uses. Exact matching is what makes this safe: these
        prompts put an affirmative button directly beside the decline one, and a
        substring or keyword match is how you end up enabling something on the account
        holder's behalf.

        When no declared label is on screen it falls back to clicking the **backdrop
        element itself** — the standard dismiss gesture, dispatched on that element
        rather than at a point, so it cannot land on a control inside the dialog.

        Platforms opt in by setting ``BLOCKING_OVERLAY_SELECTOR``.
        """
        if not self._view or not self.BLOCKING_OVERLAY_SELECTOR:
            return
        page = self._view.page()
        if not page:
            return

        selector = json.dumps(self.BLOCKING_OVERLAY_SELECTOR)
        labels = json.dumps(
            [label.strip().lower() for label in self.BLOCKING_OVERLAY_DISMISS_LABELS]
        )
        js = f"""
        (function() {{
            function shown(el) {{
                if (!el) return false;
                var r = el.getBoundingClientRect();
                var s = getComputedStyle(el);
                return r.width > 0 && r.height > 0
                    && s.display !== 'none' && s.visibility !== 'hidden';
            }}
            var el = document.querySelector({selector});
            if (!shown(el)) return {{present: false, dismissed: true}};

            // The dialog is not necessarily inside the backdrop — on Fansly it is a
            // sibling — so describe it separately for the log.
            var dialog = document.querySelector('[class*="active-modal"]');
            var text = dialog
                ? (dialog.textContent || '').trim().replace(/\\s+/g, ' ').substring(0, 160)
                : '';

            // Exact label match only. Never a substring: the affirmative button sits
            // beside the decline one.
            var wanted = {labels};
            var decline = Array.from(document.querySelectorAll(
                'button, a, [role="button"], div[class*="btn"], span[class*="btn"]'
            )).filter(shown).filter(function(b) {{
                return wanted.indexOf((b.textContent || '').trim().toLowerCase()) !== -1;
            }})[0];

            var via;
            if (decline) {{
                via = 'label:' + (decline.textContent || '').trim();
                decline.click();
            }} else {{
                via = 'backdrop';
                el.click();
            }}
            return {{
                present: true,
                dismissed: !shown(document.querySelector({selector})),
                via: via,
                text: text
            }};
        }})();
        """

        def _handle(result):
            state = result if isinstance(result, dict) else {}
            if state.get('present'):
                get_logger().info(
                    f'{self.get_platform_name()}: blocking overlay '
                    f'{"dismissed" if state.get("dismissed") else "still present"} '
                    f'(attempt {_attempt}, via={state.get("via")}, '
                    f'dialog="{state.get("text", "")}")'
                )
            if (
                state.get('present')
                and not state.get('dismissed')
                and _attempt < self.BLOCKING_OVERLAY_ATTEMPTS
            ):
                QTimer.singleShot(
                    self.POLL_INTERVAL_MS,
                    lambda: self.dismiss_blocking_overlay(callback, _attempt + 1),
                )
                return
            if callback:
                callback(state)

        page.runJavaScript(js, _handle)

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

    # ── Media attachment ────────────────────────────────────────────

    def get_media_file_selector(self, path: 'Path | None' = None) -> str | None:
        """Return the composer file-input selector for *path* (or the staged media).

        Defaults to ``MEDIA_FILE_SELECTOR``. Platforms that use a different composer
        per media type override this to route by extension.
        """
        return self.MEDIA_FILE_SELECTOR or None

    def stage_media_for_picker(self, path: Path) -> None:
        """Queue *path* to satisfy the next native file-picker request.

        Chromium refuses to open a file dialog without user activation, so staging alone
        does nothing — something must then trigger the picker from a trusted gesture.
        See open_media_picker().
        """
        self._staged_picker_files = [str(path)]

    def take_staged_picker_files(self) -> list[str]:
        """Consume the staged selection. Called by the page's chooseFiles() override."""
        self._picker_invocations += 1
        staged, self._staged_picker_files = self._staged_picker_files, []
        return staged

    @property
    def picker_invocations(self) -> int:
        """How many times the file picker has been satisfied for this platform."""
        return self._picker_invocations

    def trusted_click(
        self, selector: str | tuple[str, ...], callback: Callable[[dict], None] | None = None
    ) -> None:
        """Click a visible element with a real Qt mouse event, granting user activation.

        Chromium refuses to open a file picker without user activation, and JavaScript
        cannot grant it — a ``runJavaScript``-driven click is rejected outright. A
        synthesised ``QMouseEvent`` delivered to the render widget *is* trusted, and the
        activation it grants then lets a subsequent JS ``input.click()`` through.

        Measured 2026-08-12 against a local page, comparing every candidate mechanism:

        | Mechanism | ``userActivation`` | ``chooseFiles()`` |
        |---|---|---|
        | JS ``.click()`` alone | False | not called |
        | ``QApplication.sendEvent`` | True | called |
        | ``QApplication.postEvent`` | True | called |
        | ``QTest.mouseClick`` | True | called |

        So this needs no ``QtTest`` import — that module is a test-harness dependency and
        has no business in shipped code. The event must go to the view's **focusProxy**
        (the render widget), not the view itself.

        **Confirmed on the target platform.** The table above was measured on Linux
        (xcb under Xvfb); ``test_webview_user_activation.py`` was then re-run in the
        Windows 11 VM and passes there too, on a GPU-less guest. Qt-level event
        synthesis into Chromium therefore does not depend on the platform plugin or on
        hardware acceleration — which matters, because every media upload is built on
        it and Windows is the shipping target.

        *selector* may be a tuple; the first match with real dimensions wins. The element
        must be genuinely visible: composers hide their file inputs, so a hidden input has
        no coordinates to click and this reports failure rather than clicking at (0, 0).
        """
        if not self._view:
            if callback:
                callback({'clicked': False, 'reason': 'no webview'})
            return
        page = self._view.page()
        if not page:
            if callback:
                callback({'clicked': False, 'reason': 'no page'})
            return

        selectors = (selector,) if isinstance(selector, str) else tuple(selector)

        def _measured(rect):
            if not isinstance(rect, dict) or not rect.get('found'):
                if callback:
                    callback({'clicked': False, 'reason': 'no visible element', 'detail': rect})
                return
            x, y = int(rect['x']), int(rect['y'])
            self._send_trusted_click(x, y)
            if callback:
                callback({'clicked': True, 'x': x, 'y': y, 'selector': rect.get('selector')})

        js = f"""
        (function() {{
            var selectors = {json.dumps(list(selectors))};
            for (var i = 0; i < selectors.length; i++) {{
                var el = document.querySelector(selectors[i]);
                if (!el) continue;
                el.scrollIntoView({{block: 'center', inline: 'center'}});
                var r = el.getBoundingClientRect();
                if (r.width <= 0 || r.height <= 0) continue;
                var x = Math.round(r.left + r.width / 2);
                var y = Math.round(r.top + r.height / 2);
                if (x < 0 || y < 0 || x >= window.innerWidth || y >= window.innerHeight) {{
                    continue;
                }}
                return {{found: true, x: x, y: y, selector: selectors[i]}};
            }}
            return {{found: false, tried: selectors}};
        }})();
        """
        page.runJavaScript(js, _measured)

    def _send_trusted_click(self, x: int, y: int) -> None:
        """Deliver a press/release pair at viewport coordinates to the render widget."""
        if not self._view:
            return
        target = self._view.focusProxy() or self._view
        pos = QPointF(x, y)
        for event_type in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            QApplication.sendEvent(
                target,
                QMouseEvent(
                    event_type,
                    pos,
                    pos,
                    Qt.MouseButton.LeftButton,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                ),
            )

    def open_media_picker(
        self, path: Path | None = None, callback: Callable[[dict], None] | None = None
    ) -> None:
        """Ask the page to open its file picker for the composer's media input.

        The click is issued from JavaScript, which carries no user activation of its
        own. Chromium accepts it only if a *trusted* gesture has already activated the
        page — verified 2026-08-12: a JS ``input.click()`` fires chooseFiles when
        ``navigator.userActivation.isActive`` is true, and is refused with "File chooser
        dialog can only be shown with a user activation" when it is not. Use
        ``trusted_click()`` to supply that gesture first.

        **Refuses to click without activation** rather than clicking anyway. Chromium
        swallows the refused click silently, so the JS still completes and an
        ``opened: true`` return would be indistinguishable from success — measured
        directly: without a prior gesture this reported ``opened: true`` while
        ``picker_invocations`` never moved. Reporting the refusal is what makes the
        return mean what it says.
        """
        if not self._view:
            return
        page = self._view.page()
        if not page:
            return
        selector = self.get_media_file_selector(path)
        if not selector:
            if callback:
                callback({'opened': False, 'reason': 'platform declares no media file input'})
            return

        js = f"""
        (function() {{
            var input = document.querySelector({json.dumps(selector)});
            if (!input) return {{opened: false, reason: 'file input not found'}};
            var active = !!(navigator.userActivation && navigator.userActivation.isActive);
            if (!active) {{
                return {{
                    opened: false,
                    reason: 'no user activation — call trusted_click() first',
                    userActivationActive: false
                }};
            }}
            input.click();
            return {{opened: true, userActivationActive: true}};
        }})();
        """
        if callback:
            page.runJavaScript(js, callback)
        else:
            page.runJavaScript(js)

    def _attach_media(self, path: Path, callback: Callable[[dict], None] | None = None) -> None:
        """Attach a local file to the open upload composer's file input.

        The file is handed to the picker input via a synthetic ``DataTransfer`` so the
        page's own change handlers run.  This reports only that the file was written and
        the events dispatched — **not** that the form accepted it.  The picture composer
        moves the file to a hidden ``picture[attachments][]`` field and clears the picker
        asynchronously, so acceptance must be observed by polling
        ``_media_attachment_state()`` rather than read back here.

        The file is inlined into the script as base64, which bounds this to modest
        media.  Wiring media upload into the automatic post flow (task #417 Level B)
        should instead override ``QWebEnginePage.chooseFiles()`` and hand Chromium the
        path directly — no size ceiling and a genuinely native file-picker path.
        """
        if not self._view:
            return
        page = self._view.page()
        if not page:
            return

        selector = self.get_media_file_selector(path)
        if not selector:
            if callback:
                callback({'dispatched': False, 'reason': 'platform declares no media file input'})
            return
        mime, _ = mimetypes.guess_type(str(path))
        if not mime:
            mime = 'video/mp4' if path.suffix.lower() in VIDEO_EXTENSIONS else 'image/jpeg'

        try:
            data_b64 = base64.b64encode(path.read_bytes()).decode('ascii')
        except OSError as exc:
            if callback:
                callback({'dispatched': False, 'reason': f'could not read {path.name}: {exc}'})
            return

        js = f"""
        (function() {{
            var input = document.querySelector({json.dumps(selector)});
            if (!input) return {{dispatched: false, reason: 'file input not found'}};
            var binary = atob({json.dumps(data_b64)});
            var bytes = new Uint8Array(binary.length);
            for (var i = 0; i < binary.length; i++) {{
                bytes[i] = binary.charCodeAt(i);
            }}
            var transfer = new DataTransfer();
            transfer.items.add(
                new File([bytes], {json.dumps(path.name)}, {{type: {json.dumps(mime)}}})
            );
            input.files = transfer.files;
            input.dispatchEvent(new Event('input', {{bubbles: true}}));
            input.dispatchEvent(new Event('change', {{bubbles: true}}));
            return {{dispatched: true, fileName: {json.dumps(path.name)}}};
        }})();
        """
        if callback:
            page.runJavaScript(js, callback)
        else:
            page.runJavaScript(js)

    def _media_attachment_state(self, callback: Callable[[dict], None] | None = None) -> None:
        """Report how many files the open upload form is currently holding.

        Counts across every ``input[type="file"]`` on the page rather than the picker we
        wrote to.  The picture composer hands the file to ``picture[attachments][]`` and
        empties the picker, so inspecting the picker alone reports zero on success.
        Poll this after ``_attach_media()`` — the hand-off is asynchronous.
        """
        if not self._view:
            return
        page = self._view.page()
        if not page:
            return

        js = """
        (function() {
            var total = 0;
            var holders = [];
            document.querySelectorAll('input[type="file"]').forEach(function(el) {
                if (el.files && el.files.length) {
                    total += el.files.length;
                    holders.push(el.name || el.id || '<unnamed>');
                }
            });
            return {attached: total > 0, fileCount: total, holders: holders};
        })();
        """
        if callback:
            page.runJavaScript(js, callback)
        else:
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
        account_key = self._account_id or 'default'
        if account_key in BaseWebViewPlatform._profile_registry:
            # The profile is already loaded in this process (login window was
            # opened, or a previous connection test ran).  Skip the SQLite
            # cookie check — Chromium may have the DB locked — and go straight
            # to the live page-load test using the shared profile.
            if not self._can_run_live_connection_test():
                return True, None
            return self._run_live_connection_test()
        # Cold start: no profile in memory yet.  Check persisted cookies first
        # so we don't spin up a Chromium context unnecessarily.
        if self.has_valid_session():
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

    def chooseFiles(  # noqa: N802 - mirrors Qt API
        self,
        mode: QWebEnginePage.FileSelectionMode,
        oldFiles: Iterable[str | None],  # noqa: N803 - mirrors Qt API
        acceptedMimeTypes: Iterable[str | None],  # noqa: N803 - mirrors Qt API
    ) -> list[str]:
        """Satisfy a page's file picker from the platform's staged selection.

        This is how media reaches a WebView composer.  Chromium treats the returned
        paths as a genuine user file selection and fires a real ``change`` event with a
        real ``File`` — which is what site uploaders expect.  Assigning a synthetic
        ``DataTransfer`` from JavaScript does not achieve that: Fansly's uploader
        ignores it outright.

        With nothing staged this falls through to Qt's own handler, so a user who opens
        a picker themselves still gets the native dialog.  Functional tests set
        ``suppress_native_file_dialog`` to return an empty selection instead — a real
        modal dialog in a headless run blocks forever with nothing able to dismiss it.
        """
        staged = self._platform.take_staged_picker_files()
        if staged:
            return staged
        if self._platform.suppress_native_file_dialog:
            return []
        return super().chooseFiles(mode, oldFiles, acceptedMimeTypes)

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
