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

## Troubleshooting: OnlyFans WebView (legacy checkbox notes)

> **Historical context.** Earlier builds debugged an OnlyFans **2FA "remember this
> device" checkbox** during embedded login. That flow is **obsolete**: GaleFling no
> longer logs in to OnlyFans (reCAPTCHA blocks embedded browsers; sessions are
> imported via `auth.json`). Phase 6 functional tests do **not** include standing
> OnlyFans checkbox coverage — interaction tests are added only if a functional test
> demonstrates a real composer checkbox failure.

GaleFling still injects a legacy MutationObserver script
(`galefling_onlyfans_checkbox_fix`) on every OnlyFans WebView. It was written for the
unreachable login/2FA path. Use the procedure below **only** when diagnosing a
**reproducible** composer checkbox problem (functional test failure or confirmed manual
repro on current builds) — not as routine setup.

### What to Capture

After connecting DevTools to the OnlyFans WebView tab, reproduce the problem and
collect the following:

#### 1. Console output

The injected script emits diagnostic lines. In the **Console** tab, filter by
`[GaleFling]`:

```
[GaleFling] OF checkbox found class=... disabled=... display=... visibility=... pointerEvents=... opacity=...
[GaleFling] CF iframe w=... h=... pos=... z=...
[GaleFling] OF forwarded container click, checked=...
```

Copy all `[GaleFling]` lines and note whether a forwarded click ever appears when
the checkbox is clicked.

#### 2. Element inspection

In the **Elements** tab, find the form containing the checkbox. Locate the
`.b-chckbox` wrapper and its `<input type="checkbox">` child. Check and record:

- `pointer-events` on `.b-chckbox`, `.b-chckbox__icon`, `.b-chckbox__label`,
  and the `<input>` itself (Computed tab → filter `pointer`)
- `z-index` and `position` of any ancestor with `position: relative/absolute`
- Whether any `<iframe>` from `challenges.cloudflare.com` or `turnstile` sits
  above the checkbox (Layers panel or 3D view)

#### 3. Event tracing

In the **Console**, run the following once the checkbox is visible:

```js
document.querySelectorAll('input[type="checkbox"]').forEach(el => {
    el.addEventListener('click', e => console.log('[manual] click', e.target, 'checked=', e.target.checked), true);
    el.addEventListener('change', e => console.log('[manual] change', e.target, 'checked=', e.target.checked), true);
});
```

Then try clicking the checkbox. If neither `[manual] click` nor `[manual]
change` fire, the click is being swallowed above the input in the DOM.

#### 4. Network tab — HAR export

If Cloudflare timing is suspected:

1. Switch to the **Network** tab before reproducing the problem.
2. Enable **Preserve log**.
3. Reproduce the interaction.
4. Right-click any request → **Save all as HAR with content**.

### What to Send

When reporting a confirmed issue, include:

- All `[GaleFling]` console lines
- A screenshot of the checkbox element with Computed styles expanded
- Output of the manual event listener snippet above
- The HAR file if Cloudflare timing is suspected
- GaleFling app log (Help → View Logs or the `logs/` folder in the app data
  directory)
