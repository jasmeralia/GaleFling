# Chrome DevTools Remote Debugging

GaleFling's embedded browsers (QtWebEngine/Chromium) can expose a remote
debugging endpoint, giving you full Chrome DevTools access to inspect DOM,
console output, network traffic, and JavaScript state inside any WebView
session.

This is a developer/operator tool — do not enable it in production or leave
it on longer than needed.

---

## Enabling Remote Debugging

1. Open **Settings → Advanced**.
2. Under **WebView**, check **Enable remote debugging (Chrome DevTools Protocol)**
   and set the port (default **9222**).
3. Click **Save**. A restart-required notice will appear.
4. Restart GaleFling.
5. On startup, if the port is already in use, a warning dialog will appear —
   choose a different port and restart again.

> The setting persists across restarts until you explicitly disable it.
> A warning banner appears on every launch as a reminder.
> Disable it when you are done.

---

## Connecting DevTools

With GaleFling running, open a Chromium-based browser (Chrome, Edge, Brave)
and navigate to:

```
chrome://inspect
```

Under **Remote Target**, click **Configure…** and add `localhost:9222` (or
whichever port you set). Any open GaleFling WebView tabs will appear as
inspectable targets. Click **inspect** next to the one you want.

Alternatively, navigate directly to `http://localhost:9222` to see the raw
JSON target list.

---

## Troubleshooting: OnlyFans MFA Checkbox

### Background

OnlyFans renders its 2FA "remember me" checkbox as a Vue.js custom component
(`.b-chckbox`). In the embedded WebView the native `<input type="checkbox">`
is hidden and clicks are absorbed by decorator `<span>` and icon elements
before reaching the input. GaleFling injects a MutationObserver script
(`galefling_onlyfans_checkbox_fix`) to work around this, but the fix may
not cover all cases — particularly when a Cloudflare Turnstile challenge is
active on the same page.

### What to Capture

After connecting DevTools to the OnlyFans WebView tab, reproduce the MFA
flow and collect the following:

#### 1. Console output

The injected script already emits diagnostic lines. In the **Console** tab,
filter by `[GaleFling]` to isolate them:

```
[GaleFling] checkbox found class=... disabled=... display=... visibility=... pointerEvents=... opacity=...
[GaleFling] CF iframe w=... h=... pos=... z=...
[GaleFling] forwarded click to checkbox, checked=...
```

Copy all `[GaleFling]` lines and note whether `forwarded click` ever appears
when the checkbox is clicked.

#### 2. Element inspection

In the **Elements** tab, find the 2FA form. Locate the `.b-chckbox` wrapper
and its `<input type="checkbox">` child. Check and record:

- `pointer-events` on `.b-chckbox`, `.b-chckbox__icon`, `.b-chckbox__label`,
  and the `<input>` itself (Computed tab → filter `pointer`)
- `z-index` and `position` of any ancestor with `position: relative/absolute`
  (Computed tab → filter `z-index`)
- Whether any `<iframe>` from `challenges.cloudflare.com` or `turnstile` sits
  in the stacking context above the checkbox (Layers panel or 3D view)

#### 3. Event tracing

In the **Console**, run the following after the 2FA form is visible:

```js
document.querySelectorAll('input[type="checkbox"]').forEach(el => {
    el.addEventListener('click', e => console.log('[manual] click', e.target, 'checked=', e.target.checked), true);
    el.addEventListener('change', e => console.log('[manual] change', e.target, 'checked=', e.target.checked), true);
});
```

Then try clicking the checkbox. If neither `[manual] click` nor `[manual]
change` fire, the click is being swallowed above the input in the DOM — note
which element the DevTools **Event Listeners** panel shows as the top
handler.

#### 4. Network tab — HAR export

If the issue seems related to Cloudflare challenge timing (checkbox appears
disabled until the challenge resolves):

1. Switch to the **Network** tab before navigating to the 2FA step.
2. Enable **Preserve log**.
3. Reproduce the MFA flow.
4. Right-click any request → **Save all as HAR with content**.

Include the HAR file when reporting — it shows whether the Turnstile
challenge response arrives before or after the checkbox is rendered.

### What to Send

When reporting the issue to Jas, include:

- All `[GaleFling]` console lines
- A screenshot of the `.b-chckbox` element in the Elements panel with the
  Computed styles expanded
- Output of the manual event listener snippet above
- The HAR file if Cloudflare timing is suspected
- GaleFling app log (Help → View Logs or the `logs/` folder in the app data
  directory)
