# QA Testing Guide

Human validation steps for a new GaleFling release. Work through these in order. Note any failures and report them before signing off.

---

## Test Environment Setup

Install the release build from the installer (not from source). Use a clean Windows 10 or Windows 11 machine, or a profile that has not previously run this version. Prepare the following test media files before starting:

- A standard JPEG image
- A landscape PNG image
- A portrait PNG image
- A static WEBP image
- An animated GIF
- A short MP4 video (under 30 seconds)
- A longer MP4 video that may exceed platform duration limits
- A video file in an unsupported format (e.g. `.mkv` or `.avi`)
- Five or more image files for attachment-limit testing

Have at least one active account available for each platform type: Twitter, Bluesky, Instagram, Threads, Facebook Page, Snapchat, OnlyFans, Fansly, and FetLife.

---

## 1. Install and Launch

Run the installer and complete it. Launch the app from the Start Menu shortcut. Verify the window title, app icon, and version number in Help > About all reflect the expected release. Then uninstall the app from Windows Apps/Programs and confirm the uninstall completes cleanly. Reinstall using the same installer and verify the app launches again after reinstall.

---

## 2. First-Run Setup Wizard

On first launch after a clean install, the setup wizard should start automatically. Work through it end-to-end. Verify that required fields block progression when empty. Save credentials for at least one API platform and complete WebView login for at least one WebView platform. Midway through a second run of the wizard (via Settings > Run Setup Wizard), cancel out and confirm the app is still usable and settings from the first run are intact.

---

## 3. Account Management

Open Settings and navigate through each platform tab. Add a second account on a platform that allows two (e.g. Twitter or Bluesky). Attempt to add a third account on a platform capped at two and confirm the UI prevents it. Remove an account and verify it no longer appears in the composer. Edit credentials on an existing account and save. Restart the app and confirm all account changes persisted.

---

## 4. Composer — Text Behavior

Open the composer with no accounts selected and attempt to post. Confirm the app blocks the action. Select accounts and attempt to post with no text and no media. Confirm appropriate blocking. Type text into the composer with a character-limited platform selected (Twitter at 280, Bluesky at 300, Threads at 500) and verify the counter appears and updates correctly. Type a long caption and verify that platforms with no text support (Snapchat) or text-with-media restrictions display appropriate warnings or disable correctly.

---

## 5. Media Attachment Workflows

Attach a single image, then remove it and attach a different one. Attach multiple images up to the app's allowed maximum and verify each appears in the media list. Attempt to attach one more image beyond the maximum and verify the app handles this gracefully without crashing. Attach a video and confirm it appears correctly in the media list. Attempt a combination the app does not allow (e.g. mixing images and video) and verify clear user messaging.

---

## 6. Format Restrictions and Auto-Conversion

Attach the static WEBP image with Bluesky selected (Bluesky does not accept WEBP). Verify the app auto-converts it to JPEG and Bluesky remains enabled. Attach the animated GIF with platforms that do not support GIF selected and verify those platforms are disabled with a visible reason. Attach the unsupported video format and confirm that platforms requiring MP4 are restricted accordingly.

For Snapchat specifically: attach a single static image and verify Snapchat remains available and the image is auto-converted to MP4 before submission. Then attach two or more images and verify Snapchat is disabled due to the attachment-count restriction.

---

## 7. Preview and Processing

Open the preview dialog with a single image attached. Confirm each platform's processing preview renders. Close the preview without posting and verify nothing is posted. Re-open preview with multiple images and verify all previews render. After closing and re-opening preview, confirm previously processed media is reused and not reprocessed from scratch.

---

## 8. Posting — Success Paths

Post text-only to API platforms only (e.g. Twitter and Bluesky with no media). Confirm silent background posting completes and the Results dialog shows correct statuses and links. Post text plus media to a WebView platform only and verify the WebView panel opens, text and media are prefilled, and the manual submission flow completes. Post to a mixed selection of API and WebView platforms and verify API platforms post first, the WebView panel then opens for remaining platforms, and the final Results dialog combines both sets of outcomes.

---

## 9. Posting — Failure and Recovery Paths

Disconnect the network connection before posting. Attempt to post and verify the app handles the failure without crashing, and that the Results dialog shows an error state rather than a false success. Revoke or invalidate credentials for one API platform account, then attempt to post to it. Verify the result shows a clear auth error rather than a crash. From the Results dialog with at least one failure showing, use the "Send Logs to Jas" action and verify the flow completes or shows a recoverable error.

---

## 10. Draft Auto-Save and Restore

Compose a post with text, one or more media files, and several platforms selected. Close the app without posting. Relaunch and confirm the restore prompt appears. Accept the restore and verify text, media, and platform selections are all recovered. Close again, relaunch, and this time decline the restore. Confirm the composer opens empty. After a successful post, relaunch the app and confirm no stale draft restore prompt appears.

---

## 11. Logging and Diagnostics

From Help > Send Logs to Jas, submit logs after a test run that included at least one error. Confirm the success path shows a confirmation. Simulate a failure (e.g. disconnect network before submitting) and confirm the failure path shows copyable error details rather than crashing. Open Help > About and confirm the ffmpeg version is displayed alongside the app version.

---

## 12. Update Flow

From Help > Check for Updates, confirm the "up to date" path shows a clean message with no crash. If a newer build is available in the pre-release channel, verify the update prompt shows the expected new version, the installer download completes, and the installer launches. After update and restart, confirm the version shown in Help > About reflects the updated version.

---

## 13. UI and Layout Stability

Resize the main window to a narrow width and a tall height and confirm no controls are clipped or hidden. If the app supports theme switching (dark/light/system), toggle each mode and verify the UI renders correctly. Confirm every item in the menu bar triggers the expected action:

- Settings > Open Settings
- Settings > Run Setup Wizard
- Help > About
- Help > Check for Updates
- Help > Send Logs to Jas
- Help > Clear Logs

---

## Platform Smoke Matrix

Before signing off on a release, run at least one successful end-to-end post for each of the following:

- **Twitter** — text-only post, then text + image
- **Bluesky** — text-only post, then text + image
- **Instagram** — single image with caption
- **Threads** — text-only post, then text + image
- **Facebook Page** — text + image post
- **Snapchat** — single static image (auto-converted to MP4), then a direct short video post
- **OnlyFans** — WebView prefill with text + image, manual submit
- **Fansly** — WebView prefill with text + image, manual submit
- **FetLife** — WebView prefill, manual submit

---

## Sign-Off

Record the following before approving the release:

- Build version tested
- Tester name
- Date tested
- Windows versions covered
- Any blocking issues found
- Any non-blocking issues found
- Recommendation: promote to stable or hold
