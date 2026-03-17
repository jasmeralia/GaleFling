# Release Testing (Pre-release to Stable)

This document defines the recommended manual user testing scenarios that should pass before promoting a pre-release build to **stable**.

## Goal

Validate that a real user can install, configure, post, update, recover from errors, and send useful diagnostics without developer intervention.

## Test Environment

- OS: Windows 10 and Windows 11 (at least one run on each before stable)
- Build under test: latest pre-release installer from GitHub Releases
- Network conditions:
  - Normal broadband connection
  - Temporary offline/disconnected state for failure testing
- Accounts prepared:
  - Twitter (1-2 accounts)
  - Bluesky (1-2 accounts)
  - Instagram (1-2 accounts)
  - Snapchat (WebView login)
  - OnlyFans (WebView login)
  - Fansly (WebView login)
  - FetLife (WebView login)

## Test Data Pack

Prepare files for repeatable tests:

- `small.jpg` (standard JPEG)
- `wide.png` (landscape PNG)
- `portrait.png` (portrait PNG)
- `static.webp` (static WEBP)
- `animated.gif` (multi-frame GIF)
- `small.mp4` (short < 30s video)
- `long.mp4` (longer video that may exceed platform limits)
- `unsupported-video.ext` (for format rejection checks)
- 5+ image files to test attachment limits

## Release Gate (Must Pass)

- No crashes in tested flows.
- No data-loss regressions (draft, settings, session persistence).
- All critical posting paths function for at least one account per platform type:
  - API platforms: Twitter, Bluesky, Instagram
  - WebView platforms: Snapchat, OnlyFans/Fansly/FetLife
- Log submission works and contains actionable metadata.
- Installer and update flows complete without requiring manual file surgery.

## Manual Scenario Checklist

Use this as a pass/fail checklist in each pre-release cycle.

### 1) Install, Launch, and Uninstall

- Clean install from installer.
- Launch app from Start Menu shortcut.
- Confirm app icon, window title, and version appear correctly.
- Uninstall from Apps/Programs.
- Reinstall over previous install (upgrade-style path) and verify app still launches.

### 2) First-Run Setup Wizard

- Run first-launch setup wizard end-to-end.
- Validate required fields enforce input.
- Validate successful credential save for API platforms.
- Validate WebView login capture for WebView platforms.
- Cancel setup midway, reopen setup, and confirm app remains usable.

### 3) Settings and Account Management

- Open Settings and verify each platform tab loads.
- Add/edit/remove accounts (where supported).
- Verify duplicate/conflicting account validations.
- Test logout/clear credentials per platform.
- Verify saved settings persist after app restart.

### 4) Core Composer Behavior

- Text-only post with no media.
- Empty post attempt shows proper blocking/validation.
- Character counters appear and update for limited platforms.
- Text warnings appear for platforms that do not support text.

### 5) Media Attachment Workflows

- Attach one image, remove it, re-attach a different image.
- Attach multiple images up to allowed app max.
- Attempt to attach beyond max and verify UX handling.
- Attach one video and verify media list/preview behavior.
- Mix unsupported combinations and verify clear user messaging.

### 6) Format Restriction and Conversion Behavior

- Attach `static.webp` with platforms selected that do not accept WEBP.
- Verify static image is auto-converted when possible and platform stays enabled.
- Attach `animated.gif` and verify unsupported platforms are restricted.
- Attach unsupported video format and verify relevant restrictions.
- Snapchat specific:
  - Single static image attached: verify Snapchat remains usable and conversion to MP4 occurs.
  - Multiple images attached: verify Snapchat is disabled by attachment-count restriction.

### 7) Preview and Processing

- Open media preview with 1 image and with multiple images.
- Confirm per-platform processing previews render.
- Cancel preview and verify no unintended posting occurs.
- Confirm retry/reopen preview reuses processed media correctly.

### 8) Posting Flows (Success Paths)

- API-only selection (Twitter/Bluesky/Instagram): verify silent post flow and results.
- WebView-only selection: verify panel opens, prefill behavior works, and manual confirmation path completes.
- Mixed API + WebView selection: verify API posts first, then WebView panel opens, and results combine correctly.
- Confirm resulting links/statuses appear correctly in Results dialog.

### 9) Posting Flows (Failure/Recovery Paths)

- Network disconnect before posting: verify error handling and no app crash.
- Auth-expired or invalid credentials scenario: verify actionable error/result.
- Platform-side rejection scenario (duplicate/rate-limit if reproducible): verify clear status.
- From failed results dialog, test "Send Logs to Jas" flow.

### 10) Draft Auto-save and Restore

- Create draft with text + media + selected platforms.
- Close app and relaunch; verify restore prompt appears and works.
- Verify both restore and discard paths.
- Confirm successful post clears the current draft.

### 11) Logging, Diagnostics, and Support

- Trigger an error and send logs via Help > Send Logs to Jas.
- Confirm success message path.
- Confirm failure path shows copyable error details.
- Confirm logs include environment metadata and ffmpeg version.
- Version sanity cutoff test:
  - Using an older client build (< `1.5.1`), attempt log submission.
  - Verify server rejection and app guidance to upgrade + retest before sending logs.

### 12) About and Version Surfaces

- Help > About opens correctly.
- Confirm app version displays correctly.
- Confirm ffmpeg version is shown in About.

### 13) Update Flow

- Help > Check for Updates path when up-to-date.
- Update available path:
  - Download prompt displays expected version.
  - Installer download completes.
  - Installer launches correctly.
- Restart after update and verify app version changed as expected.

### 14) UI/UX Stability and Regression Sweep

- Resize main window and verify layout stability.
- Verify dark/light/system theme switching.
- Verify no clipped labels or hidden controls at common window sizes.
- Confirm menu actions still function:
  - Settings > Open Settings
  - Settings > Run Setup Wizard
  - Help > About
  - Help > Check for Updates
  - Help > Send Logs to Jas
  - Help > Clear Logs

## Platform Smoke Matrix (Minimum)

For stable promotion, run at least one successful post scenario per platform:

- Twitter: text-only and text+media
- Bluesky: text-only and text+media
- Instagram: media post with caption
- Snapchat: single image conversion path and one direct video post
- OnlyFans: WebView prefill and manual submit
- Fansly: WebView prefill and manual submit
- FetLife: WebView prefill and manual submit

## Sign-off Template

Record this before moving pre-release to stable:

- Build tested:
- Tester:
- Date:
- Environments tested:
- Blocking issues found:
- Non-blocking issues found:
- Recommendation: Promote to stable / Hold release

