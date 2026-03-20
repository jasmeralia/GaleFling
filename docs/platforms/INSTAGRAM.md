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

## Troubleshooting

| Problem | Solution |
|---|---|
| `IG-AUTH-INVALID` | Token is wrong or lacks required permissions. Regenerate with correct scopes. |
| `IG-AUTH-EXPIRED` | Token has expired (60-day limit). Generate a new long-lived token. |
| `IG-RATE-LIMIT` | Instagram limits posting frequency. Wait before posting again. |
| `IMG-UPLOAD-FAILED` | Image may exceed 8 MB or be in an unsupported format. Use JPEG or PNG. |
| "Instagram Business account required" | Your account must be converted to Business or Creator type. |
| Page ID returns empty `instagram_business_account` | The Facebook Page is not linked to an Instagram Business account. Link it in Page Settings. |
