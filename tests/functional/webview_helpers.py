"""Shared helpers for WebView functional tests.

Provides page loading, JS execution, event loop utilities, platform-backed
WebView creation via ``BaseWebViewPlatform.create_webview()``, and test-only
login helpers for platforms that still support automated session refresh.
"""

import contextlib
import gc
import json
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QEventLoop, Qt, QTimer, QUrl
from PyQt6.QtTest import QTest
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication

from src.platforms.base_webview import BaseWebViewPlatform
from src.platforms.fansly import FanslyPlatform
from src.platforms.fetlife import FetLifePlatform
from src.platforms.onlyfans import OnlyFansPlatform
from src.platforms.snapchat import SnapchatPlatform

_PLATFORM_CLASSES: dict[str, type[BaseWebViewPlatform]] = {
    'onlyfans': OnlyFansPlatform,
    'fansly': FanslyPlatform,
    'fetlife': FetLifePlatform,
    'snapchat': SnapchatPlatform,
}

# Non-zero while close_webview() is deliberately destroying a page.  The renderer
# crash monitor in conftest uses this to tell an intentional teardown apart from a
# renderer that exited on its own mid-test.
_TEARDOWN_DEPTH = 0


def platform_class_for_account(account_id: str) -> type[BaseWebViewPlatform]:
    """Return the WebView platform class for a GaleFling account id."""
    prefix = account_id.split('_', 1)[0]
    platform_cls = _PLATFORM_CLASSES.get(prefix)
    if platform_cls is None:
        raise ValueError(f'No WebView platform registered for account_id {account_id!r}')
    return platform_cls


def get_or_create_app():
    """Return existing QApplication or create one."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(['galefling_functional_test'])
    return app


def wait_ms(ms: int):
    """Block the event loop for the given number of milliseconds."""
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(ms)
    loop.exec()


def load_page(page: QWebEnginePage, url: str, timeout_ms: int = 15000) -> tuple[bool, str]:
    """Load a URL and wait for it to finish. Returns (ok, final_url)."""
    state: dict = {'loaded': False, 'ok': False}

    def on_load(ok):
        state['loaded'] = True
        state['ok'] = ok

    page.loadFinished.connect(on_load)

    loop = QEventLoop()
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)

    check = QTimer()
    check.setInterval(300)
    check.timeout.connect(lambda: loop.quit() if state['loaded'] else None)
    check.start()

    page.load(QUrl(url))
    timeout.start(timeout_ms)
    loop.exec()
    check.stop()
    timeout.stop()

    with contextlib.suppress(TypeError, RuntimeError):
        page.loadFinished.disconnect(on_load)

    return state['ok'], page.url().toString()


def run_js(page: QWebEnginePage, js: str, timeout_ms: int = 5000):
    """Execute JavaScript and return the result synchronously."""
    state: dict = {'done': False, 'value': None}

    def callback(value):
        state['done'] = True
        state['value'] = value

    page.runJavaScript(js, callback)

    loop = QEventLoop()
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)

    check = QTimer()
    check.setInterval(200)
    check.timeout.connect(lambda: loop.quit() if state['done'] else None)
    check.start()

    timeout.start(timeout_ms)
    loop.exec()
    check.stop()
    timeout.stop()

    return state['value']


# Confirmation controls only, scoped to the dialog/form that the delete action
# opened.  An unscoped ``button[type="submit"]`` lookup would match the first submit
# button anywhere on the page — on FetLife that is the site search form.
_CONFIRM_DELETE_JS = """
(function() {
    var scope = document.querySelector(
        '[role="dialog"], [role="alertdialog"], .modal, dialog[open], form[data-turbo-confirm]'
    ) || document;
    var btn = Array.from(scope.querySelectorAll(
        'button[type="submit"], input[type="submit"], .confirm-delete, [data-confirm], button'
    )).find(function(el) {
        var label = (el.textContent || el.value || '').trim().toLowerCase();
        return label.includes('delete') || label.includes('confirm')
            || label === 'yes' || label === 'ok';
    });
    if (!btn) return {confirmed: false, scoped: scope !== document};
    btn.click();
    return {confirmed: true, label: (btn.textContent || btn.value || '').trim()};
})();
"""


def _confirmed(result) -> bool:
    """Whether a confirmation click actually landed (not merely attempted)."""
    return bool(isinstance(result, dict) and result.get('confirmed'))


def attempt_delete_current_post(page: QWebEnginePage) -> dict:
    """Best-effort deletion of the post currently shown in the WebView.

    ``deleted`` reflects whether a confirmation control was actually clicked, not
    merely that a delete link was found — cleanup that silently did nothing must not
    report success, or stray live posts go unnoticed.
    """
    wait_ms(2000)
    delete_result = run_js(
        page,
        """
        (function() {
            var links = Array.from(document.querySelectorAll('a, button'));
            var deleteLink = links.find(function(el) {
                var text = el.textContent.trim().toLowerCase();
                return text === 'delete' || text === 'remove'
                    || text.includes('delete this');
            });
            if (deleteLink) {
                deleteLink.click();
                return {found: true, text: deleteLink.textContent.trim()};
            }
            var menuBtn = links.find(function(el) {
                var label = (el.getAttribute('aria-label') || '').toLowerCase();
                return label.includes('more') || label.includes('option')
                    || label.includes('menu');
            });
            if (menuBtn) {
                menuBtn.click();
                return {found: false, menu_opened: true};
            }
            return {found: false, menu_opened: false};
        })();
        """,
    )
    if (
        isinstance(delete_result, dict)
        and delete_result.get('menu_opened')
        and not delete_result.get('found')
    ):
        wait_ms(1000)
        delete_result2 = run_js(
            page,
            """
            (function() {
                var items = Array.from(document.querySelectorAll(
                    'a, button, [role="menuitem"]'
                ));
                var del_item = items.find(function(el) {
                    return el.textContent.trim().toLowerCase().includes('delete');
                });
                if (del_item) { del_item.click(); return {clicked: true}; }
                return {clicked: false};
            })();
            """,
        )
        if isinstance(delete_result2, dict) and delete_result2.get('clicked'):
            wait_ms(2000)
            confirm = run_js(page, _CONFIRM_DELETE_JS)
            wait_ms(2000)
            return {'deleted': _confirmed(confirm), 'via': 'menu', 'confirm': confirm}
    if isinstance(delete_result, dict) and delete_result.get('found'):
        wait_ms(2000)
        confirm = run_js(page, _CONFIRM_DELETE_JS)
        wait_ms(2000)
        return {'deleted': _confirmed(confirm), 'via': 'direct', 'confirm': confirm}
    return {'deleted': False, 'detail': delete_result}


def create_webview(
    data_dir: Path, account_id: str
) -> tuple[QWebEngineView, QWebEnginePage, BaseWebViewPlatform]:
    """Create a WebView through the shipped platform implementation.

    Uses ``BaseWebViewPlatform.create_webview()`` so functional tests exercise
    the same profile registry, page lifecycle, URL handlers, and injected scripts
    as the application.  The app must NOT be running simultaneously — Chromium
    holds an exclusive SQLite WAL lock on the cookie database.
    """
    data_path = Path(data_dir)
    platform_cls = platform_class_for_account(account_id)
    with patch('src.platforms.base_webview.get_app_data_dir', return_value=data_path):
        platform = platform_cls(account_id=account_id)
        view = platform.create_webview()
        view.resize(1280, 900)
        view.show()
        page = platform._page
        if page is None:
            raise RuntimeError(
                f'{platform_cls.__name__}.create_webview() did not retain a page reference'
            )
        return view, page, platform


def teardown_in_progress() -> bool:
    """Whether a test WebView is currently being torn down by close_webview()."""
    return _TEARDOWN_DEPTH > 0


def _pump_deferred_deletes(ms: int = 500) -> None:
    """Run pending deleteLater() calls so C++ objects are destroyed before we continue."""
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    wait_ms(ms)
    if app is not None:
        app.processEvents()


def close_webview(
    view: QWebEngineView,
    page: QWebEnginePage,
    platform: BaseWebViewPlatform,
) -> None:
    """Tear down a platform-backed test WebView and fully release its shared profile.

    ``BaseWebViewPlatform._evict_profile()`` only drops the registry key — it does not
    destroy the ``QWebEngineProfile`` or release Chromium's lock on the profile's
    persistent storage directory.  The profile lives until its last Python reference
    goes away, and ``platform._profile`` is one of them.

    That distinction is load-bearing.  When a test *fails*, pytest keeps the assertion
    traceback alive, which keeps the test frame's ``view`` / ``page`` / ``platform``
    locals alive with it.  If this function does not clear every reference itself, the
    old profile survives the test, the next ``create_webview()`` builds a *second*
    profile against the same ``persistentStoragePath``, and Chromium deadlocks — so one
    failing assertion wedges every WebView test that runs after it.
    """
    global _TEARDOWN_DEPTH

    account_id = platform._account_id or 'default'
    _TEARDOWN_DEPTH += 1
    try:
        platform._view = None
        platform._page = None
        platform._profile = None

        if view is not None:
            with contextlib.suppress(RuntimeError):
                view.close()
            with contextlib.suppress(RuntimeError):
                view.deleteLater()
        if page is not None:
            with contextlib.suppress(RuntimeError):
                page.deleteLater()

        # Destroy the pages before dropping the profile: Qt requires a profile to
        # outlive every page using it.
        _pump_deferred_deletes()
        BaseWebViewPlatform._evict_profile(account_id)
        # The caller's own locals may still reference the profile transitively; a
        # collection pass drops those cycles so the C++ object is destroyed here
        # rather than at some arbitrary point during a later test.
        gc.collect()
        _pump_deferred_deletes()
    finally:
        _TEARDOWN_DEPTH -= 1


def has_cookie_db(data_dir: Path, account_id: str) -> bool:
    """Check whether a cookie database exists for the given account."""
    return (data_dir / 'webprofiles' / account_id / 'Cookies').exists()


def type_into_web_input(page: QWebEnginePage, selector: str, value: str) -> bool:
    """Type into a WebView field using trusted Qt keyboard events.

    Current reactive login forms can reject values assigned by JavaScript. The
    credential value intentionally never crosses the JavaScript boundary.
    """
    focused = run_js(
        page,
        f"""
        (function() {{
            var input = document.querySelector({json.dumps(selector)});
            if (!input) return false;
            input.focus();
            input.select();
            return true;
        }})();
        """,
    )
    if not focused:
        return False

    wait_ms(200)
    target = QApplication.focusWidget()
    if target is None:
        return False
    QTest.keyClick(target, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(target, Qt.Key.Key_Backspace)
    QTest.keyClicks(target, value, delay=5)
    return True


def submit_focused_web_form() -> bool:
    """Submit the focused WebView form using a trusted Return key event."""
    target = QApplication.focusWidget()
    if target is None:
        return False
    QTest.keyClick(target, Qt.Key.Key_Return)
    return True


# ── Per-platform login helpers ───────────────────────────────────────


def login_fetlife(page: QWebEnginePage, email: str, password: str) -> bool:
    """Navigate to the FetLife login page and authenticate.

    Returns True if the session is valid after the attempt (either login
    succeeded or the session was already active).
    """
    ok, final_url = load_page(page, 'https://fetlife.com/login', timeout_ms=15000)
    if not ok:
        return False

    # If /login immediately redirected away, we're already logged in
    if '/login' not in final_url.lower():
        return True

    wait_ms(2000)

    result = run_js(
        page,
        f"""
        (function() {{
            var emailInput = document.querySelector(
                'input[name="user[login]"], input[autocomplete="username"], '
                + 'input[type="email"], input[name="user[email]"], input[name="email"]'
            );
            var passwordInput = document.querySelector(
                'input[type="password"], input[name="user[password]"]'
            );
            if (!emailInput || !passwordInput) return {{found: false}};
            var setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value'
            ).set;
            setter.call(emailInput, {json.dumps(email)});
            emailInput.dispatchEvent(new Event('input', {{bubbles: true}}));
            emailInput.dispatchEvent(new Event('change', {{bubbles: true}}));
            setter.call(passwordInput, {json.dumps(password)});
            passwordInput.dispatchEvent(new Event('input', {{bubbles: true}}));
            passwordInput.dispatchEvent(new Event('change', {{bubbles: true}}));
            var rememberCb = document.querySelector(
                'input[name="user[remember_me]"], input[name="remember_me"], '
                + 'input[id="remember_me"], input[id="user_remember_me"]'
            );
            if (rememberCb && !rememberCb.checked) {{ rememberCb.checked = true; }}
            var submitBtn = document.querySelector(
                'input[type="submit"], button[type="submit"]'
            );
            if (submitBtn) submitBtn.click();
            return {{found: true}};
        }})();
        """,
    )
    if not isinstance(result, dict) or not result.get('found'):
        return False

    # Wait for post-login navigation
    wait_ms(5000)
    return '/login' not in page.url().toString().lower()


def login_fansly(page: QWebEnginePage, email: str, password: str) -> bool:
    """Attempt to log in to Fansly.

    Fansly serves a landing page when logged out. This helper clicks the
    login button to open the modal (if needed) then fills credentials.

    Returns True if the session is valid after the attempt.
    """
    # Wait for Cloudflare challenge + SPA hydration
    wait_ms(5000)

    # Check session state and form availability
    session_check = run_js(
        page,
        """
        (function() {
            var usernameInput = document.querySelector(
                'input[autocomplete="username"], input[type="email"]'
            );
            var loginBtn = document.querySelector(
                'button[data-cy="login"], a[href*="/login"], '
                + '.b-login-btn, [class*="login"][class*="btn"], '
                + 'button[class*="login"]'
            );
            if (!loginBtn) {
                loginBtn = Array.from(document.querySelectorAll('.btn, [role="button"]'))
                    .find(function(el) {
                        return (el.textContent || '').trim().toLowerCase() === 'login';
                    });
            }
            return {
                hasUsernameInput: !!usernameInput,
                hasLoginBtn: !!loginBtn,
                hasLoggedOutShell: !!document.querySelector(
                    '.nav-content-wrapper.not-logged-in'
                )
            };
        })();
        """,
    )
    if not isinstance(session_check, dict):
        return False

    # If neither a login form nor a login button is visible, assume logged in
    if not any(
        session_check.get(key) for key in ('hasUsernameInput', 'hasLoginBtn', 'hasLoggedOutShell')
    ):
        return True

    # Click login button to open modal if form not yet visible
    if session_check.get('hasLoginBtn') and not session_check.get('hasUsernameInput'):
        run_js(
            page,
            """
            var loginBtn = Array.from(
                document.querySelectorAll('.btn, button, a, [role="button"]')
            ).find(function(el) {
                return (el.textContent || '').trim().toLowerCase() === 'login';
            });
            if (loginBtn) loginBtn.click();
            """,
        )
        wait_ms(2000)

    # Fill credentials
    result = run_js(
        page,
        f"""
        (function() {{
            var usernameInput = document.querySelector(
                'input[autocomplete="username"], input[type="email"]'
            );
            var passwordInput = document.querySelector('input[type="password"]');
            var submitBtn = document.querySelector(
                'app-button.auth-submit, .auth-submit, button[type="submit"]'
            );
            if (!usernameInput || !passwordInput || !submitBtn) {{
                return {{found: false}};
            }}
            var setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value'
            ).set;
            setter.call(usernameInput, {json.dumps(email)});
            usernameInput.dispatchEvent(new Event('input', {{bubbles: true}}));
            usernameInput.dispatchEvent(new Event('change', {{bubbles: true}}));
            setter.call(passwordInput, {json.dumps(password)});
            passwordInput.dispatchEvent(new Event('input', {{bubbles: true}}));
            passwordInput.dispatchEvent(new Event('change', {{bubbles: true}}));
            if (submitBtn) submitBtn.click();
            return {{found: true}};
        }})();
        """,
    )
    if not isinstance(result, dict) or not result.get('found'):
        return False

    # Wait for login to complete (Cloudflare + SPA)
    wait_ms(8000)

    final_url = page.url().toString()
    if '/login' in final_url.lower():
        return False

    # Confirm both the login form and public landing-page navigation are gone.
    logged_in = run_js(
        page,
        """
        !document.querySelector(
            'input[type="password"], .nav-content-wrapper.not-logged-in'
        )
        """,
    )
    return bool(logged_in)


def login_snapchat(page: QWebEnginePage, username: str, password: str) -> tuple[bool, str]:
    """Attempt to log in to Snapchat via accounts.snapchat.com.

    Snapchat uses a two-step form: email/username on step 1, password on step 2.
    When a Snapchat session expires, web.snapchat.com redirects to accounts.snapchat.com.

    Returns (success, reason) — reason is an empty string on success or a
    diagnostic message on failure (does not contain credential values).
    """
    ok, final_url = load_page(page, 'https://accounts.snapchat.com/', timeout_ms=20000)
    if not ok:
        return False, f'accounts.snapchat.com load failed: {final_url}'

    wait_ms(3000)

    # Diagnose what's on the page before attempting the form
    diag = run_js(
        page,
        """
        (function() {
            var inputs = Array.from(document.querySelectorAll('input'));
            return {
                url: window.location.href,
                inputCount: inputs.length,
                inputTypes: inputs.map(function(i) {
                    return (i.type || 'text') + (i.name ? '[name=' + i.name + ']' : '');
                }),
                hasSubmit: !!document.querySelector('button[type="submit"]')
            };
        })();
        """,
    )
    diag_summary = (
        f'url={page.url().toString()} inputs={diag}' if isinstance(diag, dict) else f'diag={diag}'
    )

    # Step 1: fill email/username and submit.
    # Snapchat uses input[name="accountIdentifier"]; also try common fallbacks.
    # Note: input[type="text"] may not match elements without an explicit type attribute.
    step1 = run_js(
        page,
        f"""
        (function() {{
            var usernameInput = document.querySelector(
                'input[name="accountIdentifier"], input[name="username"], '
                + 'input[name="email"], input[type="email"], '
                + 'input[type="text"], input:not([type])'
            );
            if (!usernameInput) return {{found: false}};
            usernameInput.focus();
            document.execCommand('insertText', false, {json.dumps(username)});
            usernameInput.dispatchEvent(new Event('input', {{bubbles: true}}));
            var submitBtn = document.querySelector('button[type="submit"]');
            if (submitBtn) submitBtn.click();
            return {{found: true}};
        }})();
        """,
    )
    if not isinstance(step1, dict) or not step1.get('found'):
        return False, f'step1 username field not found — {diag_summary}'

    # Wait for the password step to appear
    wait_ms(3000)

    # Step 2: fill password and submit (second screen of the login flow).
    # Snapchat may use type="text" for the password field (with a show/hide toggle),
    # so also try text inputs that are not the accountIdentifier field.
    step2 = run_js(
        page,
        f"""
        (function() {{
            var passwordInput = document.querySelector(
                'input[type="password"], input[name="password"]'
            );
            if (!passwordInput) {{
                // Fallback: find a text input that is not the accountIdentifier
                var textInputs = Array.from(document.querySelectorAll(
                    'input[type="text"], input:not([type])'
                ));
                passwordInput = textInputs.find(function(i) {{
                    return i.name !== 'accountIdentifier';
                }}) || null;
            }}
            if (!passwordInput) {{
                var allInputs = Array.from(document.querySelectorAll('input'));
                return {{
                    found: false,
                    inputCount: allInputs.length,
                    inputTypes: allInputs.map(function(i) {{
                        return (i.type || '') + (i.name ? '[name=' + i.name + ']' : '')
                            + (i.placeholder ? '[ph=' + i.placeholder.substring(0, 20) + ']' : '');
                    }})
                }};
            }}
            passwordInput.focus();
            document.execCommand('insertText', false, {json.dumps(password)});
            passwordInput.dispatchEvent(new Event('input', {{bubbles: true}}));
            var submitBtn = document.querySelector('button[type="submit"]');
            if (submitBtn) submitBtn.click();
            return {{found: true}};
        }})();
        """,
    )
    if not isinstance(step2, dict) or not step2.get('found'):
        step2_diag = step2 if isinstance(step2, dict) else step2
        return False, f'step2 password field not found — {step2_diag}'

    # Wait for post-login to complete
    wait_ms(10000)
    current = page.url().toString()

    # Accept both legacy and current Snapchat web-app hosts
    if 'web.snapchat.com' in current:
        return True, ''

    # Snapchat now often redirects to www.snapchat.com/web/ (or /v2/welcome)
    # after login.  Navigate to the stable web-app entry point (same strategy
    # as SnapchatPlatform._on_url_changed).
    if 'snapchat.com' in current:
        ok2, nav_url = load_page(page, 'https://web.snapchat.com/', timeout_ms=15000)
        wait_ms(3000)
        current = page.url().toString()
        if 'web.snapchat.com' in current or 'snapchat.com/web' in current:
            return True, ''

    return False, f'post-login URL is not Snapchat web app: {current}'
