# Setup Wizard Walkthrough

A step-by-step look at GaleFling's first-run setup wizard. Every account
handle, API key placeholder, and status shown below is fake sample data —
this walkthrough is generated offscreen against a throwaway config
directory with no real credentials involved, using
`tools/screenshots/generate_wizard_step_screenshots.py`.

The wizard is skippable at every step — connect only the platforms you
actually use, and revisit any of them later from **Settings**.

## 1. Welcome

![Welcome step](images/wizard-steps/01-welcome.png)

## 2. App Credentials

Import the app-level credentials JSON your administrator provides — Meta,
Twitter, AWS media staging, and SMTP all arrive in one file. Also where you
set the address that should receive email notifications, if you want that
ready ahead of when scheduling ships. See
[docs/CREDENTIALS.md](CREDENTIALS.md) for the full format.

![App Credentials step](images/wizard-steps/02-credentials.png)

## 3. Twitter

Twitter's PIN-flow OAuth: click **Start PIN Flow**, authorize in the browser
tab that opens, copy the 7-digit PIN back in. Supports two accounts.

![Twitter step](images/wizard-steps/03-twitter.png)

## 4. Bluesky

App passwords only — never the main account password. Also supports a
second account.

![Bluesky step](images/wizard-steps/04-bluesky.png)

## 5. Threads

Connects via Meta OAuth once the app credentials from step 2 are imported.
Each account must accept this app's Threads Tester invitation first — see
[docs/platforms/META_APPS.md](platforms/META_APPS.md#tester-roles-while-apps-are-in-development).

![Threads step](images/wizard-steps/05-threads.png)

## 6. Instagram

Same Meta OAuth connect flow as Threads, its own Tester invitation.

![Instagram step](images/wizard-steps/06-instagram.png)

## 7. Facebook Page

Also Meta OAuth, but connects a Page rather than a personal profile — see
[docs/platforms/FACEBOOK.md](platforms/FACEBOOK.md).

![Facebook Page step](images/wizard-steps/07-facebook.png)

## 8. FetLife

WebView-based — log in now to save session cookies, or skip and log in
later from the composer.

![FetLife step](images/wizard-steps/08-fetlife.png)

## Regenerating these screenshots

After a wizard UI change:

```bash
.venv/bin/python tools/screenshots/generate_wizard_step_screenshots.py docs/images/wizard-steps
```

Writes `NN-<step-name>.png` for every page in wizard order, overwriting
this directory. Offscreen-rendered against a throwaway temp `HOME`, so it
never touches real config or credentials.
