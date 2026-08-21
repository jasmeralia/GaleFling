# Credential Import Format

GaleFling's setup wizard and Settings dialog can bulk-import **app-level**
credentials from a single JSON file — the developer app IDs, secrets, and
service accounts an administrator (Jas) provisions once and hands to the
end user (Rin), rather than something she generates herself. This is
distinct from **per-platform session import**, like OnlyFans' `auth.json`
export (see [docs/platforms/ONLYFANS_SESSION_IMPORT.md](platforms/ONLYFANS_SESSION_IMPORT.md)) —
that's a live browser session for one account, not an app credential.

Implemented in `src/core/credential_importer.py::import_credentials()`.
Reachable from:
- **Setup Wizard → App Credentials** (`CredentialImportPage`, first run)
- **Settings → Advanced → Import Credentials from JSON** (any time after)

Both call the same function, so the format and behavior are identical
regardless of when you import.

## Full schema

Every section is optional and independent — see [Partial imports](#partial-imports).
This example shows every currently-supported field:

```json
{
  "version": 1,
  "meta": {
    "oauth_redirect_uri": "https://<your-relay-domain>/oauth/callback",
    "threads":   { "app_id": "<Threads App ID>",   "app_secret": "..." },
    "instagram": { "app_id": "<Instagram App ID>", "app_secret": "..." },
    "facebook":  { "app_id": "<top-level App ID>", "app_secret": "..." }
  },
  "twitter": {
    "client_id": "<OAuth 2.0 Client ID>",
    "client_secret": "<OAuth 2.0 Client Secret>"
  },
  "aws": {
    "access_key_id": "<IAM access key ID>",
    "secret_access_key": "<IAM secret access key>",
    "region": "us-west-2",
    "media_staging_bucket": "<S3 bucket name>"
  },
  "smtp": {
    "host": "smtp.gmail.com",
    "port": 587,
    "username": "galefling@rin-city.com",
    "app_password": "<app password>"
  }
}
```

## Field reference

| Section | Field | Required to import | Default if absent | Notes |
|---|---|---|---|---|
| *(top level)* | `version` | **Yes** | — | Must equal `1` exactly (strict equality, not "at least") or the **entire file** is rejected. See [Why version isn't bumped for additive fields](#why-version-isnt-bumped-for-additive-fields). |
| `meta` | `oauth_redirect_uri` | No — separately optional | the built-in relay URL | Not gated by the threads/instagram/facebook completeness checks; imported on its own if present. |
| `meta.threads` | `app_id`, `app_secret` | Both | — | Threads use-case-scoped App ID — **not** the top-level Meta App ID. See [docs/platforms/META_APPS.md](platforms/META_APPS.md#the-app-id-asymmetry). |
| `meta.instagram` | `app_id`, `app_secret` | Both | — | Instagram use-case-scoped App ID — also not the top-level ID. |
| `meta.facebook` | `app_id`, `app_secret` | Both | — | The **top-level** App ID, unlike Threads/Instagram — this is the one exception. |
| `twitter` | `client_id`, `client_secret` | Both | — | OAuth 2.0 app credentials. Distinct from the older OAuth 1.0a API key/secret, which this file does not carry (per-account, entered in the Twitter setup wizard step instead). |
| `aws` | `access_key_id`, `secret_access_key`, `media_staging_bucket` | All three | — | Required for Instagram/Threads media posts (S3 staging — Graph API needs a public URL, not a binary upload). |
| `aws` | `region` | No | `us-west-2` | |
| `smtp` | `host`, `username`, `app_password` | All three | — | Not yet used by any shipped feature — lands ahead of the scheduling feature's failure-notification email. See [docs/EMAIL_NOTIFICATIONS.md](EMAIL_NOTIFICATIONS.md). |
| `smtp` | `port` | No | `587` | `465` (implicit TLS) is also supported; anything else uses STARTTLS. |

The **notification email address** that SMTP would send *to* is deliberately
**not** part of this file — it isn't a secret an administrator provisions,
it's Rin's own preference for where alerts land, set directly in the Setup
Wizard or Settings → Advanced → Email Notifications. See
[docs/EMAIL_NOTIFICATIONS.md](EMAIL_NOTIFICATIONS.md#two-separate-pieces).

## Partial imports

A file need not contain every section. Only sections **present and
complete** are imported; a present-but-incomplete section (e.g. `aws` with
`access_key_id` but no `secret_access_key`) is reported as **skipped**, not
an error — the rest of the file still imports normally. This is what lets
an administrator hand over one section at a time, or add a new one (like
`smtp`) to an existing file without touching what's already there.

## Import result feedback

Both the Setup Wizard and Settings dialog report exactly what happened,
broken into three buckets so a non-technical user can act on it without
reading logs:

- **Imported** — sections that were present, complete, and stored.
- **Skipped (incomplete)** — sections that were present but missing a
  required field. Nothing was stored for these; check the field reference
  above against what the administrator sent.
- **Errors** — file couldn't be read, wasn't valid JSON, or failed the
  version check. These stop the whole import (see below), unlike a skipped
  section which only affects that one section.

## Why `version` isn't bumped for additive fields

`SUPPORTED_VERSION` has been `1` since this importer was written and adding
the `smtp` section didn't change that — deliberately. The version check is
**strict equality** (`data.get('version') != SUPPORTED_VERSION`), not a
minimum or range check, so bumping it would make the app start **rejecting
every existing `"version": 1` file outright**, including every file already
handed to Rin, even though those files remain completely valid. A new,
optional, additive section doesn't break anything for a file that doesn't
have it, and an old app build encountering an unrecognized new section just
ignores that one key — so there's nothing for the version number to guard
against here. Reserve an actual bump for a change that breaks old files:
a field renamed, a section's meaning changed, required-ness changed for an
existing field.

## Validating before importing

`tools/validate_import_file.py path/to/creds_import.json` checks a file
against this schema and against what's already stored locally — structural
validation only, read-only, never calls the real importer or writes
anything. Reports per-field `match` / `differs` / `new` / `empty` status
without ever printing a credential value, so its output is safe to paste
anywhere (Slack, an issue, back to Claude).

```bash
.venv/bin/python tools/validate_import_file.py path/to/creds_import.json
.venv/bin/python tools/validate_import_file.py path/to/creds_import.json --config-dir ~/.config/GaleFling
```

## Security

Never commit a real credentials JSON file to this repo, log its contents,
or paste raw values anywhere. GaleFling itself doesn't modify or delete the
file after import — it's the administrator's copy to keep or discard.

## Where each section's credentials come from

- `meta.*` — [docs/platforms/META_APPS.md](platforms/META_APPS.md) (shared setup notes),
  plus [THREADS.md](platforms/THREADS.md), [INSTAGRAM.md](platforms/INSTAGRAM.md),
  [FACEBOOK.md](platforms/FACEBOOK.md) per platform
- `twitter.*` — [docs/platforms/TWITTER.md](platforms/TWITTER.md)
- `aws.*` — `infrastructure/galefling-media-staging.yaml` (the CloudFormation stack that
  provisions the IAM user and bucket)
- `smtp.*` — [docs/EMAIL_NOTIFICATIONS.md](EMAIL_NOTIFICATIONS.md)
