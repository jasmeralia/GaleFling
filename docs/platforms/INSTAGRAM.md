# Instagram Setup Guide

GaleFling posts to Instagram using the **Instagram Platform Content Publishing API**
(Instagram Login path, `https://graph.instagram.com/`). Authentication is handled via
Instagram OAuth, which produces a long-lived Instagram user access token stored securely
in the system credential store.

GaleFling supports **up to 2 Instagram accounts**.

## Prerequisites

Before connecting an Instagram account, you must have:

1. An Instagram account converted to a **Business** or **Creator** account. Personal
   accounts are not eligible for the publishing API.
   - Open the Instagram app and go to **Settings > Account**.
   - Tap **Switch to professional account**, then choose **Business** or **Creator**.
   - No Facebook Page link is required under this path.
2. Meta app credentials imported into GaleFling via **Settings > Advanced > Import
   Credentials**. Your operator (Jas) provides a JSON credential file for this step.
   Without app credentials imported, the Connect button will be disabled.
3. You must have been added as an **Instagram Tester** on the GaleFling Instagram app in
   the Meta developer portal. Your operator handles this — you only need to accept the
   invitation via **Instagram app → Settings and privacy → Apps and websites → Tester
   invites**.

## Connecting an Account

1. Open GaleFling and go to **Settings > Instagram**.
2. Under **Connected Accounts**, click **Connect** next to the account slot you want
   to fill (Account 1 or Account 2).
3. GaleFling opens a browser window pointing to the Instagram authorization page.
4. Log in to Instagram (if not already logged in) and tap **Allow** to grant GaleFling
   permission to post on your behalf.
5. The browser tab shows "You can close this tab" — GaleFling has received the
   authorization code and the setup is complete.
6. The account now shows as **Connected** in the Meta settings tab, with your
   Instagram username displayed.

## Required Permissions

GaleFling requests the following Instagram scopes during the connect flow:

| Scope | Purpose |
|---|---|
| `instagram_business_basic` | Required baseline for all Instagram API calls |
| `instagram_business_content_publish` | Required to create and publish posts |

## Post Types Supported

| Post Type | Supported |
|---|---|
| Single image | Yes |
| Single video | Yes |
| Carousel (2–10 items) | Yes |

Stories are explicitly out of scope — GaleFling only publishes to the main feed.

## Media Specifications

### Images

| Constraint | Limit |
|---|---|
| Formats | JPEG, PNG |
| Max dimensions | 1440 × 1440 px |
| Max file size | 8 MB |
| Max attachments | 10 images per carousel |

### Videos

| Constraint | Limit |
|---|---|
| Format | MP4 |
| Max dimensions | 1920 × 1080 px |
| Max file size | 100 MB |
| Max duration | 60 seconds |

### Text

| Constraint | Limit |
|---|---|
| Max length | 2,200 characters |
| Text with media | Supported (an image or video is required — Instagram does not support text-only posts) |

## How Posting Works

Instagram requires media to be hosted at a publicly accessible URL — it cannot accept
binary file uploads directly in the API payload. GaleFling handles this automatically:

1. GaleFling uploads your media to a private S3 staging bucket and obtains a temporary
   public URL.
2. GaleFling calls the Instagram API to create a media container, passing the S3 URL.
3. GaleFling polls the container status until processing is complete.
4. GaleFling publishes the container, making the post live on Instagram.
5. The S3 staging object is automatically cleaned up within 7 days by a lifecycle
   policy — no action required on your part.

## Token Renewal

Instagram access tokens are valid for **60 days**. GaleFling automatically refreshes
your token before it expires — you will not need to re-authorize under normal
conditions. If a refresh ever fails (for example, after a password change or a revoked
permission), GaleFling will show a **Re-authorize** prompt in the Meta settings tab.
Click it and repeat the connect flow to restore posting access.

## Webhooks (not required)

Leave the **Configure webhooks** step of the Instagram use case unconfigured in the App
Dashboard. GaleFling only publishes and consumes no webhook events, so there is nothing
for a callback URL to deliver to. The dashboard's note that "your app must be in
published state" to receive webhooks concerns event delivery, not App Review, and does
not apply here.

In particular, do **not** put the OAuth relay URL in the webhook Callback URL field.
That endpoint answers OAuth redirects by issuing a redirect to localhost; it does not
implement Meta's `hub.challenge` verification handshake, so Meta rejects it with "The
callback URL or verify token couldn't be validated." That URL belongs in **OAuth
redirect URIs** under the Instagram use case's Business Login settings.

## Deleting media is not possible on this API setup

GaleFling uses **Instagram API with Instagram Login** (`graph.instagram.com`), which
cannot delete media. This is a property of the API setup, not a missing permission or an
expired token — no scope grants it and no token can be re-minted to gain it.

Meta's [IG Media reference](https://developers.facebook.com/docs/instagram-platform/reference/instagram-media/)
lists both setups under **Reading** but only one under **Deleting**:

| | Reading | Deleting |
|---|---|---|
| Instagram API with Instagram Login (`graph.instagram.com`) | ✓ | — |
| Instagram API with Facebook Login (`graph.facebook.com`) | ✓ | ✓ |
| Permissions for delete | — | `instagram_basic`, `instagram_manage_contents` |

Its own wording: *"This api only supports Instagram API with Facebook login only."*

A `DELETE` attempt against a live, readable media object returns
`HTTP 400 / code 100 / subcode 33 — "Object with ID '…' does not exist, cannot be loaded
due to missing permissions, or does not support this operation"`. That message covers
three unrelated causes and names none of them; here it is the third. The object
demonstrably exists, because the same token reads it back seconds earlier.

**Consequence for testing:** mutating Instagram functional tests cannot clean up after
themselves. Every run leaves posts that must be removed by hand in the Instagram app.
The run reports each one with its tag and permalink and records it in the artifact ledger.
See [FUNCTIONAL_TESTING.md](../testing/FUNCTIONAL_TESTING.md#leaving-mutating-artifacts-up-for-inspection).

Switching to Instagram API with Facebook Login purely to enable test cleanup would change
the credentials, the login flow, and the host URL the adapter targets — a materially
different integration for the whole product. Manual cleanup is the cheaper trade.

## Troubleshooting

| Problem | Solution |
|---|---|
| `Invalid platform app` on the authorization screen | The configured `app_id` is the app's top-level App ID. Use the **Instagram App ID** shown at App Dashboard > Instagram use case > Settings — it is a different number from the app's top-level ID. See [META_APPS.md](META_APPS.md#the-app-id-asymmetry). |
| `Insufficient developer role` on the authorization screen | The Instagram account has no accepted **Instagram Tester** role on the app. A pending invitation is not enough — accept it at Instagram > Settings and privacy > Apps and websites > Tester invites. See [META_APPS.md](META_APPS.md#tester-roles-while-apps-are-in-development). |
| Connect button is disabled | Enter app credentials in **Settings > Instagram > App Credentials**, or import them via **Settings > Advanced > Import Credentials**. |
| "The callback URL or verify token couldn't be validated" | Something that is not a webhook endpoint was entered as the webhook Callback URL. See [Webhooks](#webhooks-not-required) — the step can be skipped entirely. |
| `IG-AUTH-INVALID` | Token is wrong or lacks required permissions. Disconnect and reconnect the account. |
| `IG-AUTH-EXPIRED` | Automatic refresh failed, or the 60-day token fully expired. Reconnect via **Settings > Instagram**. |
| `IG-RATE-LIMIT` | Instagram limits posting frequency (100 API-published posts per 24-hour period). Wait before posting again. |
| `IMG-UPLOAD-FAILED` / `IMG-TOO-LARGE` / `IMG-INVALID-FORMAT` | Image may exceed 8 MB or be in an unsupported format. Use JPEG or PNG. |
| "Instagram Business account required" | Your account must be converted to Business or Creator type — see [Prerequisites](#prerequisites). |
