"""OnlyFans platform implementation using WebView."""

from PyQt6.QtWebEngineCore import QWebEngineScript
from PyQt6.QtWidgets import QWidget

from src.platforms.base_webview import BaseWebViewPlatform
from src.utils.constants import ONLYFANS_SPECS, PlatformSpecs


class OnlyFansPlatform(BaseWebViewPlatform):
    """OnlyFans posting via embedded WebView (Cloudflare-protected)."""

    COMPOSER_URL = 'https://onlyfans.com/'
    TEXT_SELECTOR = 'div[contenteditable="true"].b-make-post__text'
    SUCCESS_URL_PATTERN = ''  # SPA — URL capture unlikely
    SUCCESS_SELECTOR = ''
    COOKIE_DOMAINS = ['onlyfans.com']
    AUTH_COOKIE_NAMES = ['auth_id']
    PREFILL_DELAY_MS = 1500  # Cloudflare challenge + SPA hydration
    POLL_INTERVAL_MS = 1000
    # OnlyFans serves an inline login form at / without a URL redirect when
    # the session has expired.  These selectors detect that state via DOM.
    SESSION_EXPIRED_SELECTORS = ['.b-loginreg__form', 'input[type="password"]']
    # Vue.js renders the login form client-side; wait for it to mount before
    # running the DOM check.  On cold start Cloudflare's JS challenge also runs
    # asynchronously before the real content appears — 8 s gives it enough time.
    SESSION_EXPIRED_CHECK_DELAY_MS = 8000
    # Give the cookie store extra time to fully initialise from disk on cold start
    # before the first navigation fires.  Without this the request goes out before
    # cookies (including any persisted Cloudflare tokens) are loaded.
    CONNECTION_TEST_STARTUP_DELAY_MS = 2000
    CONNECTION_TEST_TIMEOUT_MS = 25000

    def create_webview(self, parent: QWidget | None = None):
        view = super().create_webview(parent)
        self._inject_2fa_checkbox_fix()
        return view

    def _inject_2fa_checkbox_fix(self) -> None:
        """Inject a script that ensures the 2FA 'remember me' checkbox is interactable.

        OnlyFans renders its 2FA form using Vue.js custom components (.b-chckbox).
        In some embedded WebView contexts the decorator spans and icon elements sit
        on top of the hidden <input>, absorbing clicks before they reach the input.
        The script below uses a MutationObserver to guarantee pointer-events: auto
        on those elements whenever the 2FA form appears.
        """
        if not self._profile:
            return
        # The profile is now shared across login and posting windows.  Guard
        # against re-injecting the script when create_webview is called again.
        _scripts = self._profile.scripts()
        if _scripts is None or _scripts.find('galefling_onlyfans_checkbox_fix'):
            return
        js = r"""
(function () {
    'use strict';

    // Use the prototype setter to bypass Vue's controlled-input override.
    // input.click() is NOT enough: Vue's v-model setter owns the instance property and
    // re-renders revert any direct DOM mutation.  The prototype setter writes through
    // to the raw property that Vue reads, and dispatching input+change fires v-model.
    function triggerFrameworkChange(input) {
        var newVal = !input.checked;
        var desc = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'checked');
        if (desc && desc.set) {
            desc.set.call(input, newVal);
        } else {
            input.checked = newVal;
        }
        input.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
        input.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
        console.log('[GaleFling] OF checkbox change dispatched, checked=' + input.checked);
        // After one microtask tick, Vue may re-render and reset checked if it rejected
        // the event.  Log so we can tell whether the state was accepted.
        Promise.resolve().then(function () {
            console.log('[GaleFling] OF checkbox post-tick (Vue re-render window), checked=' + input.checked);
        });
    }

    // Intercept fetch and XHR calls to auth/2FA endpoints so we can confirm that the
    // remember-me field value actually reaches the server, not just the visual element.
    if (!window._gl_auth_hooked) {
        window._gl_auth_hooked = true;
        var AUTH_URL_RE = /\/(login|two.?factor|2fa|auth|verify)/i;
        var SENSITIVE_KEY_RE = /pass|password|secret/i;

        function sanitiseBody(body) {
            if (!body) { return '(empty)'; }
            try {
                var parsed = typeof body === 'string' ? JSON.parse(body) : body;
                if (parsed && typeof parsed === 'object') {
                    var safe = {};
                    Object.keys(parsed).forEach(function (k) {
                        safe[k] = SENSITIVE_KEY_RE.test(k) ? '***' : parsed[k];
                    });
                    return JSON.stringify(safe);
                }
            } catch (e) { /* not JSON */ }
            return String(body).substring(0, 200);
        }

        var origFetch = window.fetch;
        window.fetch = function (resource, init) {
            var urlStr = typeof resource === 'string' ? resource
                : (resource && resource.url) ? resource.url : String(resource);
            if (AUTH_URL_RE.test(urlStr)) {
                console.log('[GaleFling] OF auth fetch url=' + urlStr
                    + ' body=' + sanitiseBody(init && init.body));
            }
            return origFetch.apply(this, arguments);
        };

        var origXhrOpen = XMLHttpRequest.prototype.open;
        var origXhrSend = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.open = function (method, url) {
            this._gl_url = url;
            return origXhrOpen.apply(this, arguments);
        };
        XMLHttpRequest.prototype.send = function (body) {
            if (this._gl_url && AUTH_URL_RE.test(this._gl_url)) {
                console.log('[GaleFling] OF auth XHR url=' + this._gl_url
                    + ' body=' + sanitiseBody(body));
            }
            return origXhrSend.apply(this, arguments);
        };
    }

    function syncVisual(input) {
        // Sync the visual fill colour after Vue has had a chance to re-render.
        // We read input.checked in a Promise tick so we see Vue's accepted state,
        // not the intermediate value set by triggerFrameworkChange.
        Promise.resolve().then(function () {
            var vis = input.parentElement
                && input.parentElement.querySelector('.b-input-radio__label');
            if (vis) {
                vis.style.backgroundColor = input.checked ? '#00aff0' : '';
                vis.style.borderColor     = input.checked ? '#00aff0' : '';
            }
        });
    }

    function patchCheckboxes() {
        // --- Diagnostic: log every checkbox found so the app log shows the DOM state ---
        document.querySelectorAll('input[type="checkbox"]').forEach(function (input) {
            var s = window.getComputedStyle(input);
            console.log('[GaleFling] OF checkbox found class=' + input.className
                + ' disabled=' + input.disabled
                + ' checked=' + input.checked
                + ' display=' + s.display
                + ' visibility=' + s.visibility
                + ' pointerEvents=' + s.pointerEvents
                + ' opacity=' + s.opacity);
        });

        // --- Fix 1: pointer-events on known OnlyFans custom-checkbox parts ---
        ['.b-chckbox', '.b-chckbox__icon', '.b-chckbox__label', '.b-chckbox__input', 'label']
        .forEach(function (sel) {
            document.querySelectorAll(sel).forEach(function (el) {
                el.style.pointerEvents = 'auto';
                el.style.cursor = 'pointer';
            });
        });

        // --- Fix 2: for every checkbox input, remove disabled and wire up
        //     triggerFrameworkChange so Vue's reactive state is properly updated. ---
        document.querySelectorAll('input[type="checkbox"]').forEach(function (input) {
            input.disabled = false;
            input.removeAttribute('disabled');
            input.style.pointerEvents = 'auto';

            // Sync visual colour on every patch run (Vue re-renders may reset it).
            // Read input.checked now; syncVisual will re-read after the tick.
            syncVisual(input);

            if (input._gl_fixed) { return; }
            input._gl_fixed = true;

            // Direct click on the input itself (capture phase, before Vue's handler).
            input.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopImmediatePropagation();
                triggerFrameworkChange(input);
                syncVisual(input);
            }, true);

            var container = input.closest('label')
                || input.closest('.b-chckbox')
                || input.closest('[class*="chck"]')
                || input.parentElement;
            if (!container) { return; }
            if (!container._gl_fixed) {
                container._gl_fixed = true;
                container.style.pointerEvents = 'auto';
                container.style.cursor = 'pointer';
                container.addEventListener('click', function (e) {
                    if (!e.isTrusted) { return; }
                    if (e.target === input) { return; }  // handled by input's own listener
                    e.preventDefault();
                    e.stopPropagation();
                    triggerFrameworkChange(input);
                    syncVisual(input);
                    console.log('[GaleFling] OF forwarded container click, checked=' + input.checked);
                }, true);
            }
        });

        // --- Fix 3: Cloudflare Turnstile iframes sometimes overlay the checkbox.
        //     Make them pass pointer-events through so clicks reach elements below. ---
        document.querySelectorAll('iframe').forEach(function (f) {
            var src = f.src || '';
            if (src.indexOf('challenges.cloudflare.com') !== -1
                    || src.indexOf('turnstile') !== -1) {
                var s = window.getComputedStyle(f);
                console.log('[GaleFling] CF iframe w=' + s.width + ' h=' + s.height
                    + ' pos=' + s.position + ' z=' + s.zIndex);
                // Only neutralise it if it is absolutely/fixed positioned and
                // could be covering the page (genuine overlay, not inline widget).
                if (s.position === 'fixed' || s.position === 'absolute') {
                    f.style.pointerEvents = 'none';
                }
            }
        });
    }

    var mo = new MutationObserver(patchCheckboxes);
    mo.observe(document.documentElement, { childList: true, subtree: true });
    patchCheckboxes();
})();
"""
        script = QWebEngineScript()
        script.setName('galefling_onlyfans_checkbox_fix')
        script.setSourceCode(js)
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(True)
        if (s := self._profile.scripts()) is not None:
            s.insert(script)

    def get_platform_name(self) -> str:
        if self._profile_name:
            return f'OnlyFans ({self._profile_name})'
        return 'OnlyFans'

    def get_specs(self) -> PlatformSpecs:
        return ONLYFANS_SPECS
