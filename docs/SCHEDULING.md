# Scheduling

GaleFling can keep several future posts in a local queue and publish them through the
same platform adapters and media-processing outputs used by **Post Now**.

## Schedule a post

1. Write the caption, attach media, and select accounts in the composer.
2. Click the 30×30 **calendar icon** immediately left of the emoji picker.
3. Choose a date and time at least five minutes in the future. The calendar button opens
   a real calendar popup; the adjacent combined field also lets you edit its date or time
   sections directly.
4. Click **Schedule Post**. GaleFling copies the original and processed media into its app
   data directory, clears the composer, and shows a confirmation toast.

Twitter, Bluesky, Instagram, Threads, and Facebook Page accounts can be scheduled.
Snapchat, OnlyFans, Fansly, and FetLife are excluded because their WebView posting flows
require a person to confirm them.

## Manage the queue

Use **Scheduled → View Scheduled Posts…** (or **Scheduled Posts (N)** in the tray menu)
to see pending posts in due-time order, plus a **Recent Activity** section for posts that
have already been attempted:

- **Pending**: **Edit** loads the item back into the composer so the calendar can save a
  revised caption, media, accounts, or due time. **Cancel** permanently removes it after
  confirmation.
- **Posted**: **View Results** reopens the standard results dialog with each account's
  post link. **Dismiss** removes the record after confirmation.
- **Failed**: **View Results**, **Edit & Retry**, and **Dismiss** — see below.

The queue is stored in `scheduled_posts.sqlite3` under GaleFling's app data directory.
GaleFling owns copies of queued media under `scheduled_media/`, so moving the source
file after scheduling does not break the queued post.

## Reboots and missed posts

GaleFling has to be running at the due time. Under **Settings → Advanced → Startup**,
enable **Start GaleFling automatically when I log in** and choose whether that automatic
launch opens the main window or starts minimized in the tray. This setting is specifically
for recovering after a reboot; being away from a still-running computer does not prevent
the scheduler from working. A manual launch always opens normally. If the selected desktop
does not provide a usable system tray, GaleFling opens its main window instead of starting
invisibly. Linux AppImage launches store the persistent AppImage file path in the login
entry rather than its temporary mounted executable path.

If a pending item's due time passed while GaleFling was closed, startup reconciliation
offers **Post Now**, **Edit**, or **Delete**, plus **Post All Remaining** when applicable.
Closing the reconciliation window leaves all undecided items pending and asks again on the
next launch. Interrupted `in_flight` items are also recovered to `pending` at startup.

## Failures and partial success

Platform failures stay isolated: one account failing does not stop the other selected
accounts, and a post with a mix of successes and failures is recorded as **failed** —
GaleFling never silently discards which accounts actually went out. It logs the outcome
and shows one consolidated system notification naming only the failed accounts. Clicking
it, or the tray icon's **Scheduled Posts** menu item, opens the standard results dialog
showing every account's outcome, including links for the ones that already succeeded.
If SMTP credentials and a notification address are configured, GaleFling also sends one
durable failure email. Email and system notifications are best-effort and neither changes
the recorded posting result. Optionally, **Settings → Advanced → SMTP → Also email me when
a scheduled post succeeds** sends the same kind of email — with each account's link — when
a scheduled post fully succeeds.

**Edit & Retry** on a failed post reopens the composer with only the still-failed accounts
selected; accounts that already succeeded are shown locked (their status pill reads
"Posted ✓") so a retry cannot accidentally double-post to them. Clicking a locked account
anyway prompts for confirmation — the one legitimate reason to override it is having
deleted the original post on that platform. Retrying only ever re-attempts the accounts
you leave selected; every other account's earlier result is carried forward unchanged, and
the post only becomes **posted** once every account it has ever been attempted for has
succeeded.

The tray icon shows two small corner badges, cleared or shown independently of each other:
an accent dot (bottom-left) while any post is pending, and a danger dot (bottom-right) for
an unseen scheduling failure. The failure badge clears the moment you open **Scheduled
Posts**, whether or not the failure has actually been fixed yet.

See [Email Notifications](EMAIL_NOTIFICATIONS.md) to configure and test SMTP delivery.
