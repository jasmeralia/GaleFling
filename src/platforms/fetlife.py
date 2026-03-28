"""FetLife platform implementation using WebView."""

from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import QWebEngineScript
from PyQt6.QtWidgets import QWidget

from src.platforms.base_webview import BaseWebViewPlatform
from src.utils.constants import FETLIFE_SPECS, VIDEO_EXTENSIONS, PlatformSpecs


class FetLifePlatform(BaseWebViewPlatform):
    """FetLife posting via embedded WebView (traditional MPA)."""

    LOGIN_URL = 'https://fetlife.com/login'
    TEXT_COMPOSER_URL = 'https://fetlife.com/posts/new?source=Feed'
    IMAGE_COMPOSER_URL = 'https://fetlife.com/pictures/new?source=Main+Navigation'
    VIDEO_COMPOSER_URL = 'https://fetlife.com/videos/new?source=Main+Navigation'
    COMPOSER_URL = TEXT_COMPOSER_URL
    TEXT_SELECTOR = 'div.tiptap.ProseMirror[contenteditable="true"]'
    SUCCESS_URL_PATTERN = r'fetlife\.com/(?:users/\d+/(?:statuses|posts|pictures|videos)/\d+|(?:posts|pictures|videos)/\d+)'
    SUCCESS_SELECTOR = ''
    COOKIE_DOMAINS = ['fetlife.com']
    AUTH_COOKIE_NAMES = ['_fl_sessionid', 'remember_user_token', '_fl_session_remember_me']
    PREFILL_DELAY_MS = 200  # Traditional server-rendered pages load fast

    def create_webview(self, parent: QWidget | None = None):
        view = super().create_webview(parent)
        self._inject_checkbox_fix()
        return view

    def _inject_checkbox_fix(self) -> None:
        """Inject a script that fixes the 'remember me' checkbox on the FetLife login form.

        FetLife uses a custom checkbox pattern where the actual <input> has opacity:0
        and a styled sibling/parent element provides the visual.  In the embedded WebView
        the visual element absorbs pointer events but clicking it does not trigger the
        Vue reactive state update (Vue re-renders and resets the checked state).

        The fix:
        1. Injects a <style> tag making the native checkbox directly visible.
        2. Intercepts clicks on the now-visible input and uses the HTMLInputElement
           prototype setter (bypasses Vue's instance property override) + dispatches
           'input'/'change' events so Vue's v-model handler fires correctly.
        3. Also intercepts container clicks (when user clicks the label rather than
           the input itself) and applies the same framework-compatible toggle.
        """
        if not self._profile:
            return
        _scripts = self._profile.scripts()
        if _scripts is None or _scripts.find('galefling_fetlife_checkbox_fix'):
            return
        js = r"""
(function () {
    'use strict';

    // Use the prototype setter to bypass Vue/React controlled-input overrides.
    // Setting input.checked directly is overridden by Vue's instance property; using the
    // prototype setter writes to the real DOM property that Vue's v-model watcher reads.
    function triggerFrameworkChange(input) {
        var newVal = !input.checked;
        var desc = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'checked');
        if (desc && desc.set) {
            desc.set.call(input, newVal);
        } else {
            input.checked = newVal;
        }
        // Dispatch both 'input' and 'change' so Vue v-model and React onChange both fire.
        input.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
        input.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
        console.log('[GaleFling] FetLife checkbox change dispatched, checked=' + input.checked);
        // After one microtask tick Vue may re-render and reset the value if it rejected
        // the change.  Log the post-tick state so we can see whether Vue accepted it.
        Promise.resolve().then(function () {
            console.log('[GaleFling] FetLife checkbox post-tick (Vue re-render window), checked=' + input.checked);
        });
    }

    // Ensure the native checkbox receives pointer events without touching its
    // opacity or position — we must NOT make it visible because FetLife renders
    // a custom styled element as the visible checkbox.  Changing opacity/position
    // causes a native browser checkbox to appear alongside the custom one, and
    // the custom one never updates visually (it is the element Vue re-renders).
    if (!document.getElementById('_gl_fl_checkbox_style')) {
        var style = document.createElement('style');
        style.id = '_gl_fl_checkbox_style';
        style.textContent = 'input[type="checkbox"] { pointer-events: auto !important; cursor: pointer !important; }';
        if (document.head) { document.head.appendChild(style); }
    }

    // Attach a submit listener to every form so we can log the actual checkbox states
    // (and the full FormData) just before the POST is sent.  This proves whether the
    // checkbox value is genuinely included in the submission or was just a visual change.
    function setupFormSubmitLogging() {
        document.querySelectorAll('form').forEach(function (form) {
            if (form._gl_submit_hooked) { return; }
            form._gl_submit_hooked = true;
            form.addEventListener('submit', function () {
                form.querySelectorAll('input[type="checkbox"]').forEach(function (cb) {
                    console.log('[GaleFling] FetLife form-submit checkbox: name=' + cb.name
                        + ' checked=' + cb.checked
                        + ' value=' + cb.value
                        + ' will-be-sent=' + cb.checked);
                });
                try {
                    var data = new FormData(form);
                    var parts = [];
                    data.forEach(function (val, key) {
                        parts.push(key + '=' + (/pass|password/i.test(key) ? '***' : String(val)));
                    });
                    console.log('[GaleFling] FetLife form-submit FormData: ' + parts.join(' | '));
                } catch (e) {
                    console.log('[GaleFling] FetLife form-submit FormData-error: ' + e.message);
                }
            }, true);  // capture phase — fires before the browser actually navigates
        });
    }

    function patchCheckboxes() {
        document.querySelectorAll('input[type="checkbox"]').forEach(function (input) {
            var s = window.getComputedStyle(input);
            console.log('[GaleFling] FetLife checkbox name=' + input.name
                + ' id=' + input.id
                + ' checked=' + input.checked
                + ' disabled=' + input.disabled
                + ' display=' + s.display
                + ' visibility=' + s.visibility
                + ' pointerEvents=' + s.pointerEvents
                + ' opacity=' + s.opacity);

            input.disabled = false;
            input.removeAttribute('disabled');
            input.style.pointerEvents = 'auto';
            input.style.opacity = '1';

            // Auto-check the "remember me" checkbox on the login page.
            // FetLife is a server-rendered Rails form — a direct property set is
            // sufficient; no Vue prototype-setter dance needed.
            if ((input.name === 'user[remember_me]' || input.id === 'remember_me')
                    && !input.checked) {
                input.checked = true;
                input.dispatchEvent(new Event('change', { bubbles: true }));
                console.log('[GaleFling] FetLife remember_me auto-checked');
            }

            // Intercept direct clicks on the now-visible input (capture phase so we
            // run before Vue/React's synthetic event handlers).
            if (!input._gl_click_fixed) {
                input._gl_click_fixed = true;
                input.addEventListener('click', function (e) {
                    e.preventDefault();
                    e.stopImmediatePropagation();
                    triggerFrameworkChange(input);
                }, true);
            }

            // Also intercept clicks on the surrounding label/container in case the
            // user clicks outside the input element itself.
            var container = input.closest('label')
                || input.closest('[class*="remember"]')
                || input.closest('[class*="checkbox"]')
                || input.parentElement;
            if (container && !container._gl_fixed) {
                container._gl_fixed = true;
                container.style.pointerEvents = 'auto';
                container.style.cursor = 'pointer';
                container.addEventListener('click', function (e) {
                    if (!e.isTrusted) { return; }
                    if (e.target === input) { return; }  // handled by input's own listener
                    e.preventDefault();
                    e.stopPropagation();
                    triggerFrameworkChange(input);
                }, true);
            }
        });

        setupFormSubmitLogging();
    }

    var mo = new MutationObserver(patchCheckboxes);
    mo.observe(document.documentElement, { childList: true, subtree: true });
    patchCheckboxes();
})();
"""
        script = QWebEngineScript()
        script.setName('galefling_fetlife_checkbox_fix')
        script.setSourceCode(js)
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(True)
        if (s := self._profile.scripts()) is not None:
            s.insert(script)

    def get_platform_name(self) -> str:
        if self._profile_name:
            return f'FetLife ({self._profile_name})'
        return 'FetLife'

    def get_specs(self) -> PlatformSpecs:
        return FETLIFE_SPECS

    def navigate_to_login(self):
        if not self._view:
            return
        page = self._view.page()
        if not page:
            return
        page.loadFinished.connect(self._on_load_finished)
        self._view.load(QUrl(self.LOGIN_URL))

    def get_composer_url(self) -> str:
        if not self._image_path:
            return self.TEXT_COMPOSER_URL
        if self._image_path.suffix.lower() in VIDEO_EXTENSIONS:
            return self.VIDEO_COMPOSER_URL
        return self.IMAGE_COMPOSER_URL
