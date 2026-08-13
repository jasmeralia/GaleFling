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

# 5b. As above, but leave the API posts up so they can be inspected before deletion
make test-functional-mutating-leave-up

# 6. Or use the legacy lenient mode with a virtual display
make test-functional-xvfb PYTHON=.venv/bin/python

# 7. Or via cmd.exe for native Windows process (full GPU/display, best for WebView tests)
#    First-time setup: create the Windows venv (only needed once)
make venv-win
#    Then run tests
make test-functional-cmd
```

`test-functional-non-mutating`, `test-functional-mutating`,
`test-functional-mutating-leave-up`, and
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
>
> `make test-functional-mutating-leave-up` deliberately skips the API deletes so the
> posts survive for inspection — see
> [Leaving mutating artifacts up for inspection](#leaving-mutating-artifacts-up-for-inspection).
> Everything it creates has to be deleted by hand afterwards.

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

## Leaving mutating artifacts up for inspection

The five API platforms — Twitter, Bluesky, Instagram, Threads, Facebook Page — delete
the post they create as soon as their assertions pass. That keeps the account clean, but
it also destroys the only evidence that the post existed. A green run is a weak signal on
its own: adapter return values, "we got an ID back", and UI movement have all reported
success while the platform received nothing, or received something other than what the
assertions checked. When an assertion needs to be re-read or rewritten, the artifact is
the only thing that can settle it — and a probe against an already-deleted post answers
"not found", which is indistinguishable from a real measurement failure.

To keep the posts:

```bash
make test-functional-mutating-leave-up

# or, running pytest directly
.venv/bin/python -m pytest tests/functional/ -m "functional and mutating" \
  -v --leave-mutating-artifacts

# or via the environment, for runners that pass env more easily than argv
GALEFLING_LEAVE_MUTATING_ARTIFACTS=1 make test-functional-mutating
```

**The default is unchanged.** Without the flag, mutating runs still delete what they
create, so an unattended run does not litter the account.

### What gets reported

Each finished artifact prints its outcome as **two separate lines** — the tag first, then
the permalink. The tag line is emitted before anything URL-related is touched, so a
platform that reports no permalink cannot suppress it; the tag is the only fallback for
finding the post by hand.

```
  Twitter artifact left up (tag a1b2c3d4) — --leave-mutating-artifacts is set; delete it manually once inspection is finished
  Twitter artifact URL: https://x.com/example/status/1234567890
```

These lines survive pytest's output capture even when the test **passes**, which is
exactly when they are needed — no `-s` required. Avoid `-s` here: the `mutating` marker
also selects WebView tests, whose Chromium logging would bury the report.

With deletion enabled, the outcome is reported in three distinct forms rather than
silently swallowed, so a delete that quietly stopped working is visible in scrollback:

| Line | Meaning |
|---|---|
| `artifact deleted (tag …)` | The platform accepted the delete. |
| `artifact already gone (tag …)` | The platform reports it is not there. Safe; not a failure. |
| `artifact delete FAILED (tag …)` | **The post is still live.** Delete it by hand. |

A failed delete also prints the URL and is written to the ledger, because it leaves an
artifact behind just as surely as the opt-out flag does.

### The cleanup ledger

Every artifact left live — by the flag or by a failed delete — is appended to
`tests/functional/.artifacts.jsonl`, so a later cleanup pass does not have to re-derive
state from scrollback. The file is gitignored: it names real posts on real accounts.

```json
{"platform": "Twitter", "account_id": null, "tag": "a1b2c3d4", "url": "https://x.com/…", "test": "tests/functional/test_twitter_post.py::TestTwitterTextPost::test_text_post", "created_at": "2026-08-13T18:04:11.902+00:00"}
```

`url` is written as `null` rather than omitted when no permalink was available. The
record shape is fixed by task #420 so the API and WebView sides can share one cleanup
consumer instead of growing two formats. **No credential values are written** — not to
the ledger, not to the printed lines. A failed delete is reported by HTTP status or by
exception class name, never by exception message, because a `requests` or `tweepy` error
renders the request URL and for the Graph platforms that URL carries `access_token` in
its query string.

### Relationship to WebView `CLEANUP PENDING`

The two are not the same mechanism and the difference matters:

| | API platforms | WebView platforms |
|---|---|---|
| Default | **Deletes** the post | **Leaves** the post up |
| Opt-out / opt-in | `--leave-mutating-artifacts` suppresses the delete | No switch; deletion pass is task #420 |
| Line printed | `artifact left up` / `deleted` / `already gone` / `delete FAILED` | `CLEANUP PENDING` |

A `CLEANUP PENDING` line fires unconditionally the moment a WebView artifact is created.
It is a statement that something exists, **not** a request to delete it — see `AGENTS.md`
rule 9. The same applies to the `artifact left up` line: report it so the operator knows
the post is there, leave it up while any question about it is still open, and ask for
deletion separately once every assertion has been verified.

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
`make test-functional-mutating`, `make test-functional-mutating-leave-up`, and
`make test-functional-linux` enable strict
mode. The four Linux desktop targets borrow the complete live graphical-session
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

#### Credential fixtures redact themselves

Every `*_credentials` fixture returns a `RedactedCredentials` mapping (defined in
`tests/functional/conftest.py`) rather than a plain `dict`. Subscripting works as
normal — `creds['password']` still returns the password — but the mapping renders as
`<RedactedCredentials: email, password>` instead of its values.

This exists because **pytest prints every fixture argument in a failing test's
traceback header**, using each value's `repr`. A credential fixture returning a plain
dict therefore prints the live password on any failure, with nothing in the test doing
the printing, and invisibly until something fails. That is how a Fansly password
reached a session transcript and had to be rotated.

Redacting at the value rather than the command line means it holds under `--tb=long`,
`--showlocals`, and an f-string in an assertion message. **A new credential fixture
must wrap its return value the same way** — `test_every_credential_fixture_returns_a_redacted_mapping`
in `tests/test_functional_outcomes.py` fails if one forgets.

Reading a credential into a string is still your responsibility: nothing stops
`f'{creds["password"]}'`, and the rule against printing `.env` values is unchanged.

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

Every mutating post embeds an 8-character hex UUID tag in the caption/text (via `mutating_post_text()` / `mutating_post_tag()` in `conftest.py`). Search the account for that tag if cleanup fails. API tests print the tag on every outcome and record still-live artifacts to a ledger — see [Leaving mutating artifacts up for inspection](#leaving-mutating-artifacts-up-for-inspection).

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
| FetLife (picture/video) | **Manual** | Upload is exercised for real; FetLife's delete control resists automation, so the run prints the tag and you delete it |

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

Twitter and Bluesky mutating tests additionally read the artifact back off the platform
and assert it carries the tag and the expected media, rather than trusting the adapter's
own `result.success` and returned ID. Instagram, Threads and Facebook Page do not yet.

Two things to know before adding that check to another platform:

- **Twitter — tweepy's read methods default to `user_auth=False`**, which authenticates
  with an OAuth 2.0 app-only bearer token. GaleFling's Twitter client is built from
  OAuth 1.0a credentials and has no bearer token, so the default returns a 401 that is
  easily misread as "this endpoint is not available on your access tier". Pass
  `user_auth=True` explicitly. Write methods (`create_tweet`, `delete_tweet`) already
  default to `True`, which is why posting works while a naive read does not.
- **Bluesky — read via `get_posts()` (the hydrated `app.bsky.feed.getPosts` view), not
  `get_post()`/`getRecord`.** Only the hydrated view resolves the embed, so media can be
  asserted from what the network serves rather than from what we asked it to store. Media
  kind is matched on the embed view's `py_type` discriminator
  (`app.bsky.embed.images#view`, `app.bsky.embed.video#view`) so an unrecognised embed
  reports as unexpected instead of silently counting as no media. The AppView indexes
  asynchronously, so a cold read can miss a post that genuinely exists — both platforms'
  helpers retry for ~8s before failing.

- **The three Meta platforms — Graph answers a missing object with HTTP 400 / code 100,
  not 404.** Any "already gone" detection keyed on 404 is dead code. The delete helpers
  deliberately have no "already gone" mapping at all, because code 100's own message is
  "does not exist, cannot be loaded due to missing permissions, or does not support this
  operation" — one status covering three very different causes, and treating it as benign
  would hide a delete broken by a missing scope. A Threads carousel also reports
  `CAROUSEL_ALBUM` at the top level with the real per-item types on its `children` edge,
  so attachments must be counted from the children.

The Bluesky URL-facet test also asserts the link facet reached the published record.
`detect_urls()` building a facet locally was never evidence that Bluesky stored one.

> **Threads mutating runs cannot clean up after themselves.** The configured token lacks
> the `threads_delete` scope, which GaleFling does not request because the app never
> deletes a post. Every Threads delete therefore answers `HTTP 500 / code 10 —
> "Application does not have permission for this action"`, and the run reports
> `artifact delete FAILED` and writes a ledger record. **Every mutating Threads run
> leaves six posts on the account that have to be removed by hand** until a wider token
> is in place.
>
> Mint one with `.venv/bin/python tools/oauth/meta_threads_remint.py` (see
> [THREADS.md](../platforms/THREADS.md#required-permissions)). Enabling the scope in the
> App Dashboard is not enough by itself — a token carries the scopes it was granted at
> authorization time, so an already-issued token keeps being refused. Long-lived tokens
> expire after 60 days, so this recurs.
>
> This is exactly the silent failure the three-outcome reporting exists to expose: six
> undeleted posts from a 2026-08-12 run sat on the account for a day because the previous
> best-effort delete swallowed the error and the run still passed green.
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
| Opt-out cleanup + artifact reporting | ✓ | ✓ | ✓ | ✓ | ✓ |
| Artifact read back off the platform | ✓ | ✓ | — | — | — |
| Media processing functional tests | partial | partial | partial | — | — |
| Token refresh / expiry warning path | — | — | — | — | — |
| Rate-limit headroom check | — | — | — | — | — |

#### WebView platforms

| Gap | OnlyFans | Fansly | FetLife |
|-----|----------|--------|---------|
| Mutating post submit + delete | — | — | text only |
| Media / image upload post | — | blocked (see below) | **covered** (mutating) |
| Video upload post | — | blocked (see below) | **covered** (mutating) |
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

1. **OnlyFans mutating smoke test** — submit a tagged post and verify it exists, mirroring FetLife and Fansly. (Fansly done.)
2. **FetLife media upload in the post flow** — `_attach_media()`, `_certify_upload_consent()` and `_inject_media_caption()` exist and are covered by mutating tests, but nothing calls them outside tests; wiring them into `_do_prefill()` is task #417 Level B.
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
| Session / connection         | x       | x      | -        |
| Composer page loads          | x       | x      | x        |
| Composer elements present    | x       | x      | -        |
| Composer click expansion     | -       | -      | x        |
| Text injection (platform)    | x       | x      | x        |
| Text post creates a post     | x       | x      | -        |
| Picture upload (real post)   | x       | -      | -        |
| Video upload (real post)     | x       | -      | -        |
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
- `make test-functional-mutating-leave-up` does the same but leaves the API posts on the
  account for inspection instead of deleting them

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

### Attaching media: use the file picker, not a synthetic DataTransfer
`_attach_media()` writes a synthetic `DataTransfer` onto the file input. That works on FetLife's composers and **does not work on Fansly at all** — its Angular uploader ignores the synthetic selection outright (verified 2026-08-12: the input clears and the composer subtree is byte-identical twelve seconds later).

The mechanism that does work everywhere is Chromium's own file picker, via `chooseFiles()`:

1. `platform.stage_media_for_picker(path)` queues the file.
2. A **trusted** click grants user activation — Chromium refuses to open a picker without it, and JavaScript cannot grant it. Tests use a real `QTest` mouse event; shipped code uses `BaseWebViewPlatform.trusted_click()` and a synthesised `QMouseEvent` without importing `QtTest`.
3. `platform.open_media_picker()` issues a JS `input.click()`, which Chromium now allows.
4. `_LoggingWebEnginePage.chooseFiles()` returns the staged path, and the page receives a genuine `change` event with a real `File`.

`attach_via_file_picker()` wraps steps 1–4, and the mechanism itself is verified at the Qt level: `chooseFiles()` fires and Chromium accepts the returned path as a real selection.

**Clicking Fansly's bare input is still not enough.** Chromium hands over a genuine
selection, but the composer ignores it because Fansly's uploader is not in the call
stack. The working route drives Fansly's own image dropdown and exact **Upload New**
leaf, lets that control open the picker, applies the no-paywall modal policy, and clicks
the modal's enabled **Upload** control. Success is scoped to
`media-upload-container`, then the flow waits separately for Post to enable.

> **A cautionary note on measuring this.** An earlier version of these tests "proved" the Fansly attach worked by counting elements matching `[class*="preview"]`. That count is dominated by the surrounding feed — it sits at ~81 with nothing attached and drifts by a couple as the feed updates. The same trap applies to `media-loading` (46 at baseline) and to a parent-walk scope from the composer textarea, which escapes into the feed after ~6 levels. Scope to `media-upload-container` and compare against a pristine-composer baseline before believing any counter.

Two constraints learned the hard way:
- **The activation target must be visible.** FetLife's `picture[caption]` textarea has zero size until a file is attached, so clicking it grants nothing. `trusted_click()` accepts a tuple of candidate selectors and skips any that are not rendered.
- **Tests must set `suppress_native_file_dialog`.** Without a staged file the override falls through to Qt's real dialog, which is correct for the app but blocks a headless run forever. `attach_via_file_picker()` sets it.

Fansly's uploader consumes the file into Angular state and leaves `input.files` empty, so success is measured by a preview element appearing, not by counting files on the input.

#### Direct helper tests remain on the base64 path
The established FetLife helper tests still call `_attach_media()` deliberately. The
shipped `_do_prefill()` route does not: it uses the picker, removing the base64 size
ceiling for FetLife's 500 MB videos. A separate non-mutating FetLife picture test enters
through `_do_prefill()` and verifies the picker, caption, consent, and avatar guard.
`FanslyPlatform` still inherits `_attach_media()`, but **it does not work on Fansly**.
Verified 2026-08-12 against the live composer: assigning a synthetic `DataTransfer` and
dispatching `input`/`change` clears the file input and changes nothing else — twelve
seconds later the composer subtree is byte-identical (no preview element, no
`app-media`, textarea still `ng-pristine ng-invalid`). Fansly's Angular uploader
requires its own trusted UI path.

Task #417 Level B now uses the `QWebEnginePage.chooseFiles()` approach in production:
for FetLife it removes the size ceiling; for Fansly it is part of the only verified UI
route. Existing low-level tests remain useful characterization coverage and are not a
substitute for the `_do_prefill()` entry-point test.

### FetLife statuses are not auto-deleted — every mutating run leaves one
`test_text_post_submit_and_delete` posts a real status and **cannot currently remove it**. It reports this rather than claiming success: the run prints `MANUAL CLEANUP NEEDED` with the tag. Delete it from your feed after a mutating run.

Why it cannot: FetLife's Delete control is an `<a href="#0">` whose payload is a `data` attribute stringifying to `[object Object]` — no `data-method`, no `data-turbo-confirm`, no delete endpoint, and the status permalink page offers the same control rather than a form. The handler is bound in JavaScript, so a synthetic `.click()` never reaches it. Automating it requires a trusted `QTest.mouseClick` (Phase 6's pattern), opening the "More options" dropdown first.

### FetLife post not auto-deleted
FetLife redirects to `/posts` after text submission instead of the individual post page. When a permalink is captured, the test attempts UI delete; otherwise search your feed for the UUID tag from the test output.

### FetLife picture/video uploads — real, and cleaned up by hand
Mutating upload tests exist again and create **real** pictures and videos. They were once removed because an earlier helper blindly checked every checkbox on the upload form — including **set as avatar** — and submitted real uploads while debugging.

The guard against a repeat is structural, not procedural: `_certify_upload_consent()` matches the certification field by exact name and cannot reach `picture[is_avatar]`, and `test_picture_upload_creates_a_post` asserts that box is unchecked **immediately before clicking Upload**, refusing to submit otherwise.

Current coverage:
- **Non-mutating:** composer loads, file input present, `_attach_media()` loads the file into the form, `_certify_upload_consent()` ticks the certification box — never clicks Upload
- **Mutating:** text status, picture upload, video upload — each proves the post exists before passing

Every mutating media run leaves a real post; the run prints `MANUAL CLEANUP NEEDED` with the tag. Delete them from your gallery afterwards.

#### Verifying a media upload: what actually signals success
Neither upload announces itself by navigation in the way you would expect, and getting this wrong produces a test that passes while nothing was created:

| | How success is detected |
|---|---|
| Picture | Redirects to the permalink `/<username>/pictures/<id>`; the caption tag is on the page |
| Video | **Stays on `/videos/new`.** The transfer and transcode happen in place, so the URL never changes — the only honest check is polling `/<username>/videos` for the tag |

`_certify_upload_consent()` matches `picture[is_certified]` / `video[is_certified]` by **exact field name**. It cannot touch `picture[is_avatar]`, and `test_picture_attach_via_platform` asserts that box stays unchecked. Do not reintroduce keyword or substring matching over checkbox labels.

Manual cleanup after a mutating run: delete the tagged picture and video from your gallery. If an old run ever set an avatar, restore it in FetLife profile settings.

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
