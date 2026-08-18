# Instagram Setup Guide

GaleFling posts to Instagram using the Facebook Graph API. This requires a **Business** or **Creator** Instagram account linked to a Facebook Page. Personal Instagram accounts are not supported by Meta's API.

## Prerequisites

Before you begin, make sure you have:

1. An Instagram account converted to a **Business** or **Creator** account.
2. A **Facebook Page** linked to that Instagram account.
3. A **Meta (Facebook) Developer** account.

### Converting to a Business/Creator Account

1. Open the Instagram app and go to **Settings > Account**.
2. Tap **Switch to professional account**.
3. Choose **Business** or **Creator** and follow the prompts.
4. When asked, connect your Facebook Page (or create a new one).

### Creating a Facebook Page (if needed)

1. Go to [facebook.com/pages/create](https://www.facebook.com/pages/create).
2. Choose a page name and category.
3. After creating the page, link it to your Instagram account via **Page Settings > Instagram**.

## Obtaining Credentials

You need three values to configure Instagram in GaleFling:

| Credential | Description |
|---|---|
| Access Token | A long-lived token from the Graph API |
| Instagram User ID | Your Instagram Business account's numeric ID |
| Facebook Page ID | The numeric ID of the linked Facebook Page |

### Step 1: Create a Meta App

1. Go to [developers.facebook.com](https://developers.facebook.com/) and log in.
2. Click **My Apps > Create App**.
3. Select **Business** as the app type.
4. Give it a name (e.g. "GaleFling Posting") and click **Create App**.

### Step 2: Add Instagram Graph API

1. In your app dashboard, click **Add Product**.
2. Find **Instagram Graph API** and click **Set Up**.

### Step 3: Generate a User Access Token

1. Go to **Tools > Graph API Explorer** ([developers.facebook.com/tools/explorer](https://developers.facebook.com/tools/explorer/)).
2. Select your app from the **Meta App** dropdown.
3. Click **Generate Access Token**.
4. Grant the following permissions when prompted:
   - `instagram_basic`
   - `instagram_content_publish`
   - `pages_show_list`
   - `pages_read_engagement`
5. Copy the generated token.

### Step 4: Extend the Token

The token from Step 3 is short-lived (about 1 hour). Extend it to a long-lived token (60 days):

1. Go to [developers.facebook.com/tools/debug/accesstoken](https://developers.facebook.com/tools/debug/accesstoken/).
2. Paste your token and click **Debug**.
3. Click **Extend Access Token** at the bottom.
4. Copy the new long-lived token.

Alternatively, use the Graph API directly:

```
GET https://graph.facebook.com/v21.0/oauth/access_token
  ?grant_type=fb_exchange_token
  &client_id=YOUR_APP_ID
  &client_secret=YOUR_APP_SECRET
  &fb_exchange_token=YOUR_SHORT_LIVED_TOKEN
```

### Step 5: Find Your Facebook Page ID

Using the Graph API Explorer with your long-lived token:

```
GET /me/accounts
```

This returns a list of Pages you manage. The `id` field is your Page ID.

### Step 6: Find Your Instagram User ID

Using the Graph API Explorer:

```
GET /YOUR_PAGE_ID?fields=instagram_business_account
```

The `instagram_business_account.id` value is your Instagram User ID.

## Entering Credentials in GaleFling

On first launch, the setup wizard asks for Instagram credentials. If you already ran the wizard, go to **Settings > Accounts** instead.

1. **Profile Name**: A label for this account (e.g. `rinthemodel`).
2. **Access Token**: The long-lived token from Step 4.
3. **IG User ID**: The Instagram User ID from Step 6.
4. **Facebook Page ID**: The Page ID from Step 5.

## Token Renewal

Long-lived tokens expire after **60 days**. When your token expires, posts will fail with `IG-AUTH-EXPIRED`. To fix this:

1. Repeat Steps 3-4 above to generate a new long-lived token.
2. Go to **Settings > Accounts** in GaleFling and update the Access Token field.
3. Click **Save**.

You can also refresh a still-valid long-lived token before it expires:

```
GET https://graph.facebook.com/v21.0/oauth/access_token
  ?grant_type=fb_exchange_token
  &client_id=YOUR_APP_ID
  &client_secret=YOUR_APP_SECRET
  &fb_exchange_token=YOUR_CURRENT_LONG_LIVED_TOKEN
```

## Webhooks (not required)

Leave the **Configure webhooks** step of the Instagram use case unconfigured.
GaleFling only publishes and consumes no webhook events, so there is nothing for
a callback URL to deliver to. The dashboard's note that "your app must be in
published state" to receive webhooks concerns event delivery, not App Review,
and does not apply here.

In particular, do **not** put the OAuth relay URL
(`https://galefling.jasmer.tools/oauth/callback`) in the webhook Callback URL
field. That endpoint answers OAuth redirects by issuing a 302 to localhost; it
does not implement Meta's `hub.challenge` verification handshake, so Meta
rejects it with "The callback URL or verify token couldn't be validated." That
URL belongs in **OAuth redirect URIs** under the business login settings.

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
themselves. Every run leaves five posts that must be removed by hand in the Instagram app.
The run reports each one with its tag and permalink and records it in the artifact ledger.
See [FUNCTIONAL_TESTING.md](../testing/FUNCTIONAL_TESTING.md#leaving-mutating-artifacts-up-for-inspection).

Switching to Instagram API with Facebook Login purely to enable test cleanup would change
the credentials, the login flow, and the host URL the adapter targets — a materially
different integration for the whole product. Manual cleanup is the cheaper trade.

## Troubleshooting

| Problem | Solution |
|---|---|
| `Invalid platform app` on the authorization screen | The `client_id` is the top-level Meta App ID. Use the **Instagram app ID** shown at the top of App Dashboard > Instagram > API setup with Instagram login — it is a different number from the app's top-level ID. See [META_APPS.md](META_APPS.md#the-app-id-asymmetry). |
| Connect button is disabled | Enter app credentials in **Settings > Instagram > App Credentials**, or import them via **Settings > Advanced > Import Credentials**. |
| `Insufficient developer role` on the authorization screen | The Instagram account has no accepted **Instagram Tester** role on the app. A pending invitation is not enough — accept it at Instagram > Settings and privacy > Apps and websites > Tester invites. See [META_APPS.md](META_APPS.md#tester-roles-while-apps-are-in-development). |
| "The callback URL or verify token couldn't be validated" | Something that is not a webhook endpoint was entered as the webhook Callback URL. See [Webhooks](#webhooks-not-required) — the step can be skipped entirely. |
| `IG-AUTH-INVALID` | Token is wrong or lacks required permissions. Regenerate with correct scopes. |
| `IG-AUTH-EXPIRED` | Token has expired (60-day limit). Generate a new long-lived token. |
| `IG-RATE-LIMIT` | Instagram limits posting frequency. Wait before posting again. |
| `IMG-UPLOAD-FAILED` | Image may exceed 8 MB or be in an unsupported format. Use JPEG or PNG. |
| "Instagram Business account required" | Your account must be converted to Business or Creator type. |
| Page ID returns empty `instagram_business_account` | The Facebook Page is not linked to an Instagram Business account. Link it in Page Settings. |
