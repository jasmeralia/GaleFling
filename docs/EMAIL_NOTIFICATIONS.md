# Email Notifications (SMTP)

GaleFling sends email notifications over SMTP when a scheduled post fails, and
optionally when one fully succeeds. Each failed scheduled item produces one
email naming its failed platform account(s), in addition to a system
notification that opens the normal results dialog. See
[Scheduling](SCHEDULING.md#failures-and-partial-success) for the complete
failure and retry flow.

## Two separate pieces

- **SMTP sending credentials** (host, port, username, app password) — a
  secret, provided by whoever administers GaleFling's SMTP account (currently
  `galefling@rin-city.com`, a dedicated mailbox with 2FA and an app password —
  see [docs/plans/completed/SCHEDULING.md#email-configuration](plans/completed/SCHEDULING.md#email-configuration)
  for why a dedicated account rather than a personal one). Arrives via the
  same [credential import JSON](CREDENTIALS.md) mechanism as Meta,
  Twitter, and AWS credentials — never hand-typed.
- **Notification email address** — not a secret. The address that should
  *receive* the notifications. Set this yourself, either during first-run
  setup or later in Settings.

## Setting it up

### SMTP credentials (administrator-provided)

Add an `smtp` section to the credential import JSON alongside `meta`,
`twitter`, and `aws`:

```json
{
  "version": 1,
  "smtp": {
    "host": "smtp.gmail.com",
    "port": 587,
    "username": "galefling@rin-city.com",
    "app_password": "<app password>"
  }
}
```

`port` defaults to `587` (STARTTLS) if omitted. Port `465` (implicit TLS) is
also supported. Import via **Setup Wizard → App Credentials** (first run) or
**Settings → Advanced → Import Credentials from JSON** (later). Both accept
partial files — importing just an `smtp` section, or `smtp` alongside other
sections, works the same way.

Check a credential file against what's already stored with
`tools/validate_import_file.py path/to/creds_import.json` before importing —
see [docs/platforms/META_APPS.md](platforms/META_APPS.md) for details on that
tool. It never prints a credential value.

### Notification email address (yours to set)

- **Setup Wizard → App Credentials** has a "Notification email" field,
  right below the credential import button. Optional — leave it blank and
  set it later if you'd rather.
- **Settings → Advanced → Email Notifications** has the same field, editable
  any time.

### Testing

**Settings → Advanced → Email Notifications → Test Connection** always sends
a real, clearly-labeled test email to the configured notification address —
this proves the whole path (login *and* delivery), not just that
authentication succeeds. It requires both a notification email address and
imported SMTP credentials; either missing produces a specific warning
explaining which one to fix.

## Storage

SMTP credentials are stored via `AuthManager` (`smtp_auth.json` in the app's
auth directory), the same mechanism and file-per-credential-set pattern as
every other imported credential — see `src/core/auth_manager.py`. The
notification email address is stored via `ConfigManager` (`notification_email`
in `app_config.json`) since it isn't a secret, alongside other plain settings
like the log-upload endpoint.

## Gmail specifics

If the SMTP account is a Google Workspace / Gmail mailbox:

- `smtp.gmail.com`, port `587` with STARTTLS (or `465` implicit TLS).
- **An App Password is required** — Google removed plain-password SMTP
  access. Generating one requires 2-Step Verification on the account.
- The `From:` header is rewritten to the authenticated account unless a
  verified alias is used.
- Free-account sending limits are around 500 messages/day — irrelevant at
  GaleFling's notification volume.

## References

- `docs/CREDENTIALS.md` — the full credential import JSON schema (all sections, not
  just `smtp`), partial-import behavior, and versioning
- `src/core/smtp_utils.py` — `check_smtp_connection()` and the shared email sender
- `src/core/auth_manager.py` — `get_smtp_credentials()` / `save_smtp_credentials()`
- `src/core/credential_importer.py` — the `smtp` import section
- `docs/plans/completed/SCHEDULING.md#email-configuration` — the design rationale (SMTP
  over SES, dedicated mailbox, per-host App Passwords)
