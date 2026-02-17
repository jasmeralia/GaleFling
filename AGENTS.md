# GaleFling - Phase 0 Context

## Project Overview
Windows GUI application for posting to multiple social media platforms simultaneously. Built for non-technical users with robust error handling and remote troubleshooting capabilities.

**Target User:** Content creator (Rin) - prioritizes simplicity and clear guidance
**Developer:** Jas - will provide initial setup and remote support

## Phase 0 Scope
- **Platforms**: Twitter and Bluesky only
- **Media**: Single optional image per post
- **Core Features**: Platform selection, image optimization with tabbed previews, error handling with codes, auto-updates, log upload to endpoint

---

## Technology Stack

```
Language: Python 3.11+
GUI Framework: PyQt5
Image Processing: Pillow (PIL)
APIs: 
  - tweepy (Twitter - existing setup, pay-per-tweet)
  - atproto (Bluesky - app password auth)
Packaging: PyInstaller + NSIS installer
Auth Storage: keyring (Windows Credential Manager)
Version: 0.2.0 (Phase 0)
```

---

## Project Structure

```
galefling/
├── src/
│   ├── main.py                      # Application entry point
│   ├── gui/
│   │   ├── __init__.py
│   │   ├── main_window.py           # Main application window
│   │   ├── setup_wizard.py          # First-run credential setup
│   │   ├── post_composer.py         # Text + image selection widget
│   │   ├── platform_selector.py     # Platform checkboxes
│   │   ├── image_preview_tabs.py    # TABBED platform-specific previews
│   │   ├── results_dialog.py        # Post results (CLICKABLE links + copy buttons)
│   │   └── settings_dialog.py       # Debug mode, update settings, log upload config
│   ├── platforms/
│   │   ├── __init__.py
│   │   ├── base.py                  # Abstract platform interface
│   │   ├── twitter.py               # Twitter implementation (reuse existing patterns)
│   │   └── bluesky.py               # Bluesky implementation (with link facets)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── image_processor.py       # Resize/optimize per platform
│   │   ├── error_handler.py         # Error codes + logging
│   │   ├── logger.py                # File logging + screenshots
│   │   ├── config_manager.py        # App settings persistence
│   │   ├── auth_manager.py          # Credential storage via keyring
│   │   ├── log_uploader.py          # HTTP POST logs to endpoint
│   │   └── update_checker.py        # GitHub release checking
│   └── utils/
│       ├── __init__.py
│       ├── constants.py             # Platform specs, error codes
│       └── helpers.py               # Utility functions
├── resources/
│   ├── icon.ico                     # Windows app icon
│   ├── icon.png                     # macOS/Linux icon
│   └── default_config.json          # Default settings template
├── tests/
│   ├── __init__.py
│   ├── test_platforms.py
│   ├── test_image_processor.py
│   └── test_error_handler.py
├── build/
│   ├── build.spec                   # PyInstaller specification
│   ├── version_info.txt             # Windows exe metadata
│   └── installer.nsi                # NSIS installer script
├── logs/                            # Created at runtime (gitignored)
│   ├── app_YYYYMMDD_HHMMSS.log
│   └── screenshots/
├── requirements.txt
├── requirements-dev.txt
├── README.md
├── LICENSE.md
└── .gitignore
```

---

## Platform Specifications

### Twitter
```python
TWITTER_SPECS = {
    'platform_name': 'Twitter',
    'max_image_dimensions': (4096, 4096),
    'max_file_size_mb': 5.0,
    'supported_formats': ['JPEG', 'PNG', 'GIF', 'WEBP'],
    'max_text_length': 280,
    'requires_facets': False,
    'platform_color': '#1DA1F2',  # Twitter blue for UI
    'api_type': 'tweepy',
    'auth_method': 'oauth1.0a'
}
```

### Bluesky
```python
BLUESKY_SPECS = {
    'platform_name': 'Bluesky',
    'max_image_dimensions': (2000, 2000),  # Conservative for compatibility
    'max_file_size_mb': 1.0,
    'supported_formats': ['JPEG', 'PNG'],
    'max_text_length': 300,
    'requires_facets': True,  # Auto-detect URLs and create clickable links
    'platform_color': '#0085FF',  # Bluesky blue for UI
    'api_type': 'atproto',
    'auth_method': 'app_password'
}
```

---

## Core Data Structures

### PlatformSpecs
```python
@dataclass
class PlatformSpecs:
    """Platform-specific constraints and capabilities"""
    max_image_dimensions: Tuple[int, int]      # e.g., (4096, 4096)
    max_file_size_mb: float                     # e.g., 5.0
    supported_formats: List[str]                # e.g., ['JPEG', 'PNG', 'GIF']
    max_text_length: int                        # e.g., 280
    requires_facets: bool = False               # Bluesky link facets
    platform_color: str = "#000000"             # UI accent color
```

### PostResult
```python
@dataclass
class PostResult:
    """Result of a post attempt"""
    success: bool
    post_url: Optional[str] = None              # MUST be clickable in UI
    error_code: Optional[str] = None            # e.g., "TW-AUTH-EXPIRED"
    error_message: Optional[str] = None         # User-friendly message
    raw_response: Optional[dict] = None         # Full API response for debugging
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
```

### BasePlatform Interface
```python
class BasePlatform(ABC):
    """All platforms must implement this interface"""
    
    @abstractmethod
    def authenticate(self) -> Tuple[bool, Optional[str]]:
        """Authenticate with platform. Returns (success, error_code)"""
        
    @abstractmethod
    def test_connection(self) -> Tuple[bool, Optional[str]]:
        """Test if credentials are valid. Returns (success, error_code)"""
        
    @abstractmethod
    def get_specs(self) -> PlatformSpecs:
        """Return platform requirements and constraints"""
        
    @abstractmethod
    def post(self, text: str, image_path: Optional[Path]) -> PostResult:
        """Post content. Returns detailed result with clickable URL"""
        
    @abstractmethod
    def get_platform_name(self) -> str:
        """Return display name (e.g., "Twitter", "Bluesky")"""
```

---

## Error Code System

### Format
`PLATFORM-CATEGORY-DETAIL`

Examples: `TW-AUTH-EXPIRED`, `BS-RATE-LIMIT`, `IMG-TOO-LARGE`

### Error Code Definitions
```python
ERROR_CODES = {
    # Authentication (AUTH)
    'TW-AUTH-INVALID': 'Twitter credentials are invalid',
    'TW-AUTH-EXPIRED': 'Twitter access token has expired',
    'BS-AUTH-INVALID': 'Bluesky app password is invalid',
    'BS-AUTH-EXPIRED': 'Bluesky session has expired',
    'AUTH-MISSING': 'No credentials found for platform',
    
    # Rate Limiting (RATE)
    'TW-RATE-LIMIT': 'Twitter rate limit exceeded',
    'BS-RATE-LIMIT': 'Bluesky rate limit exceeded',
    
    # Image Processing (IMG)
    'IMG-TOO-LARGE': 'Image file size exceeds platform limits',
    'IMG-INVALID-FORMAT': 'Image format not supported',
    'IMG-RESIZE-FAILED': 'Failed to resize image',
    'IMG-UPLOAD-FAILED': 'Image upload to platform failed',
    'IMG-NOT-FOUND': 'Image file does not exist',
    'IMG-CORRUPT': 'Image file is corrupted or unreadable',
    
    # Network (NET)
    'NET-TIMEOUT': 'Request timed out',
    'NET-CONNECTION': 'Could not connect to platform',
    'NET-DNS': 'DNS resolution failed',
    'NET-SSL': 'SSL certificate verification failed',
    
    # Post Submission (POST)
    'POST-TEXT-TOO-LONG': 'Post text exceeds character limit',
    'POST-DUPLICATE': 'Platform rejected duplicate post',
    'POST-FAILED': 'Post submission failed',
    'POST-EMPTY': 'Post text cannot be empty',
    
    # System (SYS)
    'SYS-CONFIG-MISSING': 'Configuration file not found',
    'SYS-PERMISSION': 'Insufficient file system permissions',
    'SYS-DISK-FULL': 'Disk full, cannot save logs',
    'SYS-UNKNOWN': 'Unknown system error occurred',
}
```

### User-Friendly Messages
Each error code maps to conversational explanation:
- `TW-RATE-LIMIT` → "Twitter says you're posting too fast. Try again in about 15 minutes."
- `BS-AUTH-EXPIRED` → "Your Bluesky session expired. Click 'Open Settings' to reconnect."
- `IMG-TOO-LARGE` → "This image is too big for [Platform]. The app will resize it automatically."

---

## Authentication

### File Format (Reuses Existing Pattern)

**twitter_auth.json:**
```json
{
    "api_key": "your_api_key_here",
    "api_secret": "your_api_secret_here",
    "access_token": "your_access_token_here",
    "access_token_secret": "your_access_token_secret_here"
}
```

**bluesky_auth.json:**
```json
{
    "identifier": "username.bsky.social",
    "app_password": "xxxx-xxxx-xxxx-xxxx",
    "service": "https://bsky.social"
}
```

### Storage Locations
- Development: Same directory as executable
- Production: `%APPDATA%/GaleFling/auth/`
- Credentials also stored in Windows Credential Manager via `keyring` for security
- Setup wizard creates these files on first run

---

## Application Configuration

**app_config.json:**
```json
{
    "version": "0.2.0",
    "last_selected_platforms": ["twitter", "bluesky"],
    "debug_mode": false,
    "auto_check_updates": true,
    "theme_mode": "system",
    "log_upload_endpoint": "https://galepost.jasmer.tools/logs/upload",
    "log_upload_enabled": true,
    "window_geometry": {
        "width": 900,
        "height": 700,
        "x": 100,
        "y": 100
    },
    "last_image_directory": "",
    "auto_save_draft": true,
    "draft_auto_save_interval_seconds": 30
}
```

---

## Image Processing

### Requirements Per Platform
- Twitter: Max 4096x4096, 5MB, formats: JPEG/PNG/GIF/WEBP
- Bluesky: Max 2000x2000, 1MB, formats: JPEG/PNG

### Processing Pipeline
1. User selects image
2. Load with PIL, convert RGBA → RGB if needed
3. For each enabled platform:
   - Calculate target dimensions (maintain aspect ratio)
   - Resize using LANCZOS resampling
   - Compress iteratively to meet file size limit
   - Generate preview thumbnail for UI tab
4. Display tabbed previews showing original vs. processed

### Resize Algorithm
```
1. Load image
2. Convert RGBA → RGB (white background)
3. Calculate aspect ratio
4. Scale to fit max_dimensions (preserve ratio)
5. Compress with quality=95
6. While size > max_size_mb and quality > 20:
   - Reduce quality by 5
   - Re-compress
7. If still too large:
   - Reduce dimensions by 10%
   - Repeat until acceptable or scale < 30%
8. If cannot compress: raise IMG-RESIZE-FAILED
```

### Preview Tab Display
- QTabWidget with one tab per enabled platform
- Each tab shows:
  - Platform name + color accent
  - Target dimensions
  - Compressed file size
  - Visual thumbnail (400x400 max)
  - Status: ✓ Meets requirements or ⚠ Warning
- Lazy loading: generate preview only when tab clicked

---

## Bluesky Link Facets

### Purpose
Make URLs clickable in Bluesky posts (required by platform)

### Implementation
```python
def detect_urls(text: str) -> List[Dict]:
    """
    Find all HTTP(S) URLs in text and create facet objects.
    
    CRITICAL: Facets use UTF-8 byte offsets, not character positions!
    
    Returns list of facet dicts for atproto API.
    """
    
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    
    facets = []
    for match in re.finditer(url_pattern, text):
        # Calculate byte positions (UTF-8 encoded)
        byte_start = len(text[:match.start()].encode('utf-8'))
        byte_end = len(text[:match.end()].encode('utf-8'))
        
        facets.append({
            "index": {
                "byteStart": byte_start,
                "byteEnd": byte_end
            },
            "features": [{
                "$type": "app.bsky.richtext.facet#link",
                "uri": match.group(0)
            }]
        })
    
    return facets
```

### Example Facet
```json
{
    "index": {
        "byteStart": 25,
        "byteEnd": 50
    },
    "features": [{
        "$type": "app.bsky.richtext.facet#link",
        "uri": "https://rin-city.com/sets/example"
    }]
}
```

---

## Logging System

### Log Directory Structure
```
logs/
├── app_20260213_142345.log          # Timestamped log files
├── app_20260213_150122.log          # Each session creates new log
└── screenshots/
    ├── error_20260213_142401.png    # Auto-captured on errors
    └── error_20260213_150205.png
```

### Log Entry Format
```
2026-02-13 14:23:45,123 - GaleFling - ERROR - Error TW-AUTH-EXPIRED on Twitter
{
    "error_code": "TW-AUTH-EXPIRED",
    "platform": "Twitter",
    "timestamp": "2026-02-13T14:23:45.123456",
    "details": {
        "request": "POST /2/tweets",
        "response_code": 401,
        "user_text_length": 145,
        "image_attached": true,
        "image_original_size": "4000x6000 (3.2MB)",
        "image_processed_size": "4096x4096 (2.8MB)"
    },
    "exception": {
        "type": "HTTPError",
        "message": "401 Unauthorized",
        "traceback": "..."
    }
}
```

### Screenshot Capture
- Automatically capture on ANY error
- Save to `logs/screenshots/error_TIMESTAMP.png`
- Include in log upload bundle
- Shows exact UI state when error occurred

---

## Log Upload to Endpoint

### Recommended: AWS Lambda + API Gateway

**Why Not SMTP:**
- Requires embedding credentials in app (security risk)
- Complex for Rin to configure
- Email provider restrictions

**Why Lambda:**
- No credentials in app
- Single endpoint URL
- You control backend
- Can add rate limiting
- Simple for Rin (one button click)

### Endpoint Specification

**URL:** `POST https://galepost.jasmer.tools/logs/upload`

**Request Body:**
```json
{
    "app_version": "0.2.0",
    "timestamp": "2026-02-13T14:23:45",
    "error_code": "BS-AUTH-EXPIRED",
    "user_id": "rin_installation_uuid",
    "user_notes": "what the user was doing",
    "os_platform": "Windows-11-10.0.26100-SP0",
    "log_files": [
        {
            "filename": "app_20260213_142345.log",
            "content": "base64_encoded_log_data"
        }
    ],
    "screenshots": [
        {
            "filename": "error_20260213_142401.png",
            "content": "base64_encoded_image_data"
        }
    ]
}
```

**Response:**
```json
{
    "success": true,
    "upload_id": "abc123-def456",
    "message": "Logs uploaded successfully"
}
```

### Lambda Function Pseudocode
```python
def lambda_handler(event, context):
    """
    1. Receive logs from app
    2. Send email to morgan@windsofstorm.net via SES (attachments preferred)
    3. Return success response
    """
    
    body = json.loads(event['body'])
    upload_id = generate_unique_id()
    
    # Email via SES
    ses.send_email(
        Source='noreply@example.com',
        Destination={'ToAddresses': ['morgan@windsofstorm.net']},
        Message={
            'Subject': f"Error Report: {body['error_code']}",
            'Body': f"Upload ID: {upload_id}\nOS Platform: {body['os_platform']}\n..."
        }
    )
    
    return {'statusCode': 200, 'body': json.dumps({'success': True})}
```

**Alternative: GitHub Issues**
- Use GitHub API to create issue
- Attach logs as comment
- Advantage: Centralized tracking, can respond/close
- Disadvantage: Logs are public (unless private repo)

---

## Auto-Update System

### Workflow
1. On app startup (if enabled in settings)
2. Call GitHub API: `GET https://api.github.com/repos/{owner}/{repo}/releases/latest`
3. Parse `tag_name` (e.g., "v0.2.0")
4. Compare with current version (0.1.0)
5. If newer: show non-blocking notification
6. User clicks "Download" → opens browser to release page

### Version Comparison
Use `packaging.version.parse()`:
- Handles semantic versioning: 0.1.0 < 0.2.0 < 1.0.0
- Supports pre-releases: 0.1.0-beta < 0.1.0

### GitHub API Response
```json
{
    "tag_name": "v0.2.0",
    "name": "Version 0.2.0 - Bug Fixes",
    "body": "- Fixed Twitter auth\n- Improved error messages",
    "assets": [
        {
            "name": "GaleFling-Setup-0.2.0.exe",
            "browser_download_url": "https://github.com/.../GaleFling-Setup-0.2.0.exe"
        }
    ]
}
```

### Update Notification UI
```
┌────────────────────────────────────────────────┐
│ 🎉 New Version Available!                      │
├────────────────────────────────────────────────┤
│ Version 0.2.0 is now available.                │
│ You're currently using 0.1.0.                  │
│                                                 │
│ [Download]  [Skip This Version]  [Remind Later]│
└────────────────────────────────────────────────┘
```

---

## Draft Auto-Save

### Purpose
Prevent data loss if app crashes or Rin closes accidentally

### Implementation
- Auto-save draft every 30 seconds (configurable)
- Save location: `%APPDATA%/GaleFling/drafts/current_draft.json`
- On app restart: prompt "Restore unsaved draft?"

### Draft File Format
```json
{
    "text": "Check out my new set! 🔥\nhttps://rin-city.com/sets/example",
    "image_path": "C:/Users/Rin/Pictures/set_cover.jpg",
    "selected_platforms": ["twitter", "bluesky"],
    "timestamp": "2026-02-13T14:23:45",
    "auto_saved": true
}
```

### Restore Prompt
```
┌────────────────────────────────────────────────┐
│ Unsaved Draft Found                            │
├────────────────────────────────────────────────┤
│ You have an unsaved draft from 5 minutes ago.  │
│                                                 │
│ "Check out my new set! 🔥..."                  │
│                                                 │
│ [Restore Draft]         [Discard]              │
└────────────────────────────────────────────────┘
```

---

## GUI Wireframes

### Main Window
```
┌────────────────────────────────────────────────────────────────┐
│ GaleFling v0.2.0                              [─] [□] [×]        │
├────────────────────────────────────────────────────────────────┤
│ File   Settings   Help                                         │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  📝 Post Text:                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Check out my new set! 🔥                                 │  │
│  │ https://rin-city.com/sets/steampunk-goddess              │  │
│  │                                                            │  │
│  │                                                            │  │
│  └──────────────────────────────────────────────────────────┘  │
│  280 characters (fits all platforms)                           │
│  ⚠ Twitter: 280 max  ✓ Bluesky: 300 max                       │
│                                                                 │
│  🖼️  Image:                                                     │
│  [Choose Image...]  [Clear]                                    │
│  📁 No image selected                                          │
│                                                                 │
│  ✅ Post to:                                                    │
│  ☑ Twitter        ☑ Bluesky                                    │
│                                                                 │
│  ──────────────────────────────────────────────────────────    │
│                                                                 │
│              [Test Connections]      [Post Now]                │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

### Image Preview Tabs Dialog
```
┌────────────────────────────────────────────────────────────────┐
│ Image Resize Preview                                    [×]    │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  📁 Original: steampunk_goddess_cover.jpg                      │
│     4000 x 6000 (3.2 MB)                                       │
│                                                                 │
│  ┌─[Twitter]─────┬─[Bluesky]────┐                             │
│  │               │               │                              │
│  │ Will resize to:                                             │
│  │ 4096 x 4096   │ 2000 x 2000   │                             │
│  │ 2.8 MB        │ 980 KB        │                             │
│  │               │               │                              │
│  │ [Thumbnail]   │ [Thumbnail]   │                             │
│  │               │               │                              │
│  │ ✓ Meets       │ ✓ Meets       │                             │
│  │ requirements  │ requirements  │                             │
│  │               │               │                              │
│  └───────────────┴───────────────┘                             │
│                                                                 │
│  ℹ️  Images are automatically optimized for each platform.     │
│     Aspect ratios are preserved.                               │
│                                                                 │
│                              [OK]                               │
└────────────────────────────────────────────────────────────────┘
```

**Tab Implementation:**
- QTabWidget with platform-specific tabs
- Tabs only show for ENABLED platforms
- Lazy load: generate preview when tab clicked
- Color accent border matching platform color

### Results Dialog (Success)
```
┌────────────────────────────────────────────────────────────────┐
│ Post Results                                            [×]    │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ✓ Twitter - Posted successfully!                              │
│    🔗 https://twitter.com/rinthemodel/status/123456789         │
│       [Copy Link]                                              │
│                                                                 │
│  ✓ Bluesky - Posted successfully!                              │
│    🔗 https://bsky.app/profile/rin.bsky.social/post/abc123     │
│       [Copy Link]                                              │
│                                                                 │
│  ──────────────────────────────────────────────────────────    │
│                                                                 │
│                    [Copy All Links]    [Close]                 │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

**CRITICAL:** 
- URLs must be CLICKABLE (QLabel with openExternalLinks=True)
- Copy buttons use QApplication.clipboard()
- "Copy All Links" format:
  ```
  Twitter: https://twitter.com/...
  Bluesky: https://bsky.app/...
  ```

### Results Dialog (Partial Failure)
```
┌────────────────────────────────────────────────────────────────┐
│ Post Results                                            [×]    │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ✓ Twitter - Posted successfully!                              │
│    🔗 https://twitter.com/rinthemodel/status/123456789         │
│       [Copy Link]                                              │
│                                                                 │
│  ❌ Bluesky - Failed to post                                    │
│     Your Bluesky session expired. Please reconnect your        │
│     account in Settings.                                       │
│                                                                 │
│     Error Code: BS-AUTH-EXPIRED                                │
│     Time: 2026-02-13 14:23:45                                  │
│                                                                 │
│     [Copy Error Details]  [Retry]  [Open Settings]             │
│                                                                 │
│  ──────────────────────────────────────────────────────────    │
│                                                                 │
│  [Send Logs to Jas]                [Close]                     │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

**Error Details Copy Format:**
```
Platform: Bluesky
Error Code: BS-AUTH-EXPIRED
Timestamp: 2026-02-13 14:23:45
Message: Your Bluesky session expired. Please reconnect your account in Settings.

Request Details:
POST https://bsky.social/xrpc/com.atproto.repo.createRecord
Response: 401 Unauthorized

Application: GaleFling v0.2.0
Log File: app_20260213_142345.log
Screenshot: error_20260213_142401.png
```

### Setup Wizard (First Run)

**Welcome:**
```
┌────────────────────────────────────────────────────────────────┐
│ Welcome to GaleFling!                                   [×]    │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Let's get you set up to post to Twitter and Bluesky!         │
│                                                                 │
│  We'll need your account credentials for each platform.        │
│  Don't worry - they're stored securely on your computer.       │
│                                                                 │
│  This should only take a minute.                               │
│                                                                 │
│                                                                 │
│                                                                 │
│                                       [Get Started]            │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

**Twitter Setup:**
```
┌────────────────────────────────────────────────────────────────┐
│ Setup - Twitter                               (Step 1 of 2)    │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Twitter API Credentials                                       │
│                                                                 │
│  API Key:                                                       │
│  [_________________________________________________________]   │
│                                                                 │
│  API Secret:                                                    │
│  [_________________________________________________________]   │
│                                                                 │
│  Access Token:                                                  │
│  [_________________________________________________________]   │
│                                                                 │
│  Access Token Secret:                                           │
│  [_________________________________________________________]   │
│                                                                 │
│  [Test Connection]                      ℹ️ How to get these    │
│                                                                 │
│  ──────────────────────────────────────────────────────────    │
│                                                                 │
│  [Skip]                                         [Next >]       │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

**Bluesky Setup:**
```
┌────────────────────────────────────────────────────────────────┐
│ Setup - Bluesky                               (Step 2 of 2)    │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Bluesky Account                                               │
│                                                                 │
│  Username (handle):                                            │
│  [_________________________________________________________]   │
│  Example: yourname.bsky.social                                 │
│                                                                 │
│  App Password:                                                  │
│  [_________________________________________________________]   │
│  Format: xxxx-xxxx-xxxx-xxxx                                   │
│                                                                 │
│  [Test Connection]                      ℹ️ How to get these    │
│                                                                 │
│  ──────────────────────────────────────────────────────────    │
│                                                                 │
│  [< Back]  [Skip]                               [Finish]       │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

---

## Dependencies

### requirements.txt
```
PyQt5>=5.15.10
tweepy>=4.14.0
atproto>=0.0.50
Pillow>=10.2.0
keyring>=25.0.0
requests>=2.31.0
packaging>=24.0
python-dotenv>=1.0.0
```

### requirements-dev.txt
```
pytest>=8.0.0
pytest-qt>=4.3.0
pytest-cov>=4.1.0
ruff>=0.8.0
mypy>=1.8.0
pyinstaller>=6.3.0
```

---

## Build Process

### Development
```bash
# Setup
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run
python src/main.py

# Test
make test

# Lint & format
make lint
make lint-fix
```

### Production Build
```bash
# Build executable
pyinstaller build/build.spec

# Output: dist/GaleFling.exe

# Create installer
makensis build/installer.nsi

# Output: GaleFling-Setup-v0.2.0.exe
```

---

## Testing Checklist

### Authentication
- [ ] Twitter auth with valid credentials succeeds
- [ ] Twitter auth with invalid credentials shows TW-AUTH-INVALID
- [ ] Bluesky auth with valid credentials succeeds
- [ ] Bluesky auth with invalid credentials shows BS-AUTH-INVALID
- [ ] Test Connection button validates both platforms
- [ ] Credentials persist across app restarts
- [ ] Can reconnect expired sessions from Settings

### Image Processing
- [ ] Selecting image opens preview dialog with TABS
- [ ] Preview tabs show correct dimensions per platform
- [ ] Images > 5MB compressed for Twitter
- [ ] Images > 1MB compressed for Bluesky
- [ ] RGBA images convert to RGB
- [ ] Unsupported formats show IMG-INVALID-FORMAT
- [ ] Missing image file shows IMG-NOT-FOUND
- [ ] Preview tabs lazy-load (only when clicked)

### Posting
- [ ] Can post text-only to Twitter
- [ ] Can post text-only to Bluesky
- [ ] Can post text + image to Twitter
- [ ] Can post text + image to Bluesky
- [ ] Bluesky URLs become CLICKABLE links (facets work)
- [ ] Can post to both platforms simultaneously
- [ ] Can uncheck platform to skip it
- [ ] Platform selection persists across sessions

### Error Handling
- [ ] Network timeout shows NET-TIMEOUT
- [ ] Rate limit shows platform-specific RATE error
- [ ] Character limit exceeded shows POST-TEXT-TOO-LONG
- [ ] Auth errors show user-friendly message + code
- [ ] Copy Error Details button works
- [ ] Retry button re-attempts failed platform only
- [ ] Screenshot auto-captured on errors

### UI/UX
- [ ] URLs in results dialog are CLICKABLE
- [ ] Copy Link buttons work for individual platforms
- [ ] Copy All Links formats correctly
- [ ] Window geometry saves/restores
- [ ] Character counter updates real-time
- [ ] Character counter warns if exceeds platform limit
- [ ] Draft auto-saves every 30 seconds
- [ ] Can restore draft on app restart

### Logging
- [ ] Log files created in logs/ directory
- [ ] Errors logged with full context
- [ ] Screenshots saved to logs/screenshots/
- [ ] Send Logs to Jas button uploads to endpoint
- [ ] Debug mode shows additional details

### Auto-Update
- [ ] Update check on startup (if enabled)
- [ ] Compares versions correctly (0.1.0 < 0.2.0)
- [ ] Shows notification if update available
- [ ] Opens browser to GitHub releases

### Setup Wizard
- [ ] Shows on first run
- [ ] Can skip platforms
- [ ] Test Connection validates before proceeding
- [ ] Saves credentials securely

---

## Deployment

### GitHub Repository
```
jasmeralia/galefling/
├── .github/workflows/release.yml  # Draft release on tag push
├── src/                           # Source code
├── resources/                     # Icons, configs
├── build/                         # Build scripts
├── tests/                         # Test suite
├── infrastructure/                # AWS CloudFormation + Lambda
├── README.md
├── LICENSE.md
├── CHANGELOG.md
└── requirements.txt
```

### Releases
- Phase 0: v0.1.x
- Phase 1: v0.2.x (multi-platform)
- Phase 2: v0.3.x (video)
- Stable: v1.0.0

### Release Assets
- `GaleFling-Setup-v0.2.0.exe` (installer)
- `GaleFling-0.2.0-portable.zip` (no install needed)

---

## Configuration Needed Before Start

### Questions to Resolve:

1. **GitHub repo name:**
   - Repo: `jasmeralia/galefling`

2. **Log upload endpoint:**
   - Lambda + API Gateway deployed via CloudFormation
   - Endpoint URL: `https://galepost.jasmer.tools/logs/upload`

3. **App icon:**
   - Need 256x256 PNG
   - Windows .ico file
   - Can be simple or Rin's branding

4. **Email for log uploads:**
   - Confirmed: morgan@windsofstorm.net

5. **Error handling behavior:**
   - Should failed platforms block others?
   - Recommendation: Always try all enabled platforms

---

## Next Implementation Steps

1. Create base platform interface (`platforms/base.py`)
2. Implement Twitter platform (reuse throwback script patterns)
3. Implement Bluesky platform (with link facets)
4. Build main window with text input + platform checkboxes
5. Add image selection with tabbed preview dialog
6. Wire up posting logic
7. Implement error handling system
8. Add logging and screenshot capture
9. Create log upload functionality
10. Build setup wizard
11. Add auto-update checker
12. Package with PyInstaller
13. Test with Rin

---

## Phase 1 Preview (For Later)

### Additional Platforms
- SuicideGirls (confirmed)
- Others TBD based on Rin's list

### Enhanced Features
- Multiple images per post (carousel/gallery)
- Platform-specific text (tabs for different captions)
- Hashtag management
- Scheduled posting (optional)

### Platform Research Template
For each new platform:
```python
PLATFORM_SPECS = {
    'name': 'PlatformName',
    'max_images': 4,  # or 1
    'max_image_dimensions': (w, h),
    'max_file_size_mb': float,
    'supported_formats': ['JPEG', 'PNG'],
    'max_text_length': int,
    'api_type': 'official' | 'unofficial' | 'scraping',
    'auth_method': 'oauth' | 'api_key' | 'username_password',
    'api_docs': 'url',
    'rate_limits': {...},
    'special_requirements': []
}
```

---

## Phase 2 Preview (For Later)

### Video Support
- Single video per post (XOR image)
- Platform-specific encoding (FFmpeg)
- Chunk-based uploads for large files
- Progress bars
- Video preview/thumbnail

### macOS Build
- Add a macOS GitHub Actions job to produce a `.app` bundle

---

## Important Notes

### Critical Design Decisions
1. **Tabbed image previews** - scales better than side-by-side for 5+ platforms
2. **Clickable URLs in results** - not just copy buttons
3. **Log upload to endpoint** - not SMTP (security + simplicity)
4. **Error codes for you** - user messages for Rin
5. **Reuse auth file format** - matches throwback script

### User Experience Priorities
1. Simple and guided (non-technical user)
2. Clear error messages
3. Remote troubleshooting (logs + screenshots)
4. No data loss (auto-save drafts)
5. Platform failures don't break others

### Development Priorities
1. Get Twitter + Bluesky working first
2. Robust error handling
3. Thorough testing with Rin
4. Phase 1 platforms incrementally
5. Video support last

---

## Release Checklist (ALWAYS follow on every update)

Every change that modifies functionality, fixes bugs, or alters configuration **must**:

1. **Bump the version** in all locations:
   - `src/utils/constants.py` → `APP_VERSION`
   - `resources/default_config.json` → `"version"`
   - `build/version_info.txt` → `filevers`, `prodvers`, `FileVersion`, `ProductVersion`
   - `build/installer.nsi` → `OutFile` and registry `Version`/`DisplayVersion`
   - `README.md` → `Current Version` line and the example `git tag` / `git push` commands
2. **Add a CHANGELOG.md entry** under a new `## [x.y.z]` heading with the date and changes
3. **Update README.md** if the change affects features, project structure, or usage instructions
4. **Run lint + format checks using the venv**: `source venv/bin/activate && make lint`  
   - Any new scripts should be included in linting when possible.
5. **Run tests using the venv (after lint, before commit)**: `source venv/bin/activate && make test`  
   - Add or update tests for new scripts when possible.
6. **Git workflow:** Use a verbose commit message (short header line, blank line, then the same bullet notes used in `CHANGELOG.md`). Prefer `scripts/commit_with_changelog_notes.sh "Header"` to avoid shell interpolation issues. Commit the changes, create a version tag, and push both commit and tag to GitHub.

Use semantic versioning in `major.minor.build` format. **Only increment the build number** unless explicitly told otherwise.

Phase versioning:
1. **Phase 0:** `0.x.y`
2. **Phase 1:** `1.x.y`
3. **Phase 2:** `2.x.y`
4. **Phase N:** `N.x.y`

## Tooling

- **Linting & formatting:** ruff (configured in `pyproject.toml`). Run `make lint` / `make lint-fix`.
- **Testing:** pytest. Run `make test`.
- **Building:** PyInstaller via `make build`, NSIS installer via `make installer`.
- **CI/CD:** GitHub Actions creates draft releases on tag push (`.github/workflows/release.yml`).

## Log Upload Endpoint

- **URL:** `https://galepost.jasmer.tools/logs/upload`
- **Infrastructure:** CloudFormation stack in `infrastructure/template.yaml`
- **Sender email:** `morgan@windsofstorm.net` (SES)
- **Recipient email:** `morgan@windsofstorm.net`

---

End of GaleFling Phase 0 Context File
