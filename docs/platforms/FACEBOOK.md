# Facebook Setup Guide

GaleFling posts to Facebook using the **Facebook Pages API** (Graph API for Pages,
`https://graph.facebook.com/v25.0/`). Authentication is handled via Facebook Login for
Business, which produces a long-lived Page access token stored securely in the system
credential store.

GaleFling supports **1 Facebook Page** per installation.

## Prerequisites

Before connecting a Facebook Page, you must have:

1. A Facebook account that administers the Page you want to post to.
2. Meta app credentials imported into GaleFling via **Settings > Advanced > Import
   Credentials**. Your operator (Jas) provides a JSON credential file for this step.
   Without app credentials imported, the Connect button will be disabled.
3. You must have been added as a **Tester** or **Developer** on the GaleFling Facebook
   app in the Meta developer portal. Your operator handles this — you only need to
   accept the invitation via **Facebook Settings > Business Integrations** or the
   notification in the Facebook app.

## Connecting a Facebook Page

1. Open GaleFling and go to **Settings > Meta**.
2. Under the **Facebook Page** section, click **Connect**.
3. GaleFling opens a browser window pointing to the Facebook Login for Business
   authorization page.
4. Log in to Facebook (if not already logged in) and grant the requested permissions
   when prompted.
5. If your Facebook account manages multiple Pages, GaleFling presents a list — select
   the Page you want to use and confirm your selection.
6. The browser tab shows "You can close this tab" — GaleFling has received the
   authorization and stored the long-lived Page access token.
7. The connection now shows as **Connected** in the Meta settings tab, with your Page
   name displayed.

## Required Permissions

GaleFling requests the following Facebook permissions during the connect flow:

| Permission | Purpose |
|---|---|
| `pages_manage_metadata` | Required baseline for Page API access |
| `pages_manage_posts` | Required to publish posts to the Page |
| `pages_read_engagement` | Required to read Page data |
| `pages_show_list` | Required to enumerate Pages the user administers |
| `pages_manage_engagement` | Required for photo posts |
| `publish_video` | Required for video posts to the Page |

## Post Types Supported

| Post Type | Supported |
|---|---|
| Text-only | Yes |
| Text with link | Yes |
| Photo | Yes |
| Video | Yes |

## Media Specifications

### Images

| Constraint | Limit |
|---|---|
| Formats | JPEG, PNG |
| Max dimensions | 4096 × 4096 px |
| Max file size | 10 MB |

### Videos

| Constraint | Limit |
|---|---|
| Formats | MP4, MOV |
| Max dimensions | 1920 × 1080 px |
| Max file size | 10 GB |

### Text

| Constraint | Limit |
|---|---|
| Max length | 63,206 characters |
| Text with media | Supported |

## How Posting Works

Facebook Page posting uses a single API call — there is no two-step container model and
no polling required:

- **Text or link posts:** GaleFling calls `POST /{page-id}/feed` with your message and
  optional link URL. The post goes live immediately.
- **Photo posts:** GaleFling calls `POST /{page-id}/photos` with the image. The post
  goes live immediately.
- **Video posts:** GaleFling calls the Facebook video upload endpoint. Processing may
  take a few seconds on Facebook's side, but GaleFling does not need to poll for
  completion.

## Token Renewal

Facebook Page access tokens are **effectively permanent**. Unlike Threads and Instagram
tokens, they do not expire on a 60-day schedule. They remain valid until one of the
following events occurs:

- You change your Facebook account password
- You revoke the GaleFling app's access via **Facebook Settings > Business Integrations**
- The Meta app itself is disabled or restricted

GaleFling monitors for `FB-AUTH-EXPIRED` errors and will show a **Reconnect** prompt in
the Meta settings tab if the Page token becomes invalid. Click it and repeat the connect
flow to restore posting access.

Because Page tokens do not expire routinely, no proactive renewal or periodic re-auth is
needed under normal conditions.

## Multiple Page Selection

If your Facebook account administers more than one Page, GaleFling presents all of them
after you authorize. Select the Page you want GaleFling to post to. Only one Page is
supported per installation. To switch to a different Page, disconnect the current
connection and reconnect, selecting the new Page during the authorization flow.

## Rate Limits

Facebook Page API rate limits are based on your app's usage tier and are not easily
enumerable from the client side. In practice, rate limiting is not a concern for the
typical GaleFling use case. If a post fails with `FB-RATE-LIMIT`, wait a few minutes
before retrying.

## Troubleshooting

| Problem | Solution |
|---|---|
| Connect button is disabled | Import Meta app credentials first via **Settings > Advanced > Import Credentials**. |
| Page list is empty after authorizing | Your Facebook account may not administer any Pages, or the Page is in a restricted state. Verify Page admin access in Facebook. |
| `FB-AUTH-EXPIRED` error when posting | Your Page token was invalidated (password change or permission revocation). Go to **Settings > Meta** and reconnect the Facebook Page. |
| `FB-AUTH-INVALID` error when posting | The token or Page ID is incorrect. Disconnect and reconnect. |
| `FB-RATE-LIMIT` error when posting | Facebook rate limited the request. Wait a few minutes and try again. |
| `FB-POST-FAILED` error | The Facebook API returned an unexpected error. Check that the Page is active and not restricted. |
| Post does not appear on the Page | Confirm the Page is published (not unpublished/draft status) and that GaleFling is using the correct Page ID. |
