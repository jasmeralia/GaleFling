# GaleFling - Agent Context

## Project Overview
Windows GUI application for posting to multiple social media platforms simultaneously. Built for non-technical users with robust error handling and remote troubleshooting capabilities.

**Target User:** Content creator (Rin) - prioritizes simplicity and clear guidance
**Developer:** Jas - will provide initial setup and remote support

## Current Status
- **Phase 0** (v0.2.118): Complete — Twitter and Bluesky working
- **Phase 1** (v1.0.0): **Complete** — Multi-account, 7 platforms, WebView integration, PyQt6 migration

### Phase 1 Progress (All Steps Complete)
- [x] **Step 1: PyQt5 → PyQt6 migration** — All source and test files migrated, 168 tests passing
- [x] **Step 2: Multi-account architecture** — AccountConfig, accounts_config.json, updated PlatformSpecs/PostResult
- [x] **Step 3: Existing platform refactoring** — Twitter PIN flow support, Bluesky account_id alignment
- [x] **Step 4: WebView infrastructure** — BaseWebViewPlatform + WebViewPanel implemented
- [x] **Step 5: Instagram platform** — Instagram Graph API fully implemented with tests
- [x] **Step 6: WebView platforms** — Snapchat, OnlyFans, Fansly, FetLife all implemented with tests
- [x] **Step 7: GUI updates** — Platform selector, setup wizard, settings, results dialog, main window all updated for multi-account
- [x] **Step 8: Error codes finalization** — All IG-* and WV-* codes defined, SuicideGirls deferred
- [x] **Step 9: Testing & polish** — 168 tests passing, 71% coverage, lint clean
- [x] **Step 10: Build & release** — Version bump to 1.0.0, CHANGELOG updated, all checks passing

**Note:** SuicideGirls support is deferred to future phases.

---

## Release Checklist
- Run `make lint` and confirm it passes.
- Run `make test` (or `make test-cov` if releasing) and confirm it passes.
- Bump version in `src/utils/constants.py`, `resources/default_config.json`, `build/installer.nsi`, `build/version_info.txt`, and `README.md`.
- Update `CHANGELOG.md` with a new version entry at the top.
- Commit with message `Release vX.Y.Z`.
- Tag with `vX.Y.Z` and push tag and `master`.
- Always run the full checklist after making any changes unless explicitly instructed otherwise.
- Any new menu options must add a log entry like `User selected <Menu> > <Action>`.

---

## Technology Stack

```
Language: Python 3.11+
GUI Framework: PyQt6 (migrated from PyQt5)
WebEngine: PyQt6-WebEngine (QtWebEngineWidgets)
Image Processing: Pillow (PIL)
APIs:
  - tweepy (Twitter - OAuth 1.0a PIN flow, pay-per-tweet)
  - atproto (Bluesky - app password auth)
  - requests + facebook-sdk (Instagram Graph API)
Packaging: PyInstaller + NSIS installer
Auth Storage: keyring (Windows Credential Manager) + accounts_config.json
Current Version: 1.1.0 (Phase 1 complete)
```

### PyQt6 Notes
- `exec_()` → `exec()` on dialogs and QApplication
- Enums are fully qualified: `Qt.AlignLeft` → `Qt.AlignmentFlag.AlignLeft`
- `QAction` lives in `PyQt6.QtGui`, not `QtWidgets`
- `QDesktopWidget` removed — use `QScreen` instead
- `PyQt6-WebEngine` is a separate pip package

---

## Project Structure

```
galefling/
├── src/
│   ├── main.py                        # Application entry point
│   ├── gui/
│   │   ├── __init__.py
│   │   ├── main_window.py             # Main application window (two-tier posting)
│   │   ├── setup_wizard.py            # First-run credential setup (multi-account)
│   │   ├── post_composer.py           # Text + image selection widget (dynamic counters)
│   │   ├── platform_selector.py       # Platform checkboxes (account-based, 2-column grid)
│   │   ├── image_preview_tabs.py      # TABBED platform-specific previews
│   │   ├── results_dialog.py          # Post results (CLICKABLE links + WebView states)
│   │   ├── settings_dialog.py         # Debug mode, update settings, log upload, account management
│   │   ├── update_dialog.py           # Update available notification
│   │   ├── log_submit_dialog.py       # Log submission with description
│   │   └── webview_panel.py           # Tabbed WebView panel for confirm-click platforms
│   ├── platforms/
│   │   ├── __init__.py
│   │   ├── base.py                    # Abstract platform interface (account_id/profile_name)
│   │   ├── base_webview.py            # Abstract base for WebView platforms
│   │   ├── twitter.py                 # Twitter (multi-account, PIN flow)
│   │   ├── bluesky.py                 # Bluesky (with link facets)
│   │   ├── instagram.py               # Instagram Graph API (multi-account)
│   │   ├── snapchat.py                # Snapchat WebView (multi-account)
│   │   ├── onlyfans.py                # OnlyFans WebView (Cloudflare-aware)
│   │   ├── fansly.py                  # Fansly WebView (Cloudflare-aware)
│   │   └── fetlife.py                 # FetLife WebView
│   ├── core/
│   │   ├── __init__.py
│   │   ├── image_processor.py         # Resize/optimize per platform
│   │   ├── error_handler.py           # Error codes + logging
│   │   ├── logger.py                  # File logging + screenshots
│   │   ├── config_manager.py          # App settings persistence
│   │   ├── auth_manager.py            # Credential storage (multi-account)
│   │   ├── log_uploader.py            # HTTP POST logs to endpoint
│   │   └── update_checker.py          # GitHub release checking
│   └── utils/
│       ├── __init__.py
│       ├── constants.py               # Platform specs, error codes, AccountConfig
│       ├── helpers.py                 # Utility functions
│       └── theme.py                   # Theme/palette management
├── resources/
│   ├── icon.ico
│   ├── icon.png
│   └── default_config.json
├── tests/
│   ├── __init__.py
│   ├── conftest.py                    # Headless display setup for WSL/CI
│   ├── test_platforms.py
│   ├── test_platform_clients.py
│   ├── test_image_processor.py
│   ├── test_image_processor_platforms.py  # Phase 1 platform specs tests
│   ├── test_error_handler.py
│   ├── test_auth_manager.py
│   ├── test_auth_manager_accounts.py  # Phase 1 account CRUD tests
│   ├── test_results_dialog_webview.py # WebView result states
│   ├── test_webview_platform.py       # WebView infrastructure tests
│   ├── test_webview_platforms.py      # Snapchat/OnlyFans/Fansly/FetLife tests
│   ├── test_instagram.py              # Instagram Graph API tests
│   └── ... (168 tests total across 27 files)
├── build/
│   ├── build.spec                     # PyInstaller specification (PyQt6 + WebEngine)
│   ├── version_info.txt
│   └── installer.nsi
├── requirements.txt
├── requirements-dev.txt
├── README.md
├── LICENSE.md
├── CHANGELOG.md
└── AGENTS.md                          # This file
```

---

## Multi-Account Architecture

### Account Data Model
```python
@dataclass
class AccountConfig:
    platform_id: str      # e.g., "twitter", "instagram"
    account_id: str       # e.g., "twitter_1", "twitter_2"
    profile_name: str     # User-assigned label, e.g., "rinthemodel"
    enabled: bool = True
```

### Supported Platforms & Account Limits
| Platform | Max Accounts | Auth Method | API Type | Status |
|---|---|---|---|---|
| Twitter | 2 | OAuth 1.0a PIN flow | tweepy | ✅ Implemented |
| Bluesky | 2 | App password | atproto | ✅ Implemented |
| Instagram | 2 | OAuth 2.0 / Graph API | graph_api | ✅ Implemented |
| Snapchat | 2 | WebView session cookies | webview | ✅ Implemented |
| OnlyFans | 1 | WebView session cookies | webview | ✅ Implemented |
| Fansly | 1 | WebView session cookies | webview | ✅ Implemented |
| FetLife | 1 | WebView session cookies | webview | ✅ Implemented |

**Platform Colors:**
- Twitter: `#1DA1F2`
- Bluesky: `#0085FF`
- Instagram: `#E1306C`
- Snapchat: `#FFFC00`
- OnlyFans: `#00AFF0`
- Fansly: `#0FABE5`
- FetLife: `#D4001A`

### Auth Storage
- **accounts_config.json** (`%APPDATA%/GaleFling/`): Non-secret account metadata (platform_id, account_id, profile_name, enabled)
- **Keyring storage**: Per-account credentials stored in Windows Credential Manager with keys like `galefling:{account_id}:access_token`
- **Twitter app credentials**: Shared across all Twitter accounts under `galefling:twitter_app:api_key` namespace
- **WebView profiles**: Session cookies at `%APPDATA%/GaleFling/webprofiles/{account_id}/`
- **Phase 0 backward compat**: Old `twitter_auth.json` / `bluesky_auth.json` files auto-migrate on first load

### Twitter PIN Flow
- API key + secret belong to Jas's developer app (entered once, stored under `twitter_app` namespace in keyring)
- Per-account access tokens obtained via OAuth 1.0a out-of-band (PIN) flow:
  1. App calls `POST oauth/request_token` with `oauth_callback=oob`
  2. Opens authorization URL in system browser
  3. User logs into Twitter, authorizes app, receives 7-digit PIN
  4. User enters PIN in wizard
  5. App exchanges PIN for permanent access token + secret
  6. Tokens stored in keyring under `galefling:{account_id}:access_token`
- Second account setup skips app credential entry entirely (reuses existing `twitter_app` credentials)

### Instagram Graph API Flow
- Requires Business/Creator account linked to Facebook Page
- Credentials stored in keyring: `access_token`, `ig_user_id`, `page_id`
- Post flow:
  1. Upload image to Facebook Page `/photos` endpoint
  2. Create media container with image ID + caption
  3. Publish container
  4. Extract permalink from response
- Multi-account support: Up to 2 Instagram accounts (`instagram_1`, `instagram_2`)

### Two-Tier Posting Architecture
- **Tier 1 (Silent API)**: Twitter, Bluesky, Instagram — post automatically in background (`PostWorker` thread)
- **Tier 2 (Confirm-Click WebView)**: Snapchat, OnlyFans, Fansly, FetLife — `WebViewPanel` opens with pre-filled composer, user clicks Post manually

Posting flow in `main_window.py::_do_post()`:
1. Split selected accounts into `api_platforms` dict and `webview_platforms` list
2. API platforms post via `PostWorker` in background
3. On `PostWorker` completion, if `webview_platforms` exist, open `WebViewPanel`
4. User manually confirms posts in WebView tabs
5. `ResultsDialog` shows combined results from both tiers

---

## Platform Specifications

All defined as `PlatformSpecs` dataclass instances in `src/utils/constants.py`. Key fields:

```python
@dataclass
class PlatformSpecs:
    platform_name: str
    max_image_dimensions: tuple[int, int]
    max_file_size_mb: float
    supported_formats: list[str]
    max_text_length: int | None          # None = no known limit (WebView platforms)
    requires_facets: bool = False
    platform_color: str = '#000000'
    api_type: str = ''                   # 'tweepy', 'atproto', 'graph_api', 'webview'
    auth_method: str = ''
    max_accounts: int = 1
    requires_user_confirm: bool = False  # True for WebView platforms
    has_cloudflare: bool = False         # OnlyFans, Fansly
```

Lookup via `PLATFORM_SPECS_MAP: dict[str, PlatformSpecs]` or individual constants (`TWITTER_SPECS`, `BLUESKY_SPECS`, `INSTAGRAM_SPECS`, etc.)

### Platform Requirements
| Platform | Max Dimensions | Max Size | Formats | Text Limit |
|---|---|---|---|---|
| Twitter | 4096x4096 | 5 MB | JPEG, PNG, GIF, WEBP | 280 |
| Bluesky | 2000x2000 | 1 MB | JPEG, PNG | 300 |
| Instagram | 1440x1440 | 8 MB | JPEG, PNG | 2200 |
| Snapchat | 1080x1920 | 5 MB | JPEG, PNG | None |
| OnlyFans | 4096x4096 | 50 MB | JPEG, PNG, WEBP | 1000 |
| Fansly | 4096x4096 | 50 MB | JPEG, PNG, WEBP | 3000 |
| FetLife | 4096x4096 | 20 MB | JPEG, PNG | None |

### PostResult
```python
@dataclass
class PostResult:
    success: bool
    platform: str = ''
    post_url: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    raw_response: dict | None = None
    timestamp: str = ...
    account_id: str | None = None       # Which account posted
    profile_name: str | None = None     # Display name for results
    url_captured: bool = False          # Whether URL was successfully captured
    user_confirmed: bool = False        # Whether user clicked Post (WebView)
```

### BasePlatform Interface
```python
class BasePlatform(ABC):
    account_id: str       # property
    profile_name: str     # property
    authenticate() -> tuple[bool, str | None]
    test_connection() -> tuple[bool, str | None]
    get_specs() -> PlatformSpecs
    post(text, image_path) -> PostResult
    get_platform_name() -> str  # Returns "Platform (username)" format
```

---

## WebView Infrastructure

### BaseWebViewPlatform
Abstract class in `src/platforms/base_webview.py` extending `BasePlatform`:
- **Profile isolation**: `QWebEngineProfile(account_id)` with persistent cookies at `%APPDATA%/GaleFling/webprofiles/{account_id}/`
- **Text pre-fill**: JS injection via configurable CSS selector, triggered after `loadFinished` + `PREFILL_DELAY_MS`
- **Image upload**: Platform-specific (not yet implemented — manual selection by user)
- **URL capture (Stage 1)**: `urlChanged` signal monitoring against `SUCCESS_URL_PATTERN` regex
- **URL capture (Stage 2)**: DOM `MutationObserver` injection + polling (not yet implemented)
- **Cloudflare-aware**: `PREFILL_DELAY_MS` = 1500ms for OnlyFans/Fansly (default 200ms)
- **Result building**: `build_result()` produces `PostResult` with `url_captured`/`user_confirmed` flags

Subclass hooks:
```python
def _get_composer_url() -> str          # URL to navigate to
def _get_text_selector() -> str         # CSS selector for text input
def _get_image_upload_selector() -> str # CSS selector for file input (unused currently)
def _get_success_url_pattern() -> str   # Regex for post permalink URL (optional)
def _get_cloudflare_delay_ms() -> int   # Delay before pre-fill (default 200ms)
```

Example implementation (Snapchat):
```python
class SnapchatPlatform(BaseWebViewPlatform):
    def _get_composer_url(self) -> str:
        return 'https://web.snapchat.com/'

    def _get_text_selector(self) -> str:
        return 'textarea[placeholder*="Say something"]'  # Empirically determined

    def _get_success_url_pattern(self) -> str:
        return r'https://web\.snapchat\.com/.*'  # Snapchat is SPA, URL capture unlikely
```

### WebViewPanel
Dialog in `src/gui/webview_panel.py`:
- Shows API platform results at top (✓/❌ rows)
- Tabbed `QWebEngineView` below, one tab per WebView account
- Real-time status indicators per tab (checkmark when URL captured or user clicks "Mark as Done")
- Pre-fills text into each tab's composer automatically
- `get_results()` collects `PostResult` from all WebView platforms
- Dialog persists until user closes or all tabs confirmed

### URL Capture Viability
| Platform | Architecture | URL Capture | Expected Outcome |
|---|---|---|---|
| FetLife | Traditional | Good | URL usually captured via `urlChanged` |
| OnlyFans | Heavy React SPA | Poor | "Link unavailable" likely |
| Fansly | Heavy React SPA | Poor | "Link unavailable" likely |
| Snapchat | Modern SPA | Poor | "Link unavailable" likely |

**"Posted (link unavailable)"** is a **normal, non-error state** for SPA platforms. It means `user_confirmed=True` but `url_captured=False`. Only logged at DEBUG level.

---

## Error Code System

### Format
`PLATFORM-CATEGORY-DETAIL` — e.g., `TW-AUTH-EXPIRED`, `WV-SESSION-EXPIRED`

### Error Categories
- **AUTH**: Authentication errors (`TW-AUTH-INVALID`, `TW-AUTH-EXPIRED`, `BS-AUTH-INVALID`, `BS-AUTH-EXPIRED`, `IG-AUTH-INVALID`, `IG-AUTH-EXPIRED`, `AUTH-MISSING`)
- **RATE**: Rate limiting (`TW-RATE-LIMIT`, `BS-RATE-LIMIT`, `IG-RATE-LIMIT`)
- **IMG**: Image processing errors (`IMG-TOO-LARGE`, `IMG-INVALID-FORMAT`, `IMG-RESIZE-FAILED`, `IMG-UPLOAD-FAILED`, `IMG-NOT-FOUND`, `IMG-CORRUPT`)
- **NET**: Network errors (`NET-TIMEOUT`, `NET-CONNECTION`, `NET-DNS`, `NET-SSL`)
- **POST**: Post submission errors (`POST-TEXT-TOO-LONG`, `POST-DUPLICATE`, `POST-FAILED`, `POST-EMPTY`)
- **WV**: WebView-specific errors (`WV-LOAD-FAILED`, `WV-PREFILL-FAILED`, `WV-SUBMIT-TIMEOUT`, `WV-SESSION-EXPIRED`, `WV-URL-CAPTURE-FAILED`)
- **SYS**: System errors (`SYS-CONFIG-MISSING`, `SYS-PERMISSION`, `SYS-DISK-FULL`, `SYS-UNKNOWN`)

Each code has both a technical message in `ERROR_CODES` dict and a user-friendly message in `USER_FRIENDLY_MESSAGES` dict (both in `constants.py`).

---

## Image Processing

### Processing Pipeline
1. User selects image → load with PIL, convert RGBA → RGB (white background)
2. For each enabled platform:
   - Calculate target dimensions (maintain aspect ratio within `max_image_dimensions`)
   - Resize using LANCZOS resampling
   - Compress iteratively (start quality=95, reduce by 5 until size < `max_file_size_mb` or quality < 20)
   - If still too large, reduce dimensions by 10% and retry
3. Generate thumbnail previews for `ImagePreviewDialog` tabs
4. Cache processed images in `main_window._processed_images` dict to avoid reprocessing on resubmit
5. Clean up processed images on successful post or draft clear

Implemented in `src/core/image_processor.py::process_image()`.

---

## Bluesky Link Facets

URLs in Bluesky posts must be converted to facet objects with **UTF-8 byte offsets** (not character positions). Implementation in `src/platforms/bluesky.py::detect_urls()`:

```python
def detect_urls(text: str) -> list[dict]:
    url_pattern = r'http[s]?://...'
    facets = []
    for match in re.finditer(url_pattern, text):
        byte_start = len(text[:match.start()].encode('utf-8'))
        byte_end = len(text[:match.end()].encode('utf-8'))
        facets.append({
            "index": {"byteStart": byte_start, "byteEnd": byte_end},
            "features": [{"$type": "app.bsky.richtext.facet#link", "uri": match.group(0)}]
        })
    return facets
```

---

## Logging & Remote Troubleshooting

### Log Structure
```
%APPDATA%/GaleFling/logs/
├── app_YYYYMMDD_HHMMSS.log
├── fatal_errors.log
└── screenshots/
    └── error_YYYYMMDD_HHMMSS.png
```

### Log Entry Format
```
2026-02-13 14:23:45,123 - GaleFling - ERROR - Error WV-SESSION-EXPIRED on OnlyFans
{
    "error_code": "WV-SESSION-EXPIRED",
    "platform": "OnlyFans",
    "account_id": "onlyfans_1",
    "profile_name": "rinthemodel",
    "timestamp": "2026-02-13T14:23:45.123456"
}
```

### Log Upload
- **Endpoint:** `POST https://galepost.jasmer.tools/logs/upload`
- **Infrastructure:** CloudFormation stack in `infrastructure/template.yaml`
- **Email:** `morgan@windsofstorm.net` (SES sender + recipient)
- User must provide a description via `LogSubmitDialog` before sending
- Sends: log file + screenshot (if available) + user description

---

## Auto-Update System
- Checks GitHub API (`https://api.github.com/repos/jasmeralia/galefling/releases/latest`) on startup (if enabled)
- Compares versions via `packaging.version.parse()`
- Supports prerelease/beta updates (configurable via `allow_prerelease_updates`)
- Downloads installer to `~/Downloads/GaleFlingSetup_{version}.exe` and launches with UAC prompt
- `UpdateDownloadWorker` thread with progress dialog

---

## Draft Auto-Save
- Every 30 seconds (configurable) to `%APPDATA%/GaleFling/drafts/current_draft.json`
- Persists: text, image path, selected accounts (account_ids), processed image paths, timestamp
- Restores on app restart with confirmation prompt
- Cleared on successful post or manual clear
- Format:
```json
{
    "text": "Check out my new set! 🔥",
    "image_path": "C:/Users/Rin/Pictures/set_cover.jpg",
    "selected_accounts": ["twitter_1", "bluesky_1", "onlyfans_1"],
    "processed_images": {"twitter": "C:/temp/processed_twitter.jpg", ...},
    "timestamp": "2026-02-13T14:23:45",
    "auto_saved": true
}
```

---

## Dependencies

### requirements.txt
```
PyQt6>=6.6.0
PyQt6-WebEngine>=6.6.0
tweepy>=4.14.0
atproto>=0.0.50
Pillow>=10.2.0
keyring>=25.0.0
requests>=2.31.0
packaging>=24.0
python-dotenv>=1.0.0
facebook-sdk>=3.1.0
```

### requirements-dev.txt
```
pytest>=8.0.0
pytest-qt>=4.3.0
pytest-cov>=4.1.0
ruff>=0.8.0
mypy>=1.8.0
pyinstaller>=6.3.0
types-requests
```

---

## Build & Development

```bash
# Setup
python -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt

# Run
.venv/bin/python src/main.py

# Test (168 tests)
PYTHON=.venv/bin/python make test

# Test with coverage (71% overall)
PYTHON=.venv/bin/python make test-cov

# Lint
.venv/bin/ruff check src/ tests/ infrastructure/
.venv/bin/ruff format --check src/ tests/ infrastructure/

# Build
pyinstaller build/build.spec
makensis build/installer.nsi
```

---

## Tooling

- **Linting & formatting:** ruff (configured in `pyproject.toml`). Run `make lint` / `make lint-fix`.
- **Testing:** pytest. **168 tests** across 27 files. Run `make test`.
- **Coverage:** 71% overall (reasonable for PyQt6 GUI app). Main gaps: WebView browser interaction, GUI event handlers, error paths.
- **Type checking:** mypy. Note: pre-existing false positive on `ImagePreviewDialog.Accepted`.
- **Building:** PyInstaller via `make build`, NSIS installer via `make installer`.
- **CI/CD:** GitHub Actions creates draft releases on tag push (`.github/workflows/release.yml`).

---

## Important Notes

### Critical Design Decisions
1. **Two-tier posting** — Silent API platforms (Twitter/Bluesky/Instagram) vs. confirm-click WebView platforms (Snapchat/OnlyFans/Fansly/FetLife)
2. **Named QWebEngineProfile per account_id** — Strict session isolation (different cookies per account)
3. **Post URL capture best-effort** — `urlChanged` signal + regex pattern matching; graceful fallback to "link unavailable"
4. **Profile names in all UI labels** — "Twitter (rinthemodel)", never bare "Twitter"
5. **Twitter PIN OAuth flow** — API key/secret from Jas (stored once), per-account tokens via PIN
6. **Cloudflare-aware WebView behavior** — 1500ms delay before pre-fill for OnlyFans/Fansly
7. **Tabbed image previews** — Scales to 10+ platform/account combinations
8. **Dynamic platform selector** — `set_accounts()` rebuilds checkboxes from `accounts_config.json`, 2-column grid layout
9. **Twitter app credentials shared** — `twitter_app` namespace in keyring, reused across all Twitter accounts

### User Experience Priorities
1. Simple and guided (non-technical user)
2. Clear error messages with codes + user-friendly messages
3. Remote troubleshooting (logs + screenshots + upload)
4. No data loss (auto-save drafts every 30s)
5. Platform failures don't block others (independent posting)
6. Post links visible and copyable for all platforms (when available)

### Development Priorities
1. ~~Phase 0 complete~~ ✅
2. ~~PyQt5 → PyQt6 migration~~ ✅
3. ~~Multi-account architecture~~ ✅
4. ~~WebView infrastructure~~ ✅
5. ~~Instagram API platform~~ ✅
6. ~~WebView platforms (Snapchat, OnlyFans, Fansly, FetLife)~~ ✅
7. ~~GUI updates for multi-account~~ ✅
8. ~~Testing & polish (168 tests)~~ ✅
9. Build & release (Step 10 pending)
10. Video support deferred to Phase 2

---

End of GaleFling Agent Context File
