# OnlyFans Session Import

OnlyFans login no longer works reliably inside GaleFling because reCAPTCHA Enterprise rejects
authentication from the embedded Qt WebEngine browser. Instead, log in with a normal browser,
export the authenticated session to an `auth.json` file, and import that file into GaleFling.
OnlyFans' own site still composes and publishes the post inside GaleFling after import.

## Obtain `auth.json`

While logged in to OnlyFans in a normal browser, export the session with the
[OF-DL Auth Helper](https://github.com/whimsical-c4lic0/OF-DL-Auth-Helper) browser
extension. It is available for Firefox and for Chromium-based browsers (Chrome, Brave,
Edge, Vivaldi, Opera). Open the extension popup once OnlyFans has finished loading, then
use its download option to save `auth.json`.

Store the exported file somewhere private. It contains session credentials that provide access to
the OnlyFans account. Do not share it or attach it to a support request.

## File format

The import expects exactly these four top-level keys:

```json
{
  "USER_ID": "<auth_id cookie value>",
  "USER_AGENT": "<capturing browser's navigator.userAgent>",
  "X_BC": "<40-character bcTokenSha value>",
  "COOKIE": "auth_id=<auth_id cookie value>; sess=<session cookie value>;"
}
```

The `auth_id` and `sess` cookie pairs may appear in either order. Do not edit the exported values
or reformat the cookie string by hand.

## Import the session

1. Log in to OnlyFans in a normal browser.
2. Export a fresh `auth.json` using the OF-DL Auth Helper extension.
3. Open GaleFling and select **Settings**.
4. Open the **OnlyFans** tab.
5. For the intended account, select **Import Session from auth.json...**.
6. Select the exported JSON file.
7. Wait for GaleFling to confirm that the session was imported and verified.

The imported session is stored separately for each configured GaleFling account.

## Troubleshooting

### The export may be stale

Log in to OnlyFans again in the normal browser, create a new export, and import the new file. Avoid
reusing an older export after logging out, changing the password, or revoking browser sessions.

### “Session expired” appears immediately after import

Confirm that the export was captured after a successful OnlyFans login. Then export it again and
repeat the import. If the account has multiple active browser sessions, use the newest export from
the browser where OnlyFans is currently open and authenticated.

### The exporting browser changed

An imported session is tied to the exact user agent of the browser that created it. GaleFling saves
and uses that user agent automatically. Exporting again from a different browser is fine because the
new export includes its matching user agent; editing `auth.json` by hand is not.
