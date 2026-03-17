# Functional Tests

Functional tests exercise real platform APIs with real credentials. They are **local-only** — never run in CI — because they require secrets and active test accounts.

## Quick Start

```bash
# 1. Copy the example env and fill in your credentials
cp tests/functional/.env.example tests/functional/.env

# 2. Edit tests/functional/.env with your real values

# 3. Run the functional tests
make test-functional PYTHON=.venv/bin/python
```

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

### Skipping Unconfigured Platforms

Tests automatically **skip** when their credentials are absent — you only need to configure the platforms you want to test. Running with no `.env` at all will skip all platform API tests (media processing tests still run).

## Running Tests

```bash
# All functional tests
make test-functional PYTHON=.venv/bin/python

# Specific platform only
.venv/bin/python -m pytest tests/functional/test_bluesky_post.py -m functional -v

# Media processing only (no credentials needed)
.venv/bin/python -m pytest tests/functional/test_media_processing.py -m functional -v
```

## Test Structure

```
tests/functional/
├── conftest.py                  # Credential loading, skip-if-missing fixtures, media fixtures
├── .env.example                 # Template showing required vars (committed)
├── .env                         # Actual credentials (gitignored)
├── test_bluesky_post.py         # Bluesky: auth, text, image, video, char limit
├── test_twitter_post.py         # Twitter: auth, text, image, video, char limit
├── test_instagram_post.py       # Instagram: auth, image post (3-step workflow)
└── test_media_processing.py     # Image/video processing (no credentials needed)
```

### Test Ordering

Each platform test module starts with a `TestXxxConnection` class that validates authentication before any posting tests run. If connection tests fail, you know immediately that the credentials are wrong — no need to debug post failures.

### Post Cleanup

Every test that creates a post **deletes it in the same test** to avoid polluting test accounts. Tests use UUID tags in post text to avoid duplicate-post rejections.

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

## CI Integration

Functional tests are **excluded from CI** via the `functional` pytest marker:

- `pyproject.toml` defines the marker
- CI workflows pass `-m "not functional"` to pytest
- `make test-cov` also excludes functional tests by default
- `make test-functional` is the dedicated target for local runs
