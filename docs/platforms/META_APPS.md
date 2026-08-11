# Meta App Setup — Shared Notes

GaleFling talks to three Meta platforms — Threads, Instagram, and Facebook Pages
— and each is configured as its **own Meta app** in the App Dashboard at
[developers.facebook.com](https://developers.facebook.com/). This page covers
what is shared across all three. For per-platform detail see
[THREADS.md](THREADS.md), [INSTAGRAM.md](INSTAGRAM.md), and
[FACEBOOK.md](FACEBOOK.md).

## One app per platform

Each app carries a single use case. Keeping them separate avoids the ambiguity
of one app exposing several use-case-scoped IDs at once.

| Platform | Use case to select when creating the app |
|---|---|
| Threads | Threads API (Threads use case) |
| Instagram | Instagram API with Instagram login |
| Facebook Pages | Manage everything on your Page |

Record which dashboard app corresponds to which platform somewhere you control.
The dashboard's app names are unhelpful here: Meta's naming policy **rejects**
app names containing its brand terms (`FB`, `IG`, `Insta`, `Gram`, `Face`,
`Book`, `Threads`, …), so the obvious labels are unavailable.

## The App ID asymmetry

This is the single most error-prone part of the setup, and it is not consistent
across the three platforms:

| Platform | Which App ID to use | Where it appears in the dashboard |
|---|---|---|
| Threads | **Threads App ID** — use-case-scoped | App settings > Basic > Threads App ID |
| Instagram | **Instagram App ID** — use-case-scoped | Instagram > API setup with Instagram login > Business login settings |
| Facebook | the app's **top-level App ID** | App settings > Basic > App ID |

Threads and Instagram each expose *two* app IDs and two secrets — the app's
top-level pair and a use-case-scoped pair. **Use the use-case-scoped pair.**
Facebook is the exception that uses the top-level ID.

Supplying a top-level App ID where a use-case-scoped one is required produces
`Invalid platform app` at the authorization window. Enter the values in
**Settings > Meta > App Credentials**, or import them all at once via
**Settings > Advanced > Import Credentials**:

```json
{
  "meta": {
    "oauth_redirect_uri": "https://<your-relay-domain>/oauth/callback",
    "threads":   { "app_id": "<Threads App ID>",   "app_secret": "..." },
    "instagram": { "app_id": "<Instagram App ID>", "app_secret": "..." },
    "facebook":  { "app_id": "<top-level App ID>", "app_secret": "..." }
  }
}
```

## Redirect URIs are per use case

The relay URL must be registered separately for each app, and **not** in the
same field:

| Platform | Where the redirect URI goes |
|---|---|
| Threads | Threads use case settings > Redirect Callback URLs |
| Instagram | Instagram > Business login settings > OAuth redirect URIs |
| Facebook | App settings > Advanced > Valid OAuth Redirect URIs |

The top-level "Valid OAuth Redirect URIs" list belongs to Facebook Login and
does **not** apply to the Threads or Instagram use cases, even though all three
apps share the same relay URL.

## Tester roles while apps are in development

An app in Development mode only lets accounts **with a role on that app** grant
permissions. Holding the Administrator role via your Meta developer account is
not sufficient: Threads and Instagram check a separate, platform-scoped role
tied to the Threads/Instagram **username**.

1. App Dashboard > **App roles > Roles > Add People**
2. Choose **Instagram Tester** or **Threads Tester** and enter the username
3. **Accept the invitation from the account itself** — until then it shows as
   *Pending* and authorization keeps failing:
   - Instagram: Settings and privacy > Apps and websites > Tester invites
   - Threads: Account Settings > Website permissions > Invites

Assign the role for whichever account will actually be connected. An invitation
sent to a different account does not help, and cannot be accepted on that
account's behalf.

## Publishing and App Review are different things

- **Published / Live** is an App Mode toggle. It gates access for users with no
  role on the app, and webhook delivery. Going Live requires a privacy policy
  URL.
- **App Review** is the separate process for advanced access to permissions.

Neither is required to post to accounts you hold a tester role on. GaleFling
works against apps left in Development mode.

## Webhooks are not needed

GaleFling only publishes and consumes no webhook events, so the **Configure
webhooks** step of the Instagram use case can be left unconfigured. See
[INSTAGRAM.md](INSTAGRAM.md#webhooks-not-required) — in particular, do not put
the OAuth relay URL in the webhook Callback URL field; it is not a webhook
endpoint and Meta will reject it.

## Scopes: request only what is used

Meta expands a requested permission to its documented **dependencies**, and
rejects the entire authorize request if any of them is unavailable to the app —
naming a scope the request never contained. Two permissions have been removed
from GaleFling's Facebook request for this reason:

| Removed scope | Why |
|---|---|
| `publish_video` | Deprecated personal-profile permission; irrelevant to Page video posts |
| `pages_manage_engagement` | Covers comment/like management GaleFling never does, and pulls in a `pages_read_user_content` dependency the app does not hold |

Before adding a Meta permission, check its dependency list in Meta's
[Permissions Reference](https://developers.facebook.com/docs/permissions/) and
confirm the app can actually hold every one of them.
