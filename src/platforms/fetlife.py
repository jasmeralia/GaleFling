"""FetLife platform implementation using WebView."""

import base64
import json
import mimetypes
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import QWebEngineScript
from PyQt6.QtWidgets import QWidget

from src.platforms.base_webview import BaseWebViewPlatform
from src.utils.constants import FETLIFE_SPECS, VIDEO_EXTENSIONS, PlatformSpecs


class FetLifePlatform(BaseWebViewPlatform):
    """FetLife posting via embedded WebView (traditional MPA)."""

    LOGIN_URL = 'https://fetlife.com/login'
    # Text posts are FetLife *statuses*, composed in the inline box on the feed —
    # not writings.  `/posts/new` is the writing composer: its form requires a
    # `post[title]` that GaleFling has no field for, so submitting from there
    # silently fails validation and bounces back to the feed.
    TEXT_COMPOSER_URL = 'https://fetlife.com/home'
    IMAGE_COMPOSER_URL = 'https://fetlife.com/pictures/new?source=Main+Navigation'
    VIDEO_COMPOSER_URL = 'https://fetlife.com/videos/new?source=Main+Navigation'
    COMPOSER_URL = TEXT_COMPOSER_URL
    TEXT_SELECTOR = 'textarea[name="body"]'
    TEXT_SUBMIT_LABEL = 'Say It!'
    # Status permalinks are /<username>/s/<id> (e.g. /Jasmeralia/s/11543410072) — not
    # /users/<id>/statuses/<id>.  Verified against a live status on 2026-08-11; without
    # the username form, URL capture never matches a text post.
    SUCCESS_URL_PATTERN = r'fetlife\.com/(?:users/\d+/(?:statuses|posts|pictures|videos)/\d+|(?:posts|pictures|videos)/\d+|[A-Za-z0-9_.-]+/s/\d+)'
    SUCCESS_SELECTOR = ''
    COOKIE_DOMAINS = ['fetlife.com']
    AUTH_COOKIE_NAMES = ['_fl_sessionid', 'remember_user_token', '_fl_session_remember_me']
    PREFILL_DELAY_MS = 200  # Traditional server-rendered pages load fast

    # Upload composers expose the picker as a hidden <input type="file"> carrying the
    # `accept` list (#picture_attachments / #video_video).  Match on `accept` rather
    # than on `name`: the picture picker has no name attribute, and the *named* field
    # (`picture[attachments][]`) carries no accept list — see _attach_media().
    IMAGE_FILE_SELECTOR = 'input[type="file"][accept*="image"]'
    VIDEO_FILE_SELECTOR = 'input[type="file"][accept*="video"]'

    # Both upload forms require an age/consent certification before they will submit.
    # Matched by exact field name — never by keyword, so no unrelated control (notably
    # `picture[is_avatar]`, which replaces the account avatar) can ever be toggled.
    CONSENT_CHECKBOX_SELECTOR = (
        'input[type="checkbox"][name="picture[is_certified]"], '
        'input[type="checkbox"][name="video[is_certified]"]'
    )

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

    function dismissMaybeLater() {
        var candidates = Array.from(document.querySelectorAll('button, a, [role="button"]'));
        var later = candidates.find(function (el) {
            return (el.textContent || '').trim().toLowerCase() === 'maybe later';
        });
        if (later) {
            later.click();
            console.log('[GaleFling] FetLife recurring prompt dismissed with Maybe Later');
        }
    }

    function patchPage() {
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
        dismissMaybeLater();
    }

    var mo = new MutationObserver(patchPage);
    mo.observe(document.documentElement, { childList: true, subtree: true });
    patchPage();
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

    def _inject_text(self, text: str):
        """Fill the status composer's textarea on the feed.

        Uses the ``HTMLTextAreaElement`` prototype setter so the value lands on the
        real DOM property the page's Stimulus controller reads — the "Say It!" button
        stays disabled otherwise.  Verified against the live composer: the button
        enables for 1..690 characters and disables at 691.
        """
        if not self._view:
            return
        page = self._view.page()
        if not page:
            return
        page.runJavaScript(
            f"""
            (function() {{
                const box = document.querySelector({json.dumps(self.TEXT_SELECTOR)});
                if (!box) return;
                const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLTextAreaElement.prototype, 'value'
                ).set;
                setter.call(box, {json.dumps(text)});
                box.dispatchEvent(new Event('input', {{ bubbles: true }}));
                box.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }})();
            """
        )

    # ── Media upload composers ──────────────────────────────────────

    def get_media_file_selector(self) -> str | None:
        """Return the file-input selector for the staged media, or None for text posts."""
        if not self._image_path:
            return None
        if self._image_path.suffix.lower() in VIDEO_EXTENSIONS:
            return self.VIDEO_FILE_SELECTOR
        return self.IMAGE_FILE_SELECTOR

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

        selector = self.get_media_file_selector() or self.IMAGE_FILE_SELECTOR
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

    def _certify_upload_consent(self, callback: Callable[[dict], None] | None = None) -> None:
        """Tick the age/consent certification required by the upload composers.

        Selects the certification field by exact name, so no other control on the form
        can be toggled — the picture composer also carries ``picture[is_avatar]``, which
        would replace the account avatar.
        """
        if not self._view:
            return
        page = self._view.page()
        if not page:
            return

        js = f"""
        (function() {{
            var boxes = Array.from(
                document.querySelectorAll({json.dumps(self.CONSENT_CHECKBOX_SELECTOR)})
            );
            if (!boxes.length) {{
                return {{certified: false, reason: 'no certification checkbox on this page'}};
            }}
            var changed = [];
            var blocked = [];
            boxes.forEach(function(box) {{
                if (box.disabled) {{ blocked.push(box.name); return; }}
                if (box.checked) {{ return; }}
                box.checked = true;
                box.dispatchEvent(new Event('change', {{bubbles: true}}));
                changed.push(box.name);
            }});
            return {{
                certified: boxes.every(function(box) {{ return box.checked; }}),
                names: boxes.map(function(box) {{ return box.name; }}),
                changed: changed,
                blocked: blocked
            }};
        }})();
        """
        if callback:
            page.runJavaScript(js, callback)
        else:
            page.runJavaScript(js)

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
