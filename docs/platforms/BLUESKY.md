# Bluesky Setup Guide

GaleFling posts to Bluesky using the AT Protocol (`atproto`). Auth uses an **app password** — not your main account password.

## Account Type

Any Bluesky account works. No paid tier or special account type required.

GaleFling supports **up to 2 Bluesky accounts**.

## Credential Setup

You need two values per account:

| Credential | Description |
|---|---|
| Identifier | Your handle (e.g. `yourname.bsky.social`) or a custom domain handle |
| App Password | A scoped password generated in Bluesky settings |

### Step 1: Create an App Password

1. Log into [bsky.app](https://bsky.app).
2. Go to **Settings > Privacy and Security > App Passwords**.
3. Click **Add App Password**.
4. Name it (e.g. "GaleFling") — this is just a label for your reference.
5. Copy the generated password (format: `xxxx-xxxx-xxxx-xxxx`). It is shown only once.

### Step 2: Enter Credentials in GaleFling

On first launch, the setup wizard prompts for Bluesky credentials. If you already ran the wizard, go to **Settings > Accounts**.

1. **Profile Name**: A label for this account (e.g. `yourname`).
2. **Identifier**: Your full handle (e.g. `yourname.bsky.social`).
3. **App Password**: The password from Step 1.

### Adding a Second Account

GaleFling supports up to 2 accounts. Repeat the steps above, generating a separate app password for each account.

## Media Restrictions

### Images

| Constraint | Limit |
|---|---|
| Formats | JPEG, PNG |
| Max dimensions | 2000 × 2000 px |
| Max file size | 1 MB |
| Max attachments | 4 images per post |

> **Note:** WEBP is not supported by Bluesky's API. GaleFling auto-converts static WEBP to JPEG before uploading. Animated GIFs are also not supported and will be rejected.

### Videos

| Constraint | Limit |
|---|---|
| Format | MP4 |
| Max dimensions | 1920 × 1080 px |
| Max file size | 50 MB |
| Max duration | 60 seconds |

### Text

| Constraint | Limit |
|---|---|
| Max length | 300 characters |
| URL handling | URLs are auto-detected and turned into clickable facets |

GaleFling uses UTF-8 byte offsets (as required by the AT Protocol) when generating facets for URLs in post text.

## Platform Behavior

- **API type**: `atproto` — posts run silently in the background, no user confirmation required.
- **Auth method**: App password stored in Windows Credential Manager.
- **URL facets**: Any `http://` or `https://` links in post text are automatically linked using AT Protocol facet objects.

## Revoking Access

To revoke GaleFling's access without changing your main password:

1. Go to **Settings > Privacy and Security > App Passwords** on bsky.app.
2. Find the app password named "GaleFling" and delete it.

In GaleFling, go to **Settings > Accounts** and log out to remove stored credentials.

## Troubleshooting

| Problem | Solution |
|---|---|
| `BS-AUTH-INVALID` | App password is incorrect or has been revoked. Regenerate and update in Settings. |
| `BS-AUTH-EXPIRED` | Session has expired. Log out in Settings and re-enter credentials. |
| `BS-RATE-LIMIT` | Posting too fast. Wait a few minutes and try again. |
| `IMG-UPLOAD-FAILED` | Image may exceed 1 MB or be in an unsupported format (e.g. WEBP). GaleFling should convert WEBP automatically — if this persists, try a JPEG or PNG. |
| "identifier not found" | Check that your handle is spelled correctly including the `.bsky.social` suffix. |
