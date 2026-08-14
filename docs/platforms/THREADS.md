# Threads Setup Guide

GaleFling posts to Threads using the **Threads API** (`https://graph.threads.net/v1.0/`).
Authentication is handled via Threads OAuth, which produces a long-lived Threads user
access token stored securely in the system credential store.

GaleFling supports **up to 2 Threads accounts**.

## Prerequisites

Before connecting a Threads account, you must have:

1. A Threads account (any account type — public or private both work, with different
   token renewal behavior; see **Token Renewal** below).
2. Meta app credentials imported into GaleFling via **Settings > Advanced > Import
   Credentials**. Your operator (Jas) provides a JSON credential file for this step.
   Without app credentials imported, the Connect button will be disabled.
3. You must have been added as a **Threads Tester** on the GaleFling Threads app in the
   Meta developer portal. Your operator handles this — you only need to accept the
   invitation via **Threads app → Settings → Account → Website permissions**.

## Connecting an Account

1. Open GaleFling and go to **Settings > Meta**.
2. Under the **Threads** section, click **Connect** next to the account slot you want
   to fill (Account 1 or Account 2).
3. GaleFling opens a browser window pointing to the Threads authorization page.
4. Log in to Threads (if not already logged in) and tap **Allow** to grant GaleFling
   permission to post on your behalf.
5. The browser tab shows "You can close this tab" — GaleFling has received the
   authorization code and the setup is complete.
6. The account now shows as **Connected** in the Meta settings tab, with your
   Threads username displayed.

## Required Permissions

GaleFling requests the following Threads API scopes during the connect flow:

| Scope | Purpose |
|---|---|
| `threads_basic` | Required for all Threads API calls; grants read access to profile |
| `threads_content_publish` | Required to create and publish posts |

GaleFling does not request `threads_delete`, because the app never deletes a post. The
**functional test suite does** need it: without that scope, `DELETE /{threads-media-id}`
answers `HTTP 500 / code 10 — "Application does not have permission for this action"`, so
mutating test runs cannot clean up after themselves and leave their posts on the account.

The test token is therefore minted separately, with the wider scope, rather than widening
`_THREADS_SCOPES` in `src/core/meta_oauth.py`:

```bash
.venv/bin/python tools/oauth/meta_threads_remint.py
```

It reuses the app's own OAuth machinery, writes the result into `tests/functional/.env`
without printing it, and proves the scope by publishing a throwaway post and deleting it —
the only check that works, since Graph returns the same generic code 100 for "missing
object" as for "no permission". Long-lived tokens last 60 days, so this recurs.

**Enabling the scope in the App Dashboard is not enough on its own.** An OAuth token
carries the scopes granted at authorization time, so an already-issued token keeps being
refused until it is re-minted.

> Meta's own docs are inconsistent here: the *Get Access Tokens* page (Mar 2025) omits
> `threads_delete` from its list of valid authorization scopes, while *Delete Posts*
> (Jul 2025) requires it. The scope list appears stale. If the authorization window
> rejects the request with `Invalid Scopes`, that is the likely cause.

See [FUNCTIONAL_TESTING.md](../testing/FUNCTIONAL_TESTING.md#leaving-mutating-artifacts-up-for-inspection).

## Post Types Supported

| Post Type | Supported |
|---|---|
| Text-only | Yes |
| Single image | Yes |
| Single video | Yes |
| Carousel (2–20 items) | Yes |

## Media Specifications

### Images

| Constraint | Limit |
|---|---|
| Formats | JPEG, PNG |
| Max width | 1440 px |
| Max height | 1440 px |
| Min width | 320 px |
| Color space | sRGB |
| Max file size | 8 MB |
| Max attachments | 10 images per carousel |

### Videos

| Constraint | Limit |
|---|---|
| Formats | MP4, MOV |
| Codec | H.264 or HEVC |
| Frame rate | 23–60 FPS |
| Max dimensions | 1920 × 1080 px |
| Max file size | 1 GB |
| Max duration | 5 minutes (300 seconds) |

### Text

| Constraint | Limit |
|---|---|
| Max length | 500 characters |
| Text with media | Supported |

## How Posting Works

Threads requires media to be hosted at a publicly accessible URL — it cannot accept
binary file uploads directly in the API payload. GaleFling handles this automatically:

1. For image and video posts, GaleFling uploads your media to a private S3 staging
   bucket and obtains a temporary public URL.
2. GaleFling calls the Threads API to create a media container, passing the S3 URL.
3. GaleFling polls the container status until processing is complete (typically 10–30
   seconds for media).
4. GaleFling publishes the container, making the post live on Threads.
5. The S3 staging object is automatically cleaned up within 7 days by a lifecycle
   policy — no action required on your part.

For text-only posts, steps 1–2 are skipped, but **step 3 still applies**. A text
container carries no media to fetch or transcode, yet it is still not publishable the
instant it is created — publishing too early fails with `code 24` / *"The requested
resource does not exist"*, which looks like a bad container ID rather than a timing
problem. It settles in a few seconds.

## Token Renewal

Threads access tokens are valid for **60 days** and must be renewed periodically.

**Public profile accounts:** GaleFling can refresh your token automatically before it
expires. Each refresh extends your authorization for another 90 days. You will not need
to re-authorize unless you revoke access or change your Meta password.

**Private profile accounts:** Threads does not allow automatic token extension for
private profiles. When your token expires (after 60 days), GaleFling will show a
**Re-authorize** prompt in the Meta settings tab. Click it and repeat the connect flow
to restore posting access. This is a Threads platform limitation and cannot be
worked around.

GaleFling displays a warning banner when a Threads token is within 10 days of expiry,
giving you time to renew before posting fails.

## Rate Limits

The Threads API allows **250 published posts per 24-hour period** per profile. GaleFling
does not currently track this limit in the UI; if you hit it, the post will fail with
a `TH-RATE-LIMIT` error.

## Troubleshooting

| Problem | Solution |
|---|---|
| `Invalid platform app` on the authorization screen | The configured `app_id` is the app's top-level App ID. Use the **Threads App ID** from App settings > Basic. See [META_APPS.md](META_APPS.md#the-app-id-asymmetry). |
| `Insufficient developer role` on the authorization screen | The Threads account has no accepted **Threads Tester** role on the app. A pending invitation is not enough — accept it at Threads > Account Settings > Website permissions > Invites. See [META_APPS.md](META_APPS.md#tester-roles-while-apps-are-in-development). |
| Connect button is disabled | Enter app credentials in **Settings > Meta > App Credentials**, or import them via **Settings > Advanced > Import Credentials**. |
| "Re-authorize" prompt on a private profile | Your 60-day token has expired. Click **Re-authorize** and complete the connect flow again. This is expected for private Threads profiles. |
| `TH-AUTH-EXPIRED` error when posting | Your token has expired. Go to **Settings > Meta** and reconnect the affected Threads account. |
| `TH-AUTH-INVALID` error when posting | Your token may have been revoked (e.g. after a password change). Disconnect and reconnect the account. |
| `TH-RATE-LIMIT` error when posting | You have hit the 250-posts-per-24-hours limit for this profile. Wait before posting again. |
| `TH-POST-FAILED` error | The Threads API returned an unexpected error. Check that your media meets the format and size requirements above. |
| Post goes live but GaleFling shows an error | The API may have accepted the post but returned a non-standard response. Check your Threads profile to confirm whether the post appeared. |
| Media upload fails before posting | Verify your AWS staging credentials are configured correctly in **Settings > Advanced**. Use the **Test** button to confirm S3 access. |
