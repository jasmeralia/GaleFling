# Functional Testing

Functional tests exercise real platform APIs with real credentials. They are **local-only** — never run in CI — because they require secrets and active test accounts.

## Quick Start (WSL / Linux)

```bash
# 1. Copy the example env and fill in your credentials
cp tests/functional/.env.example tests/functional/.env

# 2. Edit tests/functional/.env with your real values

# 3. Run every non-mutating test, including composer accessibility
make test-functional-non-mutating

# 4. Run every functional test on the live Linux desktop (creates posts)
make test-functional-linux

# 5. Run mutating tests only (explicitly creates or changes real posts)
make test-functional-mutating

# 6. Or use the legacy lenient mode with a virtual display
make test-functional-xvfb PYTHON=.venv/bin/python

# 7. Or via cmd.exe for native Windows process (full GPU/display, best for WebView tests)
#    First-time setup: create the Windows venv (only needed once)
make venv-win
#    Then run tests
make test-functional-cmd
```

`test-functional-non-mutating`, `test-functional-mutating`, and
`test-functional-linux` borrow the active KDE session's display environment from `plasmashell`,
`kwin_wayland`, or `startplasma-wayland`. This supplies the live `DISPLAY`,
`WAYLAND_DISPLAY`, `XAUTHORITY`, `XDG_RUNTIME_DIR`, and D-Bus session values when
the command starts from SSH or tmux. Set `DESKTOP_SESSION_USER` if the graphical
session belongs to a different user.

> **Mutation warning:** `make test-functional-mutating` and
> `make test-functional-linux` can create real posts. Some cleanup is best-effort
> and may require manual deletion. `make test-functional-non-mutating` selects
> composer discovery and unsent input checks, but never selects a test that calls
> a real post-creation endpoint.

> **WSL tip:** `make test-functional-cmd` invokes `cmd.exe` directly so pytest runs as a native Windows process with full GPU and display — same results as running on Windows natively. It uses a separate `.venv-win` directory because a WSL-created venv only has `bin/python`, not `Scripts/python.exe`. Run `make venv-win` once to create it. It uses the Windows Python Launcher (`py.exe`) by default, which ships with official Python installs and is more reliable than `python.exe` (which may redirect to the Microsoft Store). Override with `WIN_PYTHON` if needed, e.g. `make venv-win WIN_PYTHON="py -3.12"`.

## Quick Start (Windows)

### Prerequisites

1. **Python 3.12+** — install from https://python.org or the Microsoft Store
2. **ffmpeg** — required for video processing tests:
   ```powershell
   winget install Gyan.FFmpeg
   ```
   Or download from https://ffmpeg.org/download.html and add to `PATH`.
3. **Project dependencies**:
   ```powershell
   cd path\to\GaleFling
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt -r requirements-dev.txt
   ```

### Running Tests on Windows

Windows has full GPU access, so WebView tests that need WebGL (Snapchat) work natively.

```powershell
# All functional tests in strict mode
$env:GALEFLING_STRICT_FUNCTIONAL = "1"
.venv\Scripts\python -m pytest tests\functional\ -m functional -v --no-header

# All non-mutating tests, including composer accessibility
.venv\Scripts\python -m pytest tests\functional\ -m "functional and non_mutating" -v

# Mutating tests only (creates, updates, or deletes real posts)
.venv\Scripts\python -m pytest tests\functional\ -m "functional and mutating" -v

# Specific platform only
.venv\Scripts\python -m pytest tests\functional\test_webview_snapchat.py -m functional -v

# Media processing only (no credentials needed)
.venv\Scripts\python -m pytest tests\functional\test_media_processing.py -m functional -v
```

> **Note:** `make` is not required. The Makefile targets are convenience wrappers around `pytest` commands shown above. If you want `make` on Windows, install via `winget install GnuWin32.Make` or `choco install make`.

### Windows .env Path

On Windows, set the native path for `GALEFLING_DATA_DIR`:

```env
GALEFLING_DATA_DIR=C:\Users\you\AppData\Roaming\GaleFling
```

In WSL, use the Plan9 mount path instead:

```env
GALEFLING_DATA_DIR=/mnt/c/Users/you/AppData/Roaming/GaleFling
```

Easiest: export via **Settings > Advanced > Export Test Config** in GaleFling.

## Functional Test Groups

Every functional test belongs to exactly one side-effect group:

- `non_mutating` includes media processing, local validation, authentication,
  persisted-session checks, composer discovery, and unsent text injection. These
  tests never call a real post-creation endpoint.
- `mutating` includes every test that calls a platform post-creation endpoint,
  including rejection tests whose requests are expected to fail. These tests may
  create, update, or delete real posts.

Collection fails if a functional test has neither marker or both markers. Run
`make test-functional-non-mutating` for the side-effect-free suite. Tests that can
change platform state require an explicit `make test-functional-mutating` or
all-functional invocation.

## Display Modes and Platform Capabilities

WebView tests behave differently depending on the display environment:

| Environment | API tests | Media tests | FetLife | Fansly | OnlyFans | Threads | Snapchat |
|---|---|---|---|---|---|---|---|
| **Windows (native)** | All pass | All pass | Full | Text inject | Auth + composer | Auth + text | Full (WebGL) |
| **WSL → cmd.exe** | All pass | All pass | Full | Text inject | Auth + composer | Auth + text | Full (WebGL) |
| **WSLg (DISPLAY=:0)** | All pass | All pass | Full | Text inject | Auth only | Auth + text | JS fails (no WebGL) |
| **Offscreen (no display)** | All pass | All pass | Full | Text inject | Auth only | Auth + text | JS fails |
| **Xvfb (xvfb-run)** | All pass | All pass | Full | Text inject | Auth only | Auth + text | Depends on Mesa GL |

**Windows is the recommended environment for full test coverage** because it has native GPU access required by Snapchat's WebGL-dependent web app.

The conftest detects whether a display is available and only falls back to offscreen mode when one isn't. You can override this by setting `QT_QPA_PLATFORM=offscreen` explicitly.

### Strict and lenient outcomes

`GALEFLING_STRICT_FUNCTIONAL=1` makes environment and application defects fail the
run instead of being reported as skips. This includes failed logins, missing DOM
selectors, unavailable JavaScript, missing session databases, and WebEngine renderer
terminations. Failure messages retain the original diagnostic, including the selector
or platform state where available.

Missing platform credentials remain legitimate skips in every mode. An absent or
invalid `GALEFLING_DATA_DIR` also skips tests that require an existing GaleFling
profile, because those tests cannot start without that external configuration.

`make test-functional`, `make test-functional-non-mutating`,
`make test-functional-mutating`, and `make test-functional-linux` enable strict
mode. The three Linux desktop targets borrow the complete live graphical-session
environment so QtWebEngine can use the desktop's hardware GPU. The compatibility
targets `test-functional-xvfb` and `test-functional-cmd` keep their previous
lenient behavior; set
`GALEFLING_STRICT_FUNCTIONAL=1` explicitly when invoking pytest directly.

## Configuration

### Credential File

All credentials are read from `tests/functional/.env` (gitignored). Copy the template and fill in the platforms you want to test:

```bash
cp tests/functional/.env.example tests/functional/.env
```

### Required Variables per Platform

#### Bluesky (easiest — start here)
```env
BLUESKY_IDENTIFIER=your-handle.bsky.social
BLUESKY_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
```
- Create a free test account at https://bsky.app
- Generate an app password at **Settings > App Passwords**

#### Twitter
```env
TWITTER_API_KEY=your-api-key
TWITTER_API_SECRET=your-api-secret
TWITTER_ACCESS_TOKEN=your-access-token
TWITTER_ACCESS_TOKEN_SECRET=your-access-token-secret
```
- Requires a Twitter Developer App with OAuth 1.0a User Context
- The app must have **Read and Write** permissions
- Generate keys at https://developer.twitter.com/en/portal/dashboard

#### Instagram
```env
INSTAGRAM_ACCESS_TOKEN=your-long-lived-token
INSTAGRAM_BUSINESS_ACCOUNT_ID=your-ig-user-id
INSTAGRAM_PAGE_ID=your-facebook-page-id
```
- Requires a Business or Creator Instagram account linked to a Facebook Page
- The token needs `instagram_basic`, `instagram_content_publish`, and `pages_read_engagement` permissions
- Use the Graph API Explorer to generate a long-lived token

#### WebView Platforms — Common

All WebView platform tests also require:
```env
GALEFLING_DATA_DIR=C:\Users\you\AppData\Roaming\GaleFling
```
Set to the GaleFling application data directory containing `webprofiles/`. This is where the persistent browser profile (including cookies) is stored. Export via **Settings > Advanced > Export Test Config** or set manually.

#### OnlyFans (WebView)
```env
ONLYFANS_EMAIL=your-email@example.com
ONLYFANS_PASSWORD=your-password
ONLYFANS_TOTP_SECRET=BASE32SECRETHERE
```
- `ONLYFANS_TOTP_SECRET` is the base32-encoded seed from your authenticator app
  (the same secret you scanned as a QR code when setting up 2FA). It is only
  required if the account has two-factor authentication enabled.
- If the session cookie in `GALEFLING_DATA_DIR` is still valid, the login flow
  is skipped and the test proceeds immediately.
- If the cookie has expired, the test logs in automatically using the credentials
  above, including submitting a fresh TOTP code if a 2FA prompt appears.

#### Fansly (WebView)
```env
FANSLY_EMAIL=your-email@example.com
FANSLY_PASSWORD=your-password
```
- If the session cookie is still valid, the login flow is skipped.
- If the cookie has expired, the test logs in automatically.

#### FetLife (WebView)
```env
FETLIFE_EMAIL=your-email@example.com
FETLIFE_PASSWORD=your-password
```
- If the session cookie is still valid, the login flow is skipped.
- If the cookie has expired, the test logs in via `https://fetlife.com/login`
  automatically.

#### Threads (WebView)
```env
THREADS_USERNAME=your-instagram-username-or-email
THREADS_PASSWORD=your-password
```
- Threads uses Instagram/Meta credentials for login via `threads.net/login`.
- If the session cookie is still valid, the login flow is skipped.
- If the cookie has expired, the test logs in automatically.
- **Note:** The Threads platform is not yet finalized. Some selectors are marked
  `THREADS_PLACEHOLDER` in `ThreadsPlatform` and have not been verified against the
  live site. Tests that rely on those selectors will skip with a diagnostic message
  rather than fail, and both the platform class and the tests should be updated together
  once the selectors are confirmed.

#### Snapchat (WebView)
```env
SNAPCHAT_USERNAME=your-username-or-email
SNAPCHAT_PASSWORD=your-password
```
- If the session cookie is still valid, the login flow is skipped.
- If the cookie has expired, the test logs in automatically via `accounts.snapchat.com`.

### Skipping Unconfigured Platforms

Tests automatically **skip** when their credentials are absent — you only need to configure the platforms you want to test. Running with no `.env` at all will skip all platform API and WebView tests (media processing tests still run).

## Test Structure

```
tests/functional/
├── conftest.py                  # Credential loading, skip-if-missing fixtures, media fixtures
├── webview_helpers.py           # Shared QWebEngineView helpers and per-platform login flows
├── .env.example                 # Template showing required vars (committed)
├── .env                         # Actual credentials (gitignored)
├── test_bluesky_post.py         # Bluesky: auth, text, image, video, char limit
├── test_twitter_post.py         # Twitter: auth, text, image, video, char limit
├── test_instagram_post.py       # Instagram: auth, image post (3-step workflow)
├── test_media_processing.py     # Image/video processing (no credentials needed)
├── test_webview_sessions.py     # WebView: session cookie validation (all 4 platforms)
├── test_webview_fetlife.py      # FetLife: text/picture/video composer tests
├── test_webview_fansly.py       # Fansly: text injection tests
├── test_webview_onlyfans.py     # OnlyFans: auth + composer click expansion
├── test_webview_threads.py      # Threads: auth + text injection (selectors TBD)
└── test_webview_snapchat.py     # Snapchat: page load + text injection (needs WebGL)
```

### Session-or-Login Flow

WebView posting tests (FetLife, Fansly, OnlyFans) use a **session-or-login** approach:

1. A persistent browser profile is loaded from `GALEFLING_DATA_DIR/webprofiles/<account_id>/`.
2. The test navigates to the platform URL.
3. If the session cookie is still valid, the test proceeds immediately.
4. If the session has expired (login form detected or redirect to login URL), the test
   performs an automated login using the credentials from `.env`.
5. If login fails (wrong credentials, unexpected form structure, etc.), the test
   **skips** with a diagnostic message rather than failing.

After a successful automated login, the new session cookies are persisted to the
`webprofiles/` directory — so subsequent runs will skip the login step again until
the next expiry.

### Test Ordering

Each platform test module starts with a connection/page-load test that validates
authentication before any posting tests run. If that test fails, the credentials or
session state need attention — no need to debug post failures.

### Post Cleanup

Every test that creates a post **deletes it in the same test** to avoid polluting
test accounts. Tests use UUID tags in post text to avoid duplicate-post rejections.
FetLife text posts redirect to the feed after submission rather than to the
individual post, so manual cleanup may be needed.

## What's Tested

### Per-Platform API Tests

| Test case                  | Bluesky | Twitter | Instagram |
|----------------------------|---------|---------|-----------|
| Authentication             | x       | x       | x         |
| Profile fetch              | x       | x       | -         |
| Text-only post + delete    | x       | x       | -         |
| Post with URL facets       | x       | -       | -         |
| Single image post          | x       | x       | x         |
| Multiple images post       | x       | x       | -         |
| Video post                 | x       | x       | -         |
| Character limit rejection  | x       | x       | -         |

### WebView Platform Session Tests

| Test case                  | Snapchat | OnlyFans | Fansly | FetLife | Threads |
|----------------------------|----------|----------|--------|---------|---------|
| Cookie database exists     | x        | x        | x      | x       | x       |
| has_valid_session()        | x        | x        | x      | x       | x       |
| Platform specs consistency | x        | x        | x      | x       | x       |

### WebView Platform Posting Tests

| Test case                    | FetLife | Fansly | OnlyFans | Threads | Snapchat |
|------------------------------|---------|--------|----------|---------|----------|
| Composer page loads          | x       | x      | x        | x       | x        |
| Composer click expansion     | -       | -      | x        | -       | -        |
| Text injection               | x       | x      | x        | x *     | x        |
| Text post submit             | x       | -      | -        | -       | -        |
| Picture composer elements    | x       | -      | -        | -       | -        |
| Video composer elements      | x       | -      | -        | -       | -        |

\* Threads text injection uses an unverified selector (`THREADS_PLACEHOLDER`). The test skips gracefully if the selector doesn't match the live site.

### Media Processing (No Credentials)

| Test case                           | Platforms covered             |
|-------------------------------------|-------------------------------|
| Oversized image resize              | Twitter, Bluesky, Instagram   |
| Small image not upscaled            | Twitter, Bluesky, Instagram   |
| WebP → JPEG/PNG conversion          | Bluesky                       |
| RGBA transparency handling          | Twitter                       |
| File size compression (1MB limit)   | Bluesky                       |
| Animated GIF resize + frame preserve| Bluesky                       |
| Image validation (missing/corrupt)  | Twitter                       |
| ffmpeg availability                 | (all)                         |
| Video metadata probing              | (all)                         |
| Video validation (missing file)     | Twitter                       |
| Video processing pipeline           | Twitter, Bluesky, Instagram   |
| Duration preservation               | Twitter                       |
| Snapchat image→video (crop)         | Snapchat                      |
| Snapchat image→video (rotate)       | Snapchat                      |
| Snapchat slideshow (crop)           | Snapchat                      |
| Snapchat slideshow (rotate)         | Snapchat                      |

## CI Integration

Functional tests are **excluded from CI** via the `functional` pytest marker:

- `pyproject.toml` defines the marker
- `make test-ci` runs the marker-excluded suite with coverage, JUnit, and coverage XML reports
- the release workflow uses `make test-ci`
- `make test-cov` is a deprecated alias for `make test-ci` for one release
- `make test-functional` is the strict dedicated target for local runs
- `make test-functional-non-mutating` selects every side-effect-free functional test
- `make test-functional-mutating` explicitly selects tests that can change platform state

## Troubleshooting

### QWebEngineView crashes with "Fatal Python error: Aborted"
The conftest.py creates a module-level QApplication to prevent garbage collection, and sets `QTWEBENGINE_CHROMIUM_FLAGS=--no-sandbox --disable-gpu --disable-software-rasterizer` when in offscreen mode. If you still see crashes, try running with a real display (`DISPLAY=:0` on WSL) or on native Windows.

### WebView session tests fail with "No X cookie database found"
In strict mode, this means the platform's cookie database doesn't exist in `GALEFLING_DATA_DIR/webprofiles/<platform>_1/Cookies`. The posting tests for all four WebView platforms will create the session automatically using the credentials in `.env`. Lenient runs still report this condition as a skip.

### OnlyFans / Fansly / FetLife login fails during test
Check that the credentials in `.env` are correct. For OnlyFans with 2FA, verify that `ONLYFANS_TOTP_SECRET` is set to the raw base32 seed (not a time-based code). If the account is locked or requires email verification, complete that step manually in the GaleFling app first.

### FetLife post not auto-deleted
FetLife redirects to `/posts` after submission instead of the individual post page. Check your FetLife feed for posts containing "GaleFling functional test" and delete them manually.

### OnlyFans composer not found
The test attempts to click the compose area to expand the editor. If it still can't find the composer, the SPA may need full browser rendering. Run on Windows for the best chance of success.

### Snapchat JS execution fails
Snapchat's web app requires WebGL with a real GPU. This works on native Windows but not in WSL (even with WSLg) or offscreen mode. Strict runs fail with a diagnostic message; lenient runs skip.

### Tests pass on Windows but fail in WSL
WebView platforms that depend on GPU rendering (Snapchat, some OnlyFans features) require native Windows. API-based platforms (Twitter, Bluesky, Instagram) and FetLife/Fansly work in both environments.
