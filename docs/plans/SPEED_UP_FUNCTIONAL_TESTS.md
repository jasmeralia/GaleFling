# Plan: Speed Up Functional Tests

## Context

Functional tests run serially via `make test-functional-cmd` and take several minutes. The main bottlenecks are:

1. Video fixtures re-encoding via ffmpeg for every test that uses them
2. WebView tests creating a fresh Chromium browser per test, even within the same class
3. Conservative fixed `wait_ms()` sleeps in webview helpers

pytest-xdist parallelism is not viable — QApplication/Chromium state is global and not thread-safe.

---

## Change 1: Session-scoped video fixtures

**File:** `tests/functional/conftest.py`

**Problem:** `sample_video` and `long_video` call ffmpeg to encode a fresh video for every test that requests them. ~9 tests use `sample_video`; each encoding takes 5–10 sec.

**Fix:** Change scope to `"session"` and switch `tmp_path` → `tmp_path_factory`.

```python
@pytest.fixture(scope="session")
def sample_video(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("videos")
    # ... existing encoding logic unchanged ...
```

Apply to both `sample_video` and `long_video`.

**Est. savings:** ~50–90 sec
**Risk:** Low — video files are read-only; no mutation across tests.

---

## Change 2: Class-scoped webview browser fixture

**Files:** `tests/functional/conftest.py` + all `tests/functional/test_webview_*.py`

**Problem:** Every webview test calls `create_webview()` independently, re-initializing Chromium and reloading the page from scratch. Within the same test class this wastes 5–8 sec of browser init + page load per test.

**Fix:** Add a `scope="class"` fixture to `conftest.py`. Each test class exposes an `ACCOUNT_ID` class constant (already present); the fixture creates one browser per class and yields it to all tests in the class.

```python
@pytest.fixture(scope="class")
def webview_page(galefling_data_dir, request):
    account_id = request.cls.ACCOUNT_ID
    view, page, profile = create_webview(galefling_data_dir, account_id)
    yield view, page, profile
    page.deleteLater()
    profile.deleteLater()
```

Tests within each class use `webview_page` instead of calling `create_webview()` directly.

**Est. savings:** ~130 sec (26 webview tests, 5 sec avg overhead each, minus 1 per class)
**Risk:** Medium — must verify tests within each class leave the page in a compatible state for the next test. Add navigation resets where needed.

---

## Change 3: Polling helper to replace conservative fixed waits

**File:** `tests/functional/webview_helpers.py`

**Problem:** Many `wait_ms()` calls are conservative round-number guesses waiting for a DOM condition. Once the condition is met, the remainder of the sleep is wasted.

**Fix:** Add a `wait_for_js()` polling helper and replace applicable fixed sleeps.

```python
def wait_for_js(page, js_expr, timeout_ms=5000, poll_ms=200):
    """Poll js_expr until truthy or timeout. Returns True/False."""
    elapsed = 0
    while elapsed < timeout_ms:
        if run_js(page, js_expr):
            return True
        wait_ms(poll_ms)
        elapsed += poll_ms
    return False
```

**Do not touch** Cloudflare/SPA hydration waits (the 8000 ms Fansly/OnlyFans waits) — these are genuine minimum delays, not polling candidates.

**Est. savings:** 5–20 sec
**Risk:** Low when applied only to waits with a clear DOM condition.

---

## Implementation order

1. Session-scoped video fixtures — isolated, no cross-test risk, quick win
2. Class-scoped webview fixture — bigger saving, requires per-class review
3. Selective wait reduction — polish pass after 1 and 2 are confirmed green

## Verification

Run `make test-functional-cmd` before and after each change. Zero new failures is the acceptance criterion. If a webview test fails after class-scoping, investigate whether a navigation reset is needed between tests in that class.
