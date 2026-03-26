"""Shared helpers for WebView functional tests.

Provides QWebEngineView creation, page loading, JS execution, event loop
utilities, and per-platform login helpers used by the per-platform webview
posting test modules.
"""

import contextlib
import json
from pathlib import Path

from PyQt6.QtCore import QEventLoop, QTimer, QUrl
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication


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


def create_webview(data_dir: Path, account_id: str):
    """Create a QWebEngineView with persistent cookies from the given profile.

    Uses the same profile name and storage path as the app so that Chromium loads
    the full persisted browser context (including Cloudflare fingerprint state) from
    prior app sessions.  The app must NOT be running simultaneously — Chromium holds
    an exclusive SQLite WAL lock on the cookie database.
    """
    storage = data_dir / 'webprofiles' / account_id
    # Use the same profile name as the app (_get_profile_storage_path returns
    # get_app_data_dir() / 'webprofiles' / account_id and passes .name to
    # QWebEngineProfile).  A different name creates a fresh Chromium context with
    # no Cloudflare session state, causing re-challenges on protected sites.
    profile = QWebEngineProfile(account_id, None)
    profile.setPersistentStoragePath(str(storage))
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
    )
    page = QWebEnginePage(profile)
    view = QWebEngineView()
    view.setPage(page)
    view.resize(1280, 900)
    view.show()
    return view, page, profile


def has_cookie_db(data_dir: Path, account_id: str) -> bool:
    """Check whether a cookie database exists for the given account."""
    return (data_dir / 'webprofiles' / account_id / 'Cookies').exists()


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
                'input[type="email"], input[name="user[email]"], input[name="email"]'
            );
            var passwordInput = document.querySelector(
                'input[type="password"], input[name="user[password]"]'
            );
            if (!emailInput || !passwordInput) return {{found: false}};
            emailInput.focus();
            document.execCommand('insertText', false, {json.dumps(email)});
            passwordInput.focus();
            document.execCommand('insertText', false, {json.dumps(password)});
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
            var emailInput = document.querySelector('input[type="email"]');
            var loginBtn = document.querySelector(
                'button[data-cy="login"], a[href*="/login"], '
                + '.b-login-btn, [class*="login"][class*="btn"], '
                + 'button[class*="login"]'
            );
            return {
                hasEmailInput: !!emailInput,
                hasLoginBtn: !!loginBtn
            };
        })();
        """,
    )
    if not isinstance(session_check, dict):
        return False

    # If neither a login form nor a login button is visible, assume logged in
    if not session_check.get('hasEmailInput') and not session_check.get('hasLoginBtn'):
        return True

    # Click login button to open modal if form not yet visible
    if session_check.get('hasLoginBtn') and not session_check.get('hasEmailInput'):
        run_js(
            page,
            """
            var loginBtn = document.querySelector(
                'button[data-cy="login"], a[href*="/login"], '
                + '.b-login-btn, [class*="login"][class*="btn"], '
                + 'button[class*="login"]'
            );
            if (loginBtn) loginBtn.click();
            """,
        )
        wait_ms(2000)

    # Fill credentials
    result = run_js(
        page,
        f"""
        (function() {{
            var emailInput = document.querySelector('input[type="email"]');
            var passwordInput = document.querySelector('input[type="password"]');
            if (!emailInput || !passwordInput) return {{found: false}};
            emailInput.focus();
            document.execCommand('insertText', false, {json.dumps(email)});
            passwordInput.focus();
            document.execCommand('insertText', false, {json.dumps(password)});
            var submitBtn = document.querySelector('button[type="submit"]');
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

    # Confirm the login form is gone
    form_gone = run_js(page, '!document.querySelector(\'input[type="password"]\')')
    return bool(form_gone)


def login_onlyfans(
    page: QWebEnginePage,
    email: str,
    password: str,
    totp_secret: str | None = None,
) -> bool:
    """Attempt to log in to OnlyFans via the inline login form.

    OnlyFans renders its login form at / without redirecting. If a TOTP
    secret is provided and a 2FA code prompt appears after credential
    submission, the current TOTP code is generated and submitted.

    Returns True if the session is valid after the attempt.
    """
    # Wait for Vue.js rendering + Cloudflare challenge
    wait_ms(8000)

    # Check whether the login form is present
    form_check = run_js(
        page,
        """
        (function() {
            var form = document.querySelector('.b-loginreg__form, .b-login-wrapper');
            var emailInput = document.querySelector('input[type="email"]');
            var passwordInput = document.querySelector('input[type="password"]');
            return {
                hasForm: !!(form || emailInput),
                hasEmailInput: !!emailInput,
                hasPasswordInput: !!passwordInput
            };
        })();
        """,
    )
    if not isinstance(form_check, dict) or not form_check.get('hasForm'):
        # No login form detected — session appears active
        return True

    # Fill email and password
    result = run_js(
        page,
        f"""
        (function() {{
            var emailInput = document.querySelector(
                '.b-loginreg__form input[type="email"], '
                + 'input[name="email"], input[type="email"]'
            );
            var passwordInput = document.querySelector(
                '.b-loginreg__form input[type="password"], '
                + 'input[name="password"], input[type="password"]'
            );
            if (!emailInput || !passwordInput) return {{found: false}};
            emailInput.focus();
            document.execCommand('insertText', false, {json.dumps(email)});
            emailInput.dispatchEvent(new Event('input', {{bubbles: true}}));
            passwordInput.focus();
            document.execCommand('insertText', false, {json.dumps(password)});
            passwordInput.dispatchEvent(new Event('input', {{bubbles: true}}));
            var submitBtn = document.querySelector(
                '.b-loginreg__form button[type="submit"], '
                + '.b-loginreg__submit, button[type="submit"]'
            );
            if (submitBtn) submitBtn.click();
            return {{found: true}};
        }})();
        """,
    )
    if not isinstance(result, dict) or not result.get('found'):
        return False

    # Wait for credential submission to process
    wait_ms(8000)

    # Check for TOTP / 2FA prompt
    totp_check = run_js(
        page,
        """
        (function() {
            var codeInput = document.querySelector(
                'input[name="code"], input[autocomplete="one-time-code"], '
                + 'input[type="text"][maxlength="6"], '
                + '.b-2fa input[type="text"], .b-2fa input[type="number"], '
                + 'input[placeholder*="code" i], input[placeholder*="2fa" i]'
            );
            return {hasCodeInput: !!codeInput};
        })();
        """,
    )

    if isinstance(totp_check, dict) and totp_check.get('hasCodeInput'):
        if not totp_secret:
            # 2FA is required but no TOTP secret was provided
            return False
        try:
            import pyotp

            code = pyotp.TOTP(totp_secret).now()
        except Exception:
            return False

        totp_result = run_js(
            page,
            f"""
            (function() {{
                var codeInput = document.querySelector(
                    'input[name="code"], input[autocomplete="one-time-code"], '
                    + 'input[type="text"][maxlength="6"], '
                    + '.b-2fa input[type="text"], .b-2fa input[type="number"], '
                    + 'input[placeholder*="code" i], input[placeholder*="2fa" i]'
                );
                if (!codeInput) return {{found: false}};
                codeInput.focus();
                document.execCommand('insertText', false, {json.dumps(code)});
                codeInput.dispatchEvent(new Event('input', {{bubbles: true}}));
                var submitBtn = document.querySelector(
                    '.b-2fa button[type="submit"], button[type="submit"]'
                );
                if (submitBtn) submitBtn.click();
                return {{found: true}};
            }})();
            """,
        )
        if not isinstance(totp_result, dict) or not totp_result.get('found'):
            return False
        wait_ms(5000)

    # Confirm no login form remains
    final_check = run_js(
        page,
        """
        (function() {
            var form = document.querySelector(
                '.b-loginreg__form, .b-login-wrapper, input[type="password"]'
            );
            return {hasLoginForm: !!form};
        })();
        """,
    )
    return not (isinstance(final_check, dict) and final_check.get('hasLoginForm'))


def login_threads(page: QWebEnginePage, username: str, password: str) -> bool:
    """Attempt to log in to Threads via threads.com/login (Meta/Instagram form).

    Returns True if threads.com is the current host after the attempt.
    """
    ok, final_url = load_page(page, 'https://www.threads.com/login', timeout_ms=15000)
    if not ok:
        return False

    # If /login redirected away, we're already logged in
    if 'threads.com/login' not in final_url and 'threads.net/login' not in final_url:
        return 'threads.com' in final_url or 'threads.net' in final_url

    wait_ms(2000)

    result = run_js(
        page,
        f"""
        (function() {{
            var usernameInput = document.querySelector(
                'input[name="username"], input[type="text"], input[type="email"]'
            );
            var passwordInput = document.querySelector('input[name="password"], input[type="password"]');
            if (!usernameInput || !passwordInput) return {{found: false}};
            usernameInput.focus();
            document.execCommand('insertText', false, {json.dumps(username)});
            usernameInput.dispatchEvent(new Event('input', {{bubbles: true}}));
            passwordInput.focus();
            document.execCommand('insertText', false, {json.dumps(password)});
            passwordInput.dispatchEvent(new Event('input', {{bubbles: true}}));
            var submitBtn = document.querySelector('button[type="submit"]');
            if (submitBtn) submitBtn.click();
            return {{found: true}};
        }})();
        """,
    )
    if not isinstance(result, dict) or not result.get('found'):
        return False

    wait_ms(5000)
    current = page.url().toString()
    return ('threads.com' in current or 'threads.net' in current) and '/login' not in current


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
