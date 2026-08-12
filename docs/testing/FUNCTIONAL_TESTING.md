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

Windows has full GPU access for WebView tests. Snapchat WebView tests are excluded
from routine runs because the platform is disabled in the product.

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

### The GaleFling data directory

Leave `GALEFLING_DATA_DIR` **unset**. The suite resolves the running platform's own
location automatically — `~/.config/GaleFling` on Linux, `%APPDATA%\GaleFling` on
Windows.

Set it only to point at a non-default profile location. Be aware that the Windows test
VM reads this same `.env` over the VirtIO-FS share, so an absolute path that is valid
on one platform is wrong on the other, and the WebView tests there will skip with
`GALEFLING_DATA_DIR does not exist`.

The Linux and Windows profiles are separate: logging in on one does not authenticate
the other, and a Chromium profile copied between them will not decrypt, because cookie
values are encrypted per-platform.

## Quick Start (Windows VM, from Linux)

Runs the suite on real Windows without leaving the Linux shell, using the libvirt VM
harness in `tools/windows-vm/`. See [`tools/windows-vm/README.md`](../../tools/windows-vm/README.md)
for creating the VM; this section covers running tests once it exists.

```bash
make test-functional-win-vm                    # whole functional suite in the guest
make test-functional-win-vm PYTEST_ARGS="tests/functional/test_media_processing.py"
make test-functional-win-vm PYTEST_ARGS="-k composer -x"
make test-functional-win-vm-clean              # revert to the baseline snapshot first
```

The target starts the VM if it is not already running, executes pytest in the guest over
SSH, and exits with the guest's own exit code — a failing test in the guest fails the
make target on the host.

**Start with `test_media_processing.py`.** It needs no credentials, so it separates "the
VM dispatch works" from "the credentials work" when something goes wrong.

### How it works

The guest runs the tests directly from the host working tree, shared as `Z:` over
VirtIO-FS. There is no copy or sync step, so the guest always tests the checkout you are
editing — including uncommitted changes. Tests run with `GALEFLING_STRICT_FUNCTIONAL=1`
so environment gaps are reported as failures rather than skips; a silently skipped suite
in a VM nobody is watching looks exactly like a passing one.

Credentials are read from `tests/functional/.env` over that same share at run time, so
they stay on the host. **Never copy `.env` into the guest filesystem** — a snapshot taken
afterwards would carry the credentials, and snapshots are long-lived and reverted to
repeatedly.

### Snapshot reverts

`make test-functional-win-vm-clean` reverts to the baseline snapshot (`clean-loggedout`
by default) before running, so every run starts from identical state. This is what makes
persistence testing meaningful, but it **discards all newer guest changes**, including
any platform session you logged in by hand. The plain target does not revert.

### Troubleshooting

| Problem | Cause |
|---|---|
| `Missing VM configuration` | No `vm.env`. Copy `vm.env.example` and set local paths. |
| `Could not determine the IP address` | The guest booted but has no DHCP lease yet, or the guest agent is not running. |
| `Z:` not found in the guest | The VirtioFS service is not running. Check `WinFsp` and `VirtioFsSvc` in the guest. |
| Tests fail only in the guest | Expected for genuine Windows-specific defects — this is the point of the VM. Confirm on Linux with `make test-functional-linux` before assuming a dispatch problem. |

## Functional Test Groups

Every functional test belongs to exactly one side-effect group:

- `non_mutating` includes media processing, local validation, authentication,
  persisted-session checks, composer discovery, and unsent text injection. These
  tests never call a real post-creation endpoint.
- `mutating` includes every test that calls a platform post-creation endpoint,
  including rejection tests whose requests are expected to fail. These tests may
  create, update, or delete real posts.
- `disabled_platform` marks functional tests for platforms disabled in the product
  (currently Snapchat). These are **excluded** from `make test-functional*` and VM
  runs by default. Pass `--run-disabled-platforms` to include them locally.

Collection fails if a functional test has neither marker or both markers. Run
`make test-functional-non-mutating` for the side-effect-free suite. Tests that can
change platform state require an explicit `make test-functional-mutating` or
all-functional invocation.

## Display Modes and Platform Capabilities

WebView tests behave differently depending on the display environment:

| Environment | API tests | Media tests | FetLife | Fansly | OnlyFans |
|---|---|---|---|---|---|
| **Windows (native)** | All pass | All pass | Full | Text inject | Auth + composer |
| **WSL → cmd.exe** | All pass | All pass | Full | Text inject | Auth + composer |
| **WSLg (DISPLAY=:0)** | All pass | All pass | Full | Text inject | Auth only |
| **Offscreen (no display)** | All pass | All pass | Full | Text inject | Auth only |
| **Xvfb (xvfb-run)** | All pass | All pass | Full | Text inject | Auth only |

Snapchat WebView functional tests are disabled in the product and excluded from
routine runs (`disabled_platform`). Media-processing tests for Snapchat
image→video transforms still run — they exercise pipeline code, not the live app.

The conftest detects whether a display is available and only falls back to offscreen mode when one isn't. You can override this by setting `QT_QPA_PLATFORM=offscreen` explicitly.

### Strict and lenient outcomes

`GALEFLING_STRICT_FUNCTIONAL=1` makes environment and application defects fail the
run instead of being reported as skips. This includes failed logins, missing DOM
selectors, unavailable JavaScript, expired WebView sessions (cookie DB present but
`has_valid_session()` false), and WebEngine renderer terminations. Failure messages
retain the original diagnostic, including the selector or platform state where
available.

Missing platform credentials remain legitimate skips in every mode. So does a missing
WebView profile: if `webprofiles/<account_id>/Cookies` does not exist (because the
platform was never logged in, session cookies were reset in Settings, or the profile
folder was removed), session-validation tests skip rather than fail. An explicitly
configured `GALEFLING_DATA_DIR` that does not exist also skips tests requiring a
GaleFling profile, because those tests cannot start without that external
configuration. When it is unset the platform default is used instead of skipping.

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

#### Instagram (Graph API — graph.instagram.com)
```env
INSTAGRAM_ACCESS_TOKEN=your-long-lived-token
INSTAGRAM_BUSINESS_ACCOUNT_ID=your-ig-user-id
```
- Requires a Business or Creator Instagram account connected via the Instagram Login API
- Media posts additionally require the shared Meta AWS staging variables below

#### Meta Threads (Graph API — graph.threads.net)
```env
META_THREADS_ACCESS_TOKEN=your-long-lived-token
META_THREADS_USER_ID=your-threads-user-id
```
- Long-lived token from the GaleFling Threads OAuth connect flow (see [THREADS.md](../platforms/THREADS.md))
- Media posts additionally require the shared Meta AWS staging variables below

#### Meta Facebook Page (Graph API — graph.facebook.com)
```env
META_FACEBOOK_PAGE_ACCESS_TOKEN=your-page-access-token
META_FACEBOOK_PAGE_ID=your-page-id
```
- Long-lived Page access token from the GaleFling Facebook Page OAuth connect flow (see [FACEBOOK.md](../platforms/FACEBOOK.md))

#### Meta AWS S3 media staging (Instagram and Threads media posts)
```env
META_AWS_ACCESS_KEY_ID=your-key-id
META_AWS_SECRET_ACCESS_KEY=your-secret-key
META_AWS_REGION=us-west-2
META_AWS_BUCKET=your-staging-bucket
```
- Required for Instagram and Threads image, video, and carousel functional tests
- The bucket must expose public-read object URLs so Meta can fetch staged media
- See `infrastructure/galefling-media-staging.yaml` for the reference CloudFormation stack

#### WebView Platforms — Common

All WebView platform tests read persistent browser profiles from the GaleFling
application data directory (the one containing `webprofiles/`). This resolves
automatically per platform, so no configuration is needed. Override it with
`GALEFLING_DATA_DIR` only to point at a non-default location — see
[The GaleFling data directory](#the-galefling-data-directory).

#### OnlyFans (WebView)
```env
# Optional — import before composer tests when webprofiles/onlyfans_1/ is empty or expired
ONLYFANS_AUTH_JSON=/path/to/auth.json
```
- OnlyFans login inside the embedded browser is blocked by reCAPTCHA. Use a
  persisted GaleFling profile (`webprofiles/onlyfans_1/`) or export `auth.json`
  from a normal browser and import it in Settings. See
  [OnlyFans Session Import](../platforms/ONLYFANS_SESSION_IMPORT.md).
- When `ONLYFANS_AUTH_JSON` is set, composer tests import that file before
  running if `has_valid_session()` is false.
- Session validation tests in `test_webview_sessions.py` only need a valid
  profile under `GALEFLING_DATA_DIR`; they do not read `ONLYFANS_AUTH_JSON`.

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

Functional test modules follow a consistent naming scheme:

| Pattern | Platforms | Example |
|---------|-----------|---------|
| `test_{platform}_post.py` | Non-Meta API | `test_bluesky_post.py`, `test_twitter_post.py` |
| `test_meta_{platform}_post.py` | Meta Graph API | `test_meta_instagram_post.py`, `test_meta_threads_post.py`, `test_meta_facebook_page_post.py` |
| `test_webview_{platform}.py` | WebView | `test_webview_onlyfans.py`, `test_webview_fansly.py` |
| `test_media_processing.py` | Cross-platform media pipeline | (no credentials) |
| `test_webview_sessions.py` | WebView session cookies | all four active WebView platforms |

```
tests/functional/
├── conftest.py                      # Credential loading, skip-if-missing fixtures, media fixtures
├── webview_helpers.py               # Shared QWebEngineView helpers and per-platform login flows
├── .env.example                     # Template showing required vars (committed)
├── .env                             # Actual credentials (gitignored)
├── test_bluesky_post.py             # Bluesky API: auth, text/facet, image/video, char limit
├── test_twitter_post.py             # Twitter API: auth, text, image/video, char limit
├── test_meta_instagram_post.py      # Instagram Graph API: auth, validation, image/video/carousel
├── test_meta_threads_post.py        # Threads Graph API: auth, text/image/video/carousel posts
├── test_meta_facebook_page_post.py  # Facebook Page API: auth, text/photo/video posts
├── test_media_processing.py         # Image/video processing (no credentials needed)
├── test_webview_sessions.py         # WebView: session cookie validation (Snapchat, OnlyFans, Fansly, FetLife)
├── test_webview_fetlife.py          # FetLife: text/picture/video composer tests
├── test_webview_fansly.py           # Fansly: text injection tests
├── test_webview_onlyfans.py         # OnlyFans: session + composer click expansion
└── test_webview_snapchat.py         # Snapchat WebView (disabled_platform — excluded by default)
```

Snapchat WebView tests are tagged `disabled_platform` and excluded from `make
test-functional*`. Pass `--run-disabled-platforms` to opt in. Media-processing
Snapchat transforms in `test_media_processing.py` still run.

### Running one platform at a time

```bash
# Meta API example — mutating tests only, stop on first failure
GALEFLING_STRICT_FUNCTIONAL=1 scripts/run-with-desktop-session.sh \
  .venv/bin/python -m pytest tests/functional/test_meta_threads_post.py \
  -m "functional and mutating" -v -x

# WebView example — non-mutating only
GALEFLING_STRICT_FUNCTIONAL=1 scripts/run-with-desktop-session.sh \
  .venv/bin/python -m pytest tests/functional/test_webview_fansly.py -v
```

Every mutating post embeds an 8-character hex UUID tag in the caption/text (via `mutating_post_text()` / `mutating_post_tag()` in `conftest.py`). Search the account for that tag if cleanup fails — pytest output includes the tag when a test prints it.

### Session-or-Login Flow

WebView posting tests use a **session-first** approach:

1. A persistent browser profile is loaded from `GALEFLING_DATA_DIR/webprofiles/<account_id>/`.
2. The test navigates to the platform URL.
3. If the session cookie is still valid, the test proceeds immediately.
4. If the session has expired (login form detected or redirect to login URL), the test
   **skips or fails** with guidance to refresh the session.

**Fansly and FetLife** still support automated login from `.env` credentials when the
session expires. **OnlyFans does not** — reCAPTCHA blocks embedded-browser login, so
refresh the session via Settings import or `ONLYFANS_AUTH_JSON` instead.

After a successful automated login (Fansly/FetLife), new session cookies are persisted
to the `webprofiles/` directory — so subsequent runs will skip the login step again until
the next expiry.

### Test Ordering

Each platform test module starts with a connection/page-load test that validates
authentication before any posting tests run. If that test fails, the credentials or
session state need attention — no need to debug post failures.

### Post Cleanup

Tests that create a post attempt to delete it in the same test. Cleanup is **best-effort** — a failed assertion or API error before the delete step can leave a live post behind.

| Platform | Auto-delete? | Notes |
|----------|--------------|-------|
| Bluesky | Yes | API `delete_post` |
| Twitter | Yes | API `delete_tweet` |
| Instagram | Yes | Graph API media delete |
| Threads | Yes | Graph API delete (text, image, video, carousel) |
| Facebook Page | Yes | Graph API delete (text, photo, multi-photo, video) |
| FetLife (text) | Best-effort | UI delete when post URL is captured; feed redirect needs manual cleanup |
| FetLife (picture/video) | **No mutating tests** | Attach is covered non-mutatingly; Upload is never clicked — see warning below |

Tests use UUID tags in post text to avoid duplicate-post rejections and to make manual cleanup easy.

**If auto-delete fails** (assertion before cleanup, API error, or token lacks delete permission), search the platform for `GaleFling` plus the UUID tag in the post text and remove manually.

## What's Tested

### Per-Platform API Tests

| Test case                  | Bluesky | Twitter | Instagram | Threads | Facebook Page |
|----------------------------|---------|---------|-----------|---------|---------------|
| Authentication             | x       | x       | x         | x       | x             |
| Profile fetch              | x       | x       | x         | x       | x             |
| Bad credentials rejected   | x       | x       | x         | x       | x             |
| Text-only post + delete    | x       | x       | -         | x       | x             |
| Post with URL facets       | x       | -       | -         | -       | -             |
| Single image post          | x       | x       | x         | x       | x             |
| PNG image post             | x       | x       | x         | x       | x             |
| Multiple images post       | x       | x       | x         | x       | x             |
| Mixed image+video carousel | -       | -       | x         | x       | -             |
| Video post (platform code) | x       | x       | x         | x       | x             |
| Character limit rejection  | x       | x       | x         | x       | x             |
| Unsupported format (WEBP)  | -       | -       | x         | x       | x             |
| Text-only post rejected    | -       | -       | x         | -       | -             |

Bluesky and Twitter mutating tests route through `BlueskyPlatform` / `TwitterPlatform`
(the same adapters the app uses). Instagram and Threads media tests skip when Meta AWS
staging credentials are absent.
Facebook Page photo and video tests upload directly and do not require AWS staging.

### Coverage Gaps (functional suite)

The tables above show what **is** tested. The gaps below map missing functional coverage to platform capabilities documented in [PLATFORM_SPECS.md](../platforms/PLATFORM_SPECS.md). Unit tests in `tests/test_*_platform.py` and `tests/test_image_processor_platforms.py` cover much of the adapter and media-prep logic without live credentials.

#### API platforms

| Gap | Bluesky | Twitter | Instagram | Threads | Facebook Page |
|-----|---------|---------|-----------|---------|---------------|
| Second account slot (`*_2` / `*_alt`) | — | — | — | — | — |
| GIF / animated image post | — | — | — | — | — |
| Native WEBP image post | — | — | — | — | — |
| Post cleanup after mutating test | ✓ | ✓ | ✓ | ✓ | ✓ |
| Media processing functional tests | partial | partial | partial | — | — |
| Token refresh / expiry warning path | — | — | — | — | — |
| Rate-limit headroom check | — | — | — | — | — |

#### WebView platforms

| Gap | OnlyFans | Fansly | FetLife |
|-----|----------|--------|---------|
| Mutating post submit + delete | — | — | text only |
| Media / image upload post | — | — | attach-only (non-mutating) |
| Video upload post | — | — | attach-only (non-mutating) |
| Media upload wired into post flow | — | — | — (task #417 Level B) |
| Paid / schedule / tier UI flows | — | — | — |
| Media processing functional tests | unit only | unit only | — |

Composer checkbox interaction (OnlyFans PPV/schedule toggles, etc.) is **not** covered
today. If mutating functional tests that exercise those controls fail because clicks do
not reach the input, that failure should drive Phase 6 interaction tests — not standing
OnlyFans checkbox coverage. See `docs/testing/WEBVIEW_TEST_PLAN.md` Phase 6.

**Snapchat** — disabled in the product; WebView functional tests are retained but
excluded from routine runs (`disabled_platform`). Image→video pipeline tests in
`test_media_processing.py` still cover the processing code path.

**Priority gaps to close next** (tracked in Odoo task #166):

1. **OnlyFans + Fansly mutating smoke tests** — submit a tagged post and delete, mirroring FetLife.
2. **FetLife media upload in the post flow** — `_attach_media()` and `_certify_upload_consent()` exist and are covered, but nothing calls them outside tests; wiring them into `_do_prefill()` is task #417 Level B.
3. **Media processing** — add resize/validation cases for Threads, Facebook Page, OnlyFans, and Fansly specs.
4. **Second-account slots** — no functional test exercises `twitter_2`, `bluesky_alt`, `meta_instagram_2`, or `meta_threads_2`.

### WebView Platform Session Tests

| Test case                  | OnlyFans | Fansly | FetLife |
|----------------------------|----------|--------|---------|
| Cookie database exists     | x        | x      | x       |
| has_valid_session()        | x        | x      | x       |
| Platform specs consistency | x        | x      | x       |

Snapchat session tests exist but are `disabled_platform` (excluded from routine runs).

### WebView Platform Posting Tests

| Test case                    | FetLife | Fansly | OnlyFans |
|------------------------------|---------|--------|----------|
| Session / connection         | x       | -      | -        |
| Composer page loads          | x       | x      | x        |
| Composer click expansion     | -       | -      | x        |
| Text injection (platform)    | x       | x      | x        |
| Text post submit + delete    | x       | -      | -        |
| Picture post submit + delete | -       | -      | -        |
| Video post submit + delete   | -       | -      | -        |
| Picture attach via platform (no submit) | x | -  | -        |
| Video attach via platform (no submit)   | x | -  | -        |
| Picture composer elements    | x       | -      | -        |
| Video composer elements      | x       | -      | -        |

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
This is a **skip** in all modes when `webprofiles/<account_id>/Cookies` does not exist — the platform is not configured for functional testing. Log in via GaleFling Settings (or import an OnlyFans `auth.json`) to create the profile first.

### WebView session tests fail with "session invalid"
The cookie database exists but `has_valid_session()` returned false (expired session). For OnlyFans, import a fresh `auth.json` via Settings or set `ONLYFANS_AUTH_JSON`. For Fansly/FetLife, log in again in Settings or use **Reset Session Cookies** and re-authenticate.

### Fansly / FetLife login fails during test
Check that the credentials in `.env` are correct. If the account is locked or requires email verification, complete that step manually in the GaleFling app first.

### OnlyFans composer tests skip with "No OnlyFans session" or "login form present"
OnlyFans cannot be logged in automatically during tests. Export `auth.json` from a normal browser, import it in GaleFling Settings, or set `ONLYFANS_AUTH_JSON` in `.env`. See [OnlyFans Session Import](../platforms/ONLYFANS_SESSION_IMPORT.md).

### A WebView test failure wedges every test after it
Fixed — but the failure mode is worth knowing. `BaseWebViewPlatform._evict_profile()` only drops the registry key; it does not destroy the `QWebEngineProfile` or release Chromium's lock on `webprofiles/<account_id>/`. When a test *fails*, pytest keeps the assertion traceback alive, and with it the test frame's `view` / `page` / `platform` locals — so unless teardown clears every reference itself, the profile survives, the next `create_webview()` builds a second profile on the same storage path, and every page load after that returns an empty URL while the process wedges at exit.

`close_webview()` therefore clears `platform._profile` (not just `_view` / `_page`), pumps deferred deletes before evicting, and runs a `gc.collect()` pass. Functional tests also carry a hard `pytest-timeout` ceiling (`FUNCTIONAL_TEST_TIMEOUT_S`, thread method) so a wedged profile fails one test with stack dumps instead of stalling the run — a Chromium deadlock sits in C++ and never returns to Python, so nothing else can interrupt it.

### FetLife post not auto-deleted
FetLife redirects to `/posts` after text submission instead of the individual post page. When a permalink is captured, the test attempts UI delete; otherwise search your feed for the UUID tag from the test output.

### FetLife picture/video tests — do not auto-submit
**Mutating picture/video functional tests were removed.** An earlier helper blindly checked every checkbox on the upload form (including **set as avatar**) and submitted real uploads during debugging.

Current coverage:
- **Non-mutating:** composer loads, file input present, `FetLifePlatform._attach_media()` loads the file into the form, `FetLifePlatform._certify_upload_consent()` ticks the certification box — **never clicks Upload**
- **Mutating:** text posts only

`_certify_upload_consent()` matches `picture[is_certified]` / `video[is_certified]` by **exact field name**. It cannot touch `picture[is_avatar]`, and `test_picture_attach_via_platform` asserts that box stays unchecked. Do not reintroduce keyword or substring matching over checkbox labels.

Manual cleanup if test uploads occurred: delete the stray pictures from your gallery, restore your previous avatar in FetLife profile settings, and search for any text posts containing the UUID tag from the failed run.

Wiring media upload into the actual post flow is task #417 Level B. That should override `QWebEnginePage.chooseFiles()` rather than extend the current base64/`DataTransfer` attach, which inlines the whole file into a script and so only suits test-sized media.

### FetLife picture composer has two file inputs
`pictures/new` renders a hidden picker carrying the `accept` list (`#picture_attachments`) **and** the real `picture[attachments][]` field, which has no `accept`. A comma-list `querySelector` returns the picker (first in document order), and FetLife moves the file to the named field and clears the picker **asynchronously**.

Consequences for any test or platform code touching this form:
- Select the picker by `accept`, not by name — `FetLifePlatform.IMAGE_FILE_SELECTOR`.
- Never verify an attach by re-reading the input you wrote to; it reports zero files on success. Poll `FetLifePlatform._media_attachment_state()`, which totals files across every file input.
- `videos/new` has a single input (`#video_video`) and keeps the file, so it does not show this behaviour. Code that works there can still be wrong for pictures.

### OnlyFans composer not found
The test attempts to click the compose area to expand the editor. If it still can't find the composer, the SPA may need full browser rendering. Run on Windows for the best chance of success.

### Snapchat JS execution fails
Snapchat is disabled in the product. WebView functional tests are excluded by default
(`disabled_platform`). Pass `--run-disabled-platforms` only when working on a
virtual-camera spike. Media-processing Snapchat transforms still run in
`test_media_processing.py`.

### Tests pass on Windows but fail in WSL
WebView platforms that depend on GPU rendering require native Windows. API-based platforms (Twitter, Bluesky, Meta APIs) and FetLife/Fansly work in both environments.
