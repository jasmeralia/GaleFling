# GaleFling Debug State

## Issue Summary

FetLife and OnlyFans "remember me" checkboxes appear visually unchecked after clicking, even though the underlying state change is functional. FetLife is confirmed working at the data layer; OnlyFans state persists post-tick but 2FA submission not yet confirmed.

## Reproduction Steps

1. Install latest build and open GaleFling
2. Open FetLife login (Settings → FetLife → Log In)
3. Click the "Remember me" checkbox — observe it does not appear checked
4. Submit login form
5. Open OnlyFans login, proceed to 2FA screen
6. Click the "Remember this device" checkbox — observe visual state

## Observed Behavior

- FetLife: checkbox appears visually unchecked after clicking, but `user[remember_me]=1` IS sent in the form POST body
- OnlyFans: checkbox state now persists through Vue re-renders (`checked=true` confirmed post-tick), but visual fill may not update if `.b-input-radio__label` selector doesn't match

## Expected Behavior

- FetLife: checkbox should visually appear checked after clicking (FetLife's custom styled element should reflect state)
- OnlyFans: custom checkbox visual should turn blue when checked; `remember_me: true` should appear in the 2FA API request body

------------------------------------------------------------------------

## Current Hypotheses (MAX 5)

1. [High] FetLife visual broken by injected CSS — `opacity:1; position:static` renders native browser checkbox alongside FetLife's custom element, disrupting layout so the custom element never updates. Fix committed (CSS reduced to `pointer-events: auto` only) but not yet built/installed.
2. [Medium] OnlyFans `syncVisual` silently failing — `.b-input-radio__label` selector may not match actual DOM structure; no log confirmation the color update runs. Need a console.log inside syncVisual to verify.
3. [Low] OnlyFans 2FA API call unconfirmed — user did not submit the 2FA form during the logged session; fetch interceptor presence is unverified at submission time.

> Remove invalidated hypotheses each cycle. Do NOT let this grow.

------------------------------------------------------------------------

## Evidence (Relevant Only)

- `[GaleFling] FetLife checkbox change dispatched, checked=true`
- `[GaleFling] FetLife checkbox post-tick (Vue re-render window), checked=true` ← Vue accepted
- `[GaleFling] FetLife form-submit FormData: ... user[remember_me]=1` ← confirmed sent
- `[GaleFling] OF checkbox change dispatched, checked=true`
- `[GaleFling] OF checkbox post-tick (Vue re-render window), checked=true` ← Vue accepted
- Subsequent OF MutationObserver callbacks: `checked=true` ← persists (old `input.click()` would reset to false)
- OF checkbox `opacity=0` throughout — hidden, custom visual drives appearance
- FetLife post-login: many `name=toggle id=` checkbox log entries — unrelated page toggles, not the remember-me input

------------------------------------------------------------------------

## What Has Been Tried

- Attempt 1 (pre-session): `input.click()` on OnlyFans — Vue reset checked=false on re-render. Failed.
- Attempt 2: FetLife CSS `opacity:1; position:static` — made native input visible but broke layout; custom element never updated. Visually broken.
- Attempt 3 (current): `triggerFrameworkChange` (prototype setter + input/change events) for both platforms — Vue state confirmed accepted post-tick. Functionally correct.
- Attempt 4 (committed, not built): Remove aggressive FetLife CSS, keep only `pointer-events:auto`. Expected to fix visual.

------------------------------------------------------------------------

## Files / Components of Interest

- `src/platforms/fetlife.py` — `_inject_checkbox_fix` (CSS injection + click intercept)
- `src/platforms/onlyfans.py` — `_inject_2fa_checkbox_fix` (triggerFrameworkChange + syncVisual + fetch interceptor)

------------------------------------------------------------------------

## Current Build Info

- App version: 1.7.11 (constants.py bumped, not yet built with FetLife CSS fix)
- Log analyzed: `app_20260320_083314.log`
- Run timestamp: 2026-03-20 08:33–08:35

------------------------------------------------------------------------

## Next Step (SINGLE ACTION)

Build and install 1.7.11 with the FetLife CSS fix, then test FetLife login visually to confirm the native checkbox no longer appears. If still broken, add `console.log` inside OnlyFans `syncVisual` before the next session.

------------------------------------------------------------------------
