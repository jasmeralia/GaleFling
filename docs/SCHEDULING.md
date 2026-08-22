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
to see pending posts in due-time order. **Edit** loads an item back into the composer;
use the calendar again to save its revised caption, media, accounts, or due time.
**Cancel** permanently removes it after confirmation.

The queue is stored in `scheduled_posts.sqlite3` under GaleFling's app data directory.
GaleFling owns copies of queued media under `scheduled_media/`, so moving the source
file after scheduling does not break the queued post.

## Reboots and missed posts

GaleFling has to be running at the due time. Under **Settings → Advanced → Startup**,
enable **Start GaleFling automatically when I log in** and choose whether that automatic
launch opens the main window or starts minimized in the tray. This setting is specifically
for recovering after a reboot; being away from a still-running computer does not prevent
the scheduler from working. A manual launch always opens normally.

If a pending item's due time passed while GaleFling was closed, startup reconciliation
offers **Post Now**, **Edit**, or **Delete**, plus **Post All Remaining** when applicable.
Closing the reconciliation window leaves all undecided items pending and asks again on the
next launch. Interrupted `in_flight` items are also recovered to `pending` at startup.

## Failures

Platform failures stay isolated: one account failing does not stop the other selected
accounts. GaleFling records the item as failed, logs the outcome, and shows one consolidated
system notification naming the failed accounts. Clicking it opens the standard results
dialog. If SMTP credentials and a notification address are configured, GaleFling also
sends one durable failure email. Email and system notifications are best-effort and neither
changes the recorded posting result.

See [Email Notifications](EMAIL_NOTIFICATIONS.md) to configure and test SMTP delivery.
