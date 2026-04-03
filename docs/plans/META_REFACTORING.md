# Meta Posting Context for GaleFling

## Goal

Implement posting support for these Meta surfaces:
- Threads timeline posting for **1–2 Threads accounts**
- Instagram feed posting for **1–2 Instagram accounts** (**feed only, not Stories**)
- Facebook posting for **1 Facebook Page**

This document is meant to give an implementation-oriented overview of:
1. which APIs to use and which app registrations are needed,
2. what credentials/tokens are needed,
3. how to obtain them,
4. how to model them in the app,
5. how app credentials are distributed to users,
6. how media is staged to S3 for Instagram and Threads publishing,
7. which legacy WebView code must be removed,
8. what test coverage is required,
9. which integration points must be wired before the plan is considered complete.

---

## Architectural decisions

### One app per platform

GaleFling uses **three separate Meta app registrations**, one per platform:

- **GaleFling Threads** — Threads API only
- **GaleFling Instagram** — Instagram Platform (Instagram Login path) only
- **GaleFling Facebook** — Facebook Pages API only

This approach was chosen because:
- The Instagram Login and Facebook Login auth paths are mutually exclusive within a single app
- Isolation: a restriction on one app registration does not affect the other platforms
- GaleFling is a private tool used by a small number of known users; App Review is never
  required, and the added credential management overhead of three apps is negligible at
  this scale

Each app operates in **development mode** indefinitely. No App Review, no Business
Verification, no Tech Provider verification is needed.

### Credential distribution model

GaleFling does **not** embed Meta app credentials in the open source codebase. Instead:

- The app owner (you) registers the three Meta apps and holds the credentials
- GaleFling exposes an **advanced settings JSON import** for app-level credentials
- For trusted users such as Rin, you provide a pre-configured JSON file to import
- Other open source users who want Meta platform support register their own apps and
  import their own credentials

This keeps the codebase clean and avoids any App Review obligation tied to credential
embedding.

### Internal provider model

Treat each connected surface as a separate account connection:

- `meta_threads`
- `meta_instagram`
- `meta_facebook_page`

Do **not** assume one token can be used interchangeably across platforms. Meta's platform
is shared infrastructure, but permissions, token types, and base URLs are all
product-specific.

### Media staging via S3

Instagram and Threads do not accept binary file uploads in the API payload. Instead,
Meta's servers fetch media directly from a publicly accessible URL at publish time.
GaleFling must upload media to S3 before making the publish API call, pass the resulting
public URL to the API, and may clean up the S3 object after confirmed publication.

Facebook Pages does not have this constraint — its `/photos` endpoint accepts direct
binary uploads — but using S3 consistently across all three platforms is acceptable and
simplifies the publisher implementation.

A dedicated S3 bucket is used for this purpose, separate from any other GaleFling or
personal AWS infrastructure. See the **S3 media staging** section below for bucket
configuration, lifecycle policy, and CloudFormation stack details.

---

## Platform details

### 1) Threads timeline posting

**App:** GaleFling Threads
**API:** Threads API
**Base URL:** `https://graph.threads.net/v1.0/`
**Auth path:** Threads OAuth (via `api.instagram.com/oauth/authorize` with Threads scopes)

Relevant capabilities:
- text posts (500 character limit)
- image posts (JPEG/PNG, 8 MB max, 320–1440px wide, sRGB)
- video posts (MOV/MP4, H264/HEVC, 23–60 FPS, max 1920px, max 5 min, 1 GB max)
- carousel posts (2–20 items, images and/or video mixed)

Key permissions/scopes:
- `threads_basic` — required for all Threads API calls
- `threads_content_publish` — required for publishing

Token notes:
- Threads uses **Threads user access tokens** (distinct token type from Instagram/Facebook)
- Long-lived tokens are valid for **60 days**, refreshable while still valid
- **Public profile accounts:** refreshing extends the grant another 90 days
- **Private profile accounts:** permission grant cannot be extended; user must re-auth after
  expiry — surface this clearly in GaleFling's UI

Publishing flow (two-step, same as Instagram):
1. Upload media to S3 staging bucket → get public URL (for image/video posts)
2. `POST /{user-id}/threads` with content → returns container ID
3. Wait ~30 seconds for media processing (poll status endpoint for media posts)
4. `POST /{user-id}/threads_publish` with `creation_id` → publishes
5. S3 object expires automatically via lifecycle policy within 7 days

Rate limit: 250 posts per 24-hour period per profile.

**Important:** The Threads use case generates its own app ID and app secret within the
app dashboard, separate from the main Meta app ID. Always use the **Threads-specific
app ID and secret** for Threads OAuth and token exchange, not the top-level app
credentials.

---

### 2) Instagram feed posting

**App:** GaleFling Instagram
**API:** Instagram Platform Content Publishing API (Instagram Login path)
**Base URL:** `https://graph.instagram.com/`
**Auth path:** Business Login for Instagram (Instagram credentials, no Facebook Page required)

Relevant capabilities (feed only — Stories explicitly excluded):
- single image feed posts
- single video feed posts
- carousel feed posts (up to 10 items)

Key permissions/scopes:
- `instagram_business_basic` — required baseline
- `instagram_business_content_publish` — required for publishing

Account requirement:
- Account must be a **Professional account** (Business or Creator type)
- Personal/consumer accounts are not eligible for the publishing API
- No Facebook Page link required under the Instagram Login path
- Both of Rin's accounts are confirmed Professional/Creator — no account type changes
  needed

Token notes:
- Produces **Instagram User access tokens** (not Facebook User tokens)
- Long-lived tokens valid for **60 days**, refreshable before expiry

Publishing flow (two-step container model):
1. Upload media to S3 staging bucket → get public URL
2. `POST /{ig-account-id}/media` with public S3 URL → returns container ID
3. Poll `GET /{container-id}?fields=status_code` until `FINISHED`
4. `POST /{ig-account-id}/media_publish` with `creation_id` → publishes
5. S3 object expires automatically via lifecycle policy within 7 days

Media must be hosted on a publicly accessible URL at the time of the publish call. Meta
cURL-fetches it directly from S3 — the object must be publicly readable at that moment.
See the **S3 media staging** section for bucket and IAM configuration.

Rate limit: 100 API-published posts per 24-hour moving period.

---

### 3) Facebook Page posting

**App:** GaleFling Facebook
**API:** Facebook Pages API / Graph API for Pages
**Base URL:** `https://graph.facebook.com/`
**Auth path:** Facebook Login for Business (Facebook credentials)

Relevant capabilities:
- text/link posts
- photo posts
- video posts

Key permissions/scopes:
- `pages_manage_metadata` — required
- `pages_manage_posts` — required for publishing
- `pages_read_engagement` — required
- `pages_show_list` — required to enumerate Pages
- `pages_manage_engagement` — required for photo posts
- `publish_video` — required for video posts

Token model (two-token chain — most complex of the three):
1. Facebook Login OAuth → **Facebook User access token** (60 days, long-lived)
2. `GET /me/accounts` → returns list of Pages with embedded short-lived Page tokens
3. Exchange each Page token for a **long-lived Page access token** (effectively permanent
   as long as permissions are not revoked)

Store the long-lived Page access token — this does not require periodic refresh the way
Instagram and Threads tokens do, making it the lowest-maintenance token of the three at
runtime.

Publishing flow (single API call — simplest of the three):
- Text/link: `POST /{page-id}/feed` with `message` and optional `link`
- Photo: `POST /{page-id}/photos` with `url`
- No container model, no processing wait, no polling required

If the user manages multiple Pages, GaleFling should present the list returned by
`/me/accounts` and let the user select which Page(s) to enable, rather than
auto-enabling all of them.

---

## Setting up the three Meta apps

### Prerequisites

- A Meta developer account at developers.facebook.com
- For each app: the app will operate in development mode; no business portfolio or
  business verification is required

---

### App 1: GaleFling Threads

1. Go to developers.facebook.com → Create App
2. App name: `GaleFling Threads` (or similar)
3. Select use case: **Access the Threads API**
4. Skip business portfolio connection (not required for development mode)
5. In the app dashboard, go to **Use Cases → Customize → Threads**
6. Add permissions:
   - `threads_basic` (required, added by default)
   - `threads_content_publish`
7. Go to **Use Cases → Customize → Settings**
   - Note the **Threads App ID** and **Threads App Secret** (these are separate from
     the main app ID/secret — use these for all Threads OAuth)
   - Add OAuth redirect URIs (see Redirect URI section below)
   - Add Deauthorize Callback URL and Data Deletion Request URL (can be placeholder
     URLs for private use)
8. Add Rin as a Threads Tester:
   - Go to **App Roles → Roles → Add People**
   - Select **Threads Tester**
   - Enter her Threads username
   - She must accept the invitation from **Threads app → Settings → Account →
     Website permissions**

Credentials to extract for the JSON import file:
- `threads_app_id` (from Threads use case settings, NOT the top-level app ID)
- `threads_app_secret` (from Threads use case settings, NOT the top-level app secret)

---

### App 2: GaleFling Instagram

1. Go to developers.facebook.com → Create App
2. App name: `GaleFling Instagram` (or similar)
3. Select use case: **Manage messaging & content on Instagram**
4. Skip business portfolio connection
5. In the app dashboard, go to **Use Cases → Customize → Instagram**
6. Select **API setup with Instagram Login** (not Facebook Login — this is the
   Instagram Login path)
7. Add permissions:
   - `instagram_business_basic` (required, added by default)
   - `instagram_business_content_publish`
8. In **Business Login Settings**:
   - Add OAuth redirect URIs (see Redirect URI section below)
   - Add Deauthorize Callback URL and Data Deletion Request URL
9. Add Instagram accounts for testing:
   - Go to **App Roles → Roles → Add People** or use the account addition flow in
     the Instagram use case settings
   - Add both of Rin's Instagram accounts as testers
   - She must accept via Instagram app settings

Note the **Instagram App ID** and **Instagram App Secret** from the Instagram use case
settings page (distinct from the top-level app credentials).

Credentials to extract for the JSON import file:
- `instagram_app_id`
- `instagram_app_secret`

---

### App 3: GaleFling Facebook

1. Go to developers.facebook.com → Create App
2. App name: `GaleFling Facebook` (or similar)
3. Select use case: **Manage everything on your Page**
4. Skip business portfolio connection
5. In the app dashboard, go to **Use Cases → Customize**
6. Add permissions:
   - `pages_manage_metadata`
   - `pages_manage_posts`
   - `pages_read_engagement`
   - `pages_show_list`
   - `pages_manage_engagement`
   - `publish_video` (if video posting to Pages is desired)
7. Configure Facebook Login for Business:
   - Add OAuth redirect URIs (see Redirect URI section below)
8. Add Rin as a tester/developer on the app so she can authorize in development mode:
   - Go to **App Roles → Roles → Add People**
   - Add her Facebook account as a Tester or Developer

Credentials to extract for the JSON import file:
- `facebook_app_id` (top-level app ID)
- `facebook_app_secret` (top-level app secret)

---

## OAuth redirect URIs and localhost callback handling

### Strategy

GaleFling uses **localhost HTTP redirect** for OAuth callbacks. This avoids the custom
URI scheme approach (`galefling://`) which triggers browser permission prompts that can
confuse non-technical users. With localhost redirects the browser silently navigates to
a local URL with no prompts.

### Port handling

GaleFling spins up a temporary local HTTP server immediately before launching an OAuth
flow, captures the callback, then shuts the server down. To handle potential port
conflicts, GaleFling tries a small range of ports sequentially:

```python
import socket

def find_free_port(start=8765, end=8770):
    for port in range(start, end):
        with socket.socket() as s:
            try:
                s.bind(('localhost', port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free ports available in range")
```

The redirect URI is constructed dynamically from whichever port is free before the
OAuth flow begins.

### Registering redirect URIs in Meta app dashboards

Because the port is dynamic, register all ports in the range as valid redirect URIs in
each app dashboard. Add the following to each of the three apps:

```
http://localhost:8765/oauth/callback
http://localhost:8766/oauth/callback
http://localhost:8767/oauth/callback
http://localhost:8768/oauth/callback
http://localhost:8769/oauth/callback
http://localhost:8770/oauth/callback
```

Meta allows multiple redirect URIs per app. This is a one-time setup step. The same URI
list can be used across all three apps — there is no conflict risk since the temporary
server only lives for the duration of a single OAuth flow.

### User experience

After authorizing in the browser, the user sees a simple "You can close this tab"
page served by GaleFling's temporary local server. GaleFling has already received the
auth code at that point and the server shuts down. No unexpected prompts, no custom
protocol dialogs.

---

## Credential JSON import format

GaleFling exposes an advanced settings option to import Meta (and Twitter/X) app-level
credentials from a JSON file. This is the mechanism for distributing credentials to
trusted users like Rin without embedding them in the codebase.

### JSON format

```json
{
  "version": 1,
  "meta": {
    "threads": {
      "app_id": "...",
      "app_secret": "..."
    },
    "instagram": {
      "app_id": "...",
      "app_secret": "..."
    },
    "facebook": {
      "app_id": "...",
      "app_secret": "..."
    }
  },
  "twitter": {
    "client_id": "...",
    "client_secret": "..."
  },
  "aws": {
    "access_key_id": "...",
    "secret_access_key": "...",
    "region": "us-west-2",
    "media_staging_bucket": "..."
  }
}
```

Notes:
- The Twitter `client_id` and `client_secret` are the **app-level OAuth 2.0 credentials**
  registered in the Twitter developer portal. These are what enable GaleFling to initiate
  the PIN-based auth flow — they are not the per-account tokens that result from it.
  Per-account tokens are obtained and stored separately after the user completes the PIN
  flow. Without these app credentials imported, Twitter PIN login cannot be initiated at
  all.
- Partial imports are valid — only include platforms that are configured
- The `version` field allows future schema migrations
- After import, credentials are stored in GaleFling's secure credential store
  (e.g. Windows Credential Manager via `keyring`) and the JSON file can be deleted
- Raw credentials are never written to disk by GaleFling after import
- To rotate credentials (e.g. if an app secret is regenerated), provide a new JSON
  file to import

### Credentials extracted per app

For the JSON file you provide to Rin:

| Platform | Field | Where to find it |
|---|---|---|
| Threads | `app_id` | App dashboard → Threads use case → Settings → Threads App ID |
| Threads | `app_secret` | App dashboard → Threads use case → Settings → Threads App Secret |
| Instagram | `app_id` | App dashboard → Instagram use case → Settings → Instagram App ID |
| Instagram | `app_secret` | App dashboard → Instagram use case → Settings → Instagram App Secret |
| Facebook | `app_id` | App dashboard → top-level App ID |
| Facebook | `app_secret` | App dashboard → App Settings → Basic → App Secret |
| AWS | `access_key_id` | IAM console → GaleFling media staging user → Security credentials |
| AWS | `secret_access_key` | IAM console → GaleFling media staging user → Security credentials |
| AWS | `media_staging_bucket` | The bucket name chosen when deploying the CloudFormation stack |

---

## S3 media staging

### Why it's needed

Instagram and Threads require media to be hosted at a publicly accessible URL at publish
time — they do not accept binary uploads in the API payload. GaleFling uploads media to
a dedicated S3 bucket, passes the public URL to the API, then either deletes the object
after confirmed publication or relies on the bucket lifecycle policy to clean it up
within a week.

Facebook Pages does not have this constraint (its `/photos` endpoint accepts multipart
binary uploads), but routing all media through S3 is acceptable and keeps the publisher
implementation uniform.

### Bucket configuration

A dedicated CloudFormation stack should be created at
`infrastructure/galefling-media-staging.yaml` with the following configuration:

**Region:** `us-west-2`

**Bucket name:** globally unique, e.g. `galefling-media-staging-<identifier>`

**Public access:**
- Block public ACLs: enabled
- Block public policy: disabled (public read is granted via bucket policy, not ACLs)
- Ignore public ACLs: enabled
- Restrict public buckets: disabled

**Bucket policy:** allow `s3:GetObject` from `*` (anonymous read) scoped to all objects
in the bucket. This is what makes the URLs Meta can fetch publicly accessible.

**Lifecycle rules:**
- Rule 1 — `DeleteStagedMedia`: expire all objects after **7 days**. This ensures the
  bucket does not grow indefinitely even if GaleFling fails to delete objects after
  successful publication.
- Rule 2 — `AbortIncompleteMultipartUploads`: abort incomplete multipart uploads after
  **1 day**. This prevents orphaned upload parts from accumulating storage costs.

**Versioning:** disabled (not needed for staging use).

**Encryption:** SSE-S3 (AES-256) at rest is fine; objects are intentionally publicly
readable so there is no benefit to KMS.

### IAM user

Create a dedicated IAM user (e.g. `galefling-media-staging`) with an attached inline
or managed policy granting only:
- `s3:PutObject` on `arn:aws:s3:::<bucket-name>/*`

Do **not** grant `s3:DeleteObject` — cleanup is handled entirely by the lifecycle policy.

Do **not** use your personal AWS credentials or the `windsofstorm` profile for this.
Generate an access key for the dedicated IAM user and include those credentials in the
JSON import file.

### Object key convention

Use a key prefix that groups staged media clearly:

```
staging/{iso-date}/{uuid}/{filename}
```

Example: `staging/2026-04-01/a3f2c1d4-…/image.jpg`

This makes lifecycle expiry predictable and makes it easy to manually inspect or clean
up the bucket if needed.

### GaleFling upload flow

For each media file destined for Instagram or Threads:
1. Generate a UUID-based key under the `staging/` prefix
2. Upload the file to S3 using the configured IAM credentials
3. Construct the public URL: `https://<bucket>.s3.us-west-2.amazonaws.com/<key>`
4. Pass that URL to the Meta publish API call
5. The lifecycle policy cleans up the object within 7 days — no explicit deletion needed

### Settings UI exposure

AWS credentials and bucket name should be configurable in GaleFling's advanced settings,
separate from the Meta/Twitter credential import. They can be included in the same JSON
import file (see **Credential JSON import format**) or entered manually in the UI. The
settings panel should show:
- AWS Access Key ID (partially masked)
- AWS Region (read-only, `us-west-2`)
- S3 Bucket Name
- A test button that performs a small upload and delete to verify credentials and bucket
  access before the user tries to publish

---

## Token storage model

### Per-connection fields

```text
connections
- id
- provider_family                 # "meta"
- provider                        # "meta_threads" | "meta_instagram" | "meta_facebook_page"
- external_account_id             # platform-specific user/page ID
- external_account_name           # display name for UI
- access_token_encrypted
- refresh_token_encrypted         # not applicable for most Meta flows
- token_expires_at                # null for long-lived Page tokens
- granted_scopes_json
- status                          # "active" | "expires_soon" | "reauth_required"
- metadata_json                   # platform-specific extras (e.g. page name, account type)
- created_at
- updated_at
```

### Expected connections for this use case

| provider | account |
|---|---|
| `meta_threads` | Jas's Threads account |
| `meta_threads` | Rin's Threads account |
| `meta_instagram` | Jas's Instagram account |
| `meta_instagram` | Rin's primary Instagram account |
| `meta_instagram` | Rin's secondary Instagram account |
| `meta_facebook_page` | the relevant Facebook Page |

### Token lifetime summary

| Platform | Token type | Lifetime | Refresh behavior |
|---|---|---|---|
| Threads | Threads user token | 60 days | Refreshable; public profiles extend grant 90 days on refresh; private profiles must re-auth |
| Instagram | Instagram user token | 60 days | Refreshable before expiry |
| Facebook Page | Page access token | Effectively permanent | No routine refresh needed; invalidated by password change or permission revocation |
| Facebook User | Facebook user token | 60 days | Needed to re-derive Page token if ever invalidated |

---

## Publishing flows summary

### Threads

```
# For image/video posts only — skip for text posts
PUT https://<bucket>.s3.us-west-2.amazonaws.com/staging/<date>/<uuid>/<filename>
  → public_url

POST https://graph.threads.net/v1.0/{user-id}/threads
  media_type=TEXT|IMAGE|VIDEO|CAROUSEL
  text=...
  image_url={public_url} (if IMAGE)
  → container_id

# wait / poll for media processing if IMAGE or VIDEO

POST https://graph.threads.net/v1.0/{user-id}/threads_publish
  creation_id={container_id}
  → post_id

# S3 object expires automatically via lifecycle policy within 7 days
```

### Instagram

```
# Upload media to S3 first
PUT https://<bucket>.s3.us-west-2.amazonaws.com/staging/<date>/<uuid>/<filename>
  → public_url

POST https://graph.instagram.com/{ig-account-id}/media
  image_url={public_url} (or video_url=...)
  caption=...
  → container_id

# poll GET /{container-id}?fields=status_code until FINISHED

POST https://graph.instagram.com/{ig-account-id}/media_publish
  creation_id={container_id}
  → post_id

# S3 object expires automatically via lifecycle policy within 7 days
```

### Facebook Page

```
# Text/link post
POST https://graph.facebook.com/v25.0/{page-id}/feed
  message=...
  link=... (optional)
  access_token={page_access_token}
  → post_id

# Photo post
POST https://graph.facebook.com/v25.0/{page-id}/photos
  url=...
  access_token={page_access_token}
  → photo_id, post_id
```

---

## Implementation phases

### Phase 1 — Infrastructure: S3 media staging bucket

- Create `infrastructure/galefling-media-staging.yaml` CloudFormation stack
- Deploy to `us-west-2` with lifecycle rules (7-day object expiry, 1-day multipart
  abort cleanup) and public read bucket policy
- Create dedicated IAM user with `PutObject` and `DeleteObject` only
- Generate IAM access key for inclusion in the credential JSON import file

### Phase 2 — Credential import and app config

- Implement JSON credential import in advanced settings
- Support Meta (all three platforms), Twitter, and AWS credentials in one import
- Store all imported credentials in system keyring
- Expose AWS settings (key ID, bucket name) in advanced settings UI with a test button
- Surface per-platform connection status in settings UI (not yet connected /
  credentials missing / connected)

### Phase 3 — OAuth connect flows

Build three connect flows using the localhost callback pattern:
- Connect Threads account
- Connect Instagram account
- Connect Facebook Page

Each flow:
1. Find a free port in range
2. Start temporary local HTTP server
3. Construct redirect URI from port
4. Open Meta auth URL in system browser
5. Catch callback, extract auth code
6. Exchange code for short-lived token
7. Exchange for long-lived token
8. Store encrypted token + metadata
9. Shut down local server
10. Show "You can close this tab" page

### Phase 4 — Token lifecycle management

- Token expiry tracking and `expires_soon` / `reauth_required` status
- Proactive refresh for Threads and Instagram tokens before expiry
- Notify user when reauth is needed (especially for private Threads profiles)

### Phase 5 — S3 media upload layer

- Implement `MediaStager` component: upload file → return public URL
- Integrate into the publish pipeline: upload before API call
- Handle upload failures gracefully (do not attempt Meta publish if S3 upload failed)
- No explicit cleanup needed; lifecycle policy handles expiry

### Phase 6 — API platform adapters

Implement publishing adapters for:
- `src/platforms/meta_threads.py` — `MetaThreadsPlatform` (text, image, video, carousel)
- `src/platforms/meta_facebook_page.py` — `MetaFacebookPagePlatform` (text/link, photo, video)
- Update `src/platforms/meta_instagram.py` / `instagram.py` as needed to align with the
  Instagram Login path and `META_INSTAGRAM_API_SPECS`

### Phase 7 — Remove WebView Threads implementation

The WebView-based Threads implementation is superseded by the API adapter in Phase 6.
All of the following must be removed before this plan is considered complete:

- [ ] Delete `src/platforms/threads.py` (the `ThreadsPlatform` WebView class)
- [ ] Remove the `threads` platform factory entry from `src/gui/main_window.py`
- [ ] Remove the WebView Threads setup pages and account entries from
      `src/gui/setup_wizard.py` (`ThreadsSetupPage`, `threads_1`/`threads_2` accounts)
- [ ] Remove the legacy `THREADS_SPECS` constant and `'threads'` key from
      `PLATFORM_SPECS_MAP` in `src/utils/constants.py` — `META_THREADS_API_SPECS` under
      the `'meta_threads'` key is the sole surviving Threads spec
- [ ] Remove the `threads` import and cookie domain entry from `src/gui/settings_dialog.py`
- [ ] Delete `tests/test_threads.py` (tests the removed WebView class)
- [ ] Delete `tests/functional/test_webview_threads.py` (functional WebView test)
- [ ] Update `AGENTS.md` and `docs/ARCHITECTURE_OVERVIEW.md` to remove references to
      WebView Threads

These removals should be done as a single coordinated change once the API adapter is
confirmed working end-to-end.

### Phase 8 — Destination selection

When composing a post, allow selecting one or more destination accounts
from the connected surfaces (`meta_threads`, `meta_instagram`, `meta_facebook_page`).

### Phase 9 — Wire into all integration points

The following integration points must be updated before this plan is considered complete:

**Main window (`src/gui/main_window.py`):**
- [ ] Add `meta_threads` platform factory entry (maps to `MetaThreadsPlatform`)
- [ ] Add `meta_facebook_page` platform factory entry (maps to `MetaFacebookPagePlatform`)
- [ ] Ensure both route through the API (Tier 1) posting path, not WebView

**Setup wizard (`src/gui/setup_wizard.py`):**
- [ ] Add a Meta credentials import page (links to advanced settings JSON import or
      provides inline credential entry) covering all three Meta providers
- [ ] Add account connect steps for `meta_threads` (up to 2 accounts) and
      `meta_facebook_page` (1 account) — mirrors the existing `InstagramSetupPage` pattern
- [ ] Remove the legacy WebView Threads setup pages (`threads_1`, `threads_2`)

**Settings dialog (`src/gui/settings_dialog.py`):**
- [ ] Verify the Meta tab correctly reflects connected/disconnected state for
      `meta_threads` and `meta_facebook_page` after Phase 6 adapters are in place
- [ ] Add connection test buttons for `meta_threads` and `meta_facebook_page` accounts

**Connection testing:**
- [ ] `MetaThreadsPlatform.test_connection()` calls `GET /{user-id}?fields=username`
      and returns an appropriate success/failure error code
- [ ] `MetaFacebookPagePlatform.test_connection()` calls `GET /{page-id}` with the
      long-lived Page token and returns an appropriate success/failure error code

**Composer (`src/gui/post_composer.py` or equivalent):**
- [ ] `meta_threads` accounts appear in the platform/account destination selector
- [ ] `meta_facebook_page` account appears in the platform/account destination selector
- [ ] Destination-specific validation (text length, image format) runs for both

### Phase 10 — Validation rules

Before publishing:
- [ ] Validate media format and dimensions against `META_THREADS_API_SPECS` /
      `META_FACEBOOK_PAGE_SPECS` for the respective destination
- [ ] Validate caption/text length per destination
- [ ] Validate token freshness and connection status before posting
- [ ] Check rate limit headroom where trackable (Threads: 250/day; Instagram: 100/day)

### Phase 11 — Test coverage

The following test modules must be added or updated before this plan is considered
complete.

**Unit tests — new:**
- [ ] `tests/test_meta_threads_platform.py` — covers `MetaThreadsPlatform`:
  - `authenticate()` / `test_connection()` with mocked HTTP responses (success, 401, timeout)
  - `post()` text-only path (no S3 upload)
  - `post()` image path (mocked `MediaStager.upload`, mocked container/publish calls)
  - `post()` video path (mocked polling loop)
  - carousel path
  - error code mapping (`TH-AUTH-EXPIRED`, `TH-RATE-LIMIT`, `TH-POST-FAILED`)
  - `get_specs()` returns `META_THREADS_API_SPECS`
- [ ] `tests/test_meta_facebook_page_platform.py` — covers `MetaFacebookPagePlatform`:
  - `authenticate()` / `test_connection()` with mocked HTTP responses
  - `post()` text/link path
  - `post()` photo path (mocked HTTP)
  - `post()` video path
  - error code mapping (`FB-AUTH-EXPIRED`, `FB-RATE-LIMIT`, `FB-POST-FAILED`)
  - `get_specs()` returns `META_FACEBOOK_PAGE_SPECS`

**Unit tests — updated:**
- [ ] `tests/test_threads.py` — **delete** (tests the removed WebView class; see Phase 7)
- [ ] `tests/test_auth_manager.py` — add coverage for any new per-account token storage
      added by Phase 6 adapters, if not already covered
- [ ] `tests/test_settings_dialog.py` — add assertions that `meta_threads` and
      `meta_facebook_page` sections render correctly in the Meta tab

**Functional tests — new:**
- [ ] `tests/functional/test_meta_threads_post.py` — live post to Threads API using
      real credentials from `tests/functional/.env`
- [ ] `tests/functional/test_meta_facebook_page_post.py` — live post to a Facebook
      Page using real credentials from `tests/functional/.env`

**Functional tests — retired:**
- [ ] `tests/functional/test_webview_threads.py` — delete alongside Phase 7 WebView removal

---

## Config/environment variables

Each platform uses its own set of credentials now that the one-app-per-platform
approach is in use:

```env
# Threads
META_THREADS_APP_ID=
META_THREADS_APP_SECRET=

# Instagram
META_INSTAGRAM_APP_ID=
META_INSTAGRAM_APP_SECRET=

# Facebook
META_FACEBOOK_APP_ID=
META_FACEBOOK_APP_SECRET=

# Shared redirect URI base (port appended dynamically)
META_OAUTH_REDIRECT_BASE=http://localhost
META_OAUTH_PORT_RANGE_START=8765
META_OAUTH_PORT_RANGE_END=8770

# AWS media staging
AWS_MEDIA_STAGING_ACCESS_KEY_ID=
AWS_MEDIA_STAGING_SECRET_ACCESS_KEY=
AWS_MEDIA_STAGING_REGION=us-west-2
AWS_MEDIA_STAGING_BUCKET=
```

---

## Completion criteria

This plan is **not complete** until all of the following are true:

1. The WebView Threads implementation (`src/platforms/threads.py`, legacy `THREADS_SPECS`,
   associated setup wizard pages, settings wiring, and WebView test files) has been
   fully removed.
2. `MetaThreadsPlatform` and `MetaFacebookPagePlatform` API adapters are implemented and
   confirmed posting end-to-end against real accounts.
3. Both platforms are wired into the main window platform factory, setup wizard, settings
   dialog (including connection test buttons), and the composer destination selector.
4. All unit tests listed in Phase 11 have been written and pass (`make test-cov` green).
5. Functional tests for Threads API and Facebook Page have been added and pass against
   real credentials.
6. `PLATFORM_SPECS_MAP` contains `meta_threads` and `meta_facebook_page` as the only
   Threads and Facebook entries; the legacy `threads` (WebView) key has been removed.
7. `docs/platforms/THREADS.md`, `docs/platforms/FACEBOOK.md`, and
   `docs/platforms/PLATFORM_SPECS.md` all reflect the API-based state.

---

## Things not to assume

- Do not assume a Threads token can post to Instagram.
- Do not assume an Instagram token can post to Facebook Pages.
- Do not assume a Facebook user token is the same thing as a Facebook Page token.
- Do not assume ordinary personal Instagram accounts are eligible for the publishing API.
- Do not hardcode one-token-per-human logic; use one-token-per-connected-surface.
- Do not assume the Threads app ID is the same as the top-level Meta app ID — it is not.
- Do not assume the same redirect URI server instance can serve multiple concurrent
  OAuth flows; spin up a fresh server per flow.
- Do not persist the credential JSON file after import; treat it as a one-time import
  vehicle only.
- Do not assume long-lived Page tokens expire on a schedule — they can be invalidated
  at any time by password changes or permission revocation.
- Do not attempt a Meta publish call before the S3 upload has succeeded and returned a
  public URL.
- Do not use personal AWS credentials or the windsofstorm profile for S3 media staging;
  use the dedicated IAM user with scoped permissions only.
- Do not implement explicit S3 DeleteObject calls; the lifecycle policy is the sole
  cleanup mechanism.
- Do not leave `src/platforms/threads.py` in place after the API adapter is confirmed
  working; the WebView and API code paths must not coexist long-term.

---

## App Review and access levels

App Review is **not required** for this use case. All three apps operate in development
mode permanently. Development mode allows full API access for:
- Any account that has a role on the app (developer, tester, etc.)
- The app owner's own accounts

To grant Rin access: add her as a Tester on each app (see setup steps above). She does
not need to interact with the Meta developer console herself — just accept the tester
invitations through the relevant platform's settings UI.

If GaleFling were ever extended to support arbitrary third-party users, App Review and
Business Verification would then be required per permission per app. That is out of
scope for the current use case.
