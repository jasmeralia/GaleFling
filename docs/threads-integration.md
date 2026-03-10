# Threads Integration Notes

Threads support exists via WebView platform plumbing, but text prefill/session detection quality depends on verified selectors/cookies.

## Verification Data Needed
Provide both values after manual verification:
- `TEXT_SELECTOR`: CSS selector for Threads composer text input
- `AUTH_COOKIE_NAMES`: cookie names that indicate logged-in session

## Manual Collection Steps
1. Open `https://www.threads.net/` in Chromium-based browser.
2. Log in and open the composer.
3. In DevTools Console, inspect likely composer candidates:
   - `[data-lexical-editor]`
   - `[contenteditable="true"]`
   - `[role="textbox"]`
4. Validate that setting text + input event actually updates composer state.
5. In DevTools Application -> Cookies for Threads, identify auth cookies.
6. Log out and confirm which cookies disappear.

## Expected Follow-Up Changes
- Update selector/cookie constants in `src/platforms/threads.py`.
- Remove placeholder comments once verified.
- Update affected tests in `tests/test_threads.py`.
- Run lint/tests and follow release checklist if a release is requested.
