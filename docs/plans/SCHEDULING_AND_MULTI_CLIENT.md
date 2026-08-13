# GaleFling — Scheduling & Multi-Client Architecture

## Status

**Draft — Phase 0 not started.** Supersedes `docs/plans/ANDROID_PORT.md`, which framed
this work as an Android/iOS port of the desktop app. That framing was wrong; see
[Why this is not a port](#why-this-is-not-a-port). The mobile-port feasibility analysis
is preserved in [Appendix A](#appendix-a--mobile-native-port-analysis-deferred).

Canonical repo path: `docs/plans/SCHEDULING_AND_MULTI_CLIENT.md`

---

## Executive summary

Rin asked for two things that were not on the roadmap: **posting from her phone**, and
**scheduled posts**. The first reads as "port the app to mobile." It isn't. Taken
together with the second, the correct response is a **topology change, not a rewrite**:

| Component | Runs on | Status |
|-----------|---------|--------|
| **GaleFling desktop** — the whole app: composer, posting, media pipeline, scheduler, **and the HTTPS server that serves mobile clients** | Windows or Linux, always-on (Rin: Win11, 24×7) | Existing app + scheduler + embedded server |
| **PWA client** | iPhone, Android tablet, any browser — served *by the desktop app itself, directly over the LAN* | New |

**There is no relay, no VPN, and no hosted component.** Rin's desktop is on the router by
ethernet and her phone by wifi; they talk to each other directly. Off-LAN access is
explicitly out of scope — see [Out of scope](#out-of-scope).

The decisive constraint is that **scheduled posting cannot run on a phone**. Android's
WorkManager schedules into maintenance windows, not at times; iOS `BGTaskScheduler` is
explicitly opportunistic with no timing guarantee and does not run at all after a force
quit. The WebView tier additionally needs a live browser rendering a DOM, which neither
mobile OS permits from a background task. Something that is already always-on has to do
the posting — and Rin's desktop already is.

Once the desktop is the poster, the phone client becomes thin: compose, attach media,
pick platforms, pick a time, watch status. That is a web app, which removes the App
Store, TestFlight, code signing, Xcode, and Mac-hardware problem space entirely.

**Nothing in `src/` is discarded.** This plan is additive.

---

## Why this is not a port

The superseded plan assumed the thing Rin holds must also be the thing that posts. Under
that assumption, mobile means reimplementing the WebView automation tier against Android
WebView and WKWebView, bundling ffmpeg as a linked library on both, and finding mobile
builds of `Pillow` and `atproto`. Every one of those blockers exists only because the
work was going to run on the handset.

Moving the work to the always-on desktop deletes all of them at once:

| Blocker under a mobile port | Under this plan |
|---|---|
| No Qt WebEngine on Android/iOS | WebView tier stays on the desktop, unchanged |
| WKWebView cannot supply a file to `<input type=file>` | No WebView automation on the phone |
| No iOS wheels for `Pillow`, `atproto`/`libipld` | Media and API work stays on the desktop |
| ffmpeg cannot be `exec`'d on iOS; Android W^X since API 29; ffmpeg-kit retired | ffmpeg runs where it runs today |
| App Store review, TestFlight expiry, ad hoc signing, Xcode 26, Mac hardware | No app store involved |
| PyQt6 → PySide6 migration; possible KMP rewrite | No language or toolkit change |

---

## Requirements

From Rin:

1. **R1** — Compose and post from her phone (iPhone).
2. **R2** — Schedule a post for a future time.

Derived:

3. **R3** — Posting must continue to originate from her own machine and network
   (see [IP identity](#why-the-poster-stays-on-her-machine)).
4. **R4** — A missed scheduled post must not fail silently.
5. **R5** — Rin must be able to complete setup herself. She was sent setup instructions
   for the current desktop app months ago and has not gotten through them; onboarding
   friction is the empirically binding constraint on this project, not implementation
   effort. Treated as a deliverable, not a documentation afterthought.
6. **R6** — **Windows and Linux both run the full application**, with every capability
   enabled, including serving mobile clients. There is no reduced or headless-only build:
   the desktop app is the composer, the poster, the scheduler, *and* the server the phone
   talks to. A mobile client is always a view onto some desktop instance, never a
   standalone posting agent.
7. **R7** — Phone and desktop connect **directly over the LAN**. No relay, no VPN, no
   hosted component, no third party in the path.

---

## Confirmed environment

| | |
|---|---|
| Rin's desktop | Windows 11, powered 24×7, automatic logon (to confirm — see [Open questions](#open-questions)) |
| Rin's phone | iPhone |
| Rin's laptop | Used almost exclusively for travel/conventions — **not** part of this design |
| Jas's devices | iPhone (phone use only), Android tablet, desktop dual-booting Windows 11 / Kubuntu 26.04 |
| Jas's hosting | TrueNAS (Docker Compose apps, nginx proxy manager); `rin-city.com` server (EC2) |

---

## Architecture

```
        [ phone / tablet ]                    [ home router ]
                |                                    |
                +------ wifi ------------------------+
                                                     |
                         direct HTTPS over the LAN   |  ethernet
                                                     |
    +----------------------------------------------------------+
    |  GaleFling desktop  —  Windows or Linux, always-on        |
    |                                                            |
    |  full GUI: composer, setup wizard, settings, WebView tabs  |
    |  embedded HTTPS server: serves the PWA + its API           |
    |  schedule queue (SQLite)                                   |
    |  API tier: Twitter, Bluesky, Meta                          |
    |  WebView tier: OnlyFans, Fansly, FetLife (Qt WebEngine)    |
    |  media pipeline: ffmpeg, Pillow                            |
    |  credentials + platform sessions — never leave this host   |
    +----------------------------------------------------------+
```

The desktop app is a peer, not a headless daemon: everything it can do from its own GUI it
can also do on behalf of a mobile client, and the mobile client is served by the same
process. Nothing leaves the house, and there is no third party in the path.

### The one constraint LAN-direct imposes: TLS is mandatory

A PWA needs a **secure context**. Service workers, push notifications, and home-screen
installability all require HTTPS, and the only non-HTTPS exception is `localhost` —
**there is no exemption for private IP addresses**. `http://192.168.1.x:8443` gets
"Page is not served from a secure origin" and no service worker, on both iOS and Android.

So the embedded server must serve real TLS. Options, best first:

1. **A real certificate for a hostname that resolves to the LAN IP.** Jas already owns
   domains and runs DNS; a DNS-01 ACME challenge issues a publicly-trusted cert without
   any inbound exposure, and renewal needs outbound internet only. The phone trusts it with
   no prompts and Rin does nothing. **Recommended.**
2. Self-signed cert plus manual trust on each device — works, but it is an iOS
   trust-profile dance per device, which fails R5.
3. Plain HTTP — viable only if the client is downgraded to a plain web page: no
   installability, no push, no offline. Loses the "add to home screen" experience.

This is a genuine design item for Phase 2 and the main thing that makes LAN-direct less
trivial than it first appears. It is **not** an argument for a relay: option 1 needs no
inbound connectivity and no hosted service.

### Linux and Windows parity (R6)

Linux is not a secondary target — **it is where development happens.** Since Jas moved
from WSL to Kubuntu, Linux is the first-pass platform: features are built and exercised
natively via `make run`, and functional tests are usually written and run under Linux
before anything else. Build coverage is already complete (`make build-linux`, AppImage,
nfpm deb/rpm, snap), Qt WebEngine supports Linux, and the `sys.platform` gates in `src/`
touch only theme, Windows shell integration, app-data paths, and log collection — never
the posting tiers.

**Windows is the side more likely to drift**, precisely because it is not the daily
development platform. That is already handled by existing practice rather than by anything
this plan needs to invent: releases ship as **pre-releases**, and a build is promoted to
latest-stable only after explicit Windows verification, now via the `galefling-win11` VM.
Since Windows is Rin's platform, that promotion gate is the control that matters, and the
embedded server and scheduler must clear it like everything else.

The WSL functional-testing path is effectively dead — booting typhoon into Windows is not
a development activity anymore. It stays supported but should not be assumed exercised,
and it is not a validation route for this work.

### Why the poster stays on her machine

The obvious alternative is to run the poster in Docker on TrueNAS. It is rejected, and
the usual "datacenter IPs get flagged" argument is not the strongest reason.

The stronger reason is **IP identity**. If Rin's OnlyFans and Fansly sessions begin
originating from Jas's house — a different city, ISP, and ASN than every prior login for
those accounts — that is precisely the anomaly those platforms watch for. A residential
IP is not inherently safe; an IP *consistent with where the account has always been used*
is. Jas's residential IP is the right IP for Jas's accounts and the wrong one for Rin's.

Secondary reasons, in descending order of weight:

- Credentials and live platform sessions never leave Rin's device, so there is no
  custody question to put to her and no new class of secret on Jas's infrastructure.
- The Cloudflare-passing configuration on Fansly and OnlyFans — real Chromium, persistent
  per-account profile, a human available to solve a challenge — is the one that already
  works. Server-side means headless detection, Xvfb, and remote challenge-solving.
- The desktop already has a working ffmpeg and media pipeline.

`rin-city.com` is excluded for the same IP-identity reason. Under this plan no server-side
hosting is involved at all, so the question is moot unless off-LAN access is ever brought
into scope.

## Out of scope

**Using the app from the phone while away from home.** Rin posts, or schedules for later,
while she is at home; the phone and the desktop are on the same router. Nothing in R1 or
R2 requires reaching the desktop from outside the LAN.

This is a defensible feature to add later — the client speaks HTTPS to the same API
regardless of how the packets arrive, so a relay or Tailscale could be introduced without
touching the client — but it is a separate feature with its own hosting, exposure, and
onboarding costs, and shipping any mobile support at all comes first. Treat a request for
it as new scope, not as something this plan half-delivers.

Also out of scope: native mobile clients (see [Appendix A](#appendix-a--mobile-native-port-analysis-deferred)),
and any posting path that does not originate from the user's own machine.

---

## Scheduling design

### Delegate to the platform wherever it exists

There is a useful inversion here: the platforms that are hardest to automate are the ones
that can absorb the scheduling themselves. Driving a composer once to set a future post in
the platform's own scheduler is strictly more reliable than holding the schedule locally —
it survives the desktop being off, rebooting, or losing its network at post time.

Confirmed by Jas, 2026-08-13:

| Platform | Native scheduling | Approach |
|----------|-------------------|----------|
| OnlyFans | Yes | **Delegate** — drive the composer once, set a future time |
| Fansly | Yes | **Delegate** — drive the composer once, set a future time |
| Instagram | Yes | **Delegate** |
| Threads | Yes | **Delegate** |
| Facebook Page | No, directly | **Delegate indirectly** — see below |
| FetLife | No | Hold locally |
| Bluesky | No | Hold locally |
| Twitter | Not in the v2 API | Hold locally |

The delegated set includes both Cloudflare-protected WebView platforms, which is the
valuable part: for OnlyFans and Fansly the desktop does not need to be awake at post time
at all, and the riskiest automation runs once, while someone is around, rather than
unattended at 2 a.m.

**Facebook via Instagram crosspost.** Facebook Page posts have no scheduling path of their
own here, but Instagram does, and an Instagram post can crosspost to a linked Facebook
Page. A scheduled Instagram post can therefore carry Facebook with it, leaving nothing for
the local queue. Conditions to verify in Phase 0: the accounts must be linked with
crossposting enabled; the post must satisfy Instagram's constraints — media required, no
text-only — even when Facebook alone would have accepted it; and the two become coupled,
so "Facebook but not Instagram" and per-platform caption variants are lost for scheduled
posts. If any of those bite, Facebook falls back to the local queue, which is why it stays
listed as conditional rather than resolved.

That leaves the scheduler's unattended workload at three platforms — four if Facebook
falls back — only one of which drives a browser.

### Local queue

For the remainder: a SQLite-backed queue in the existing app data directory, a due-time
poller in the poster process, and per-item state (`pending` → `in_flight` → `posted` /
`failed`). Missed windows on wake are executed late with a visible "posted N minutes
late" status rather than silently dropped or silently skipped.

### Not failing silently (R4)

With no server-side component, alerting has to originate from the desktop itself: a
scheduled item that passes its due time without reaching a terminal state raises a visible
failure in the GUI, a push to any paired device, and an entry in the existing log-upload
path. Delegated posts are reconciled on the next session by checking whether the platform
actually published. Whether Jas gets an out-of-band notification when Rin's instance stops
running at all is an open question — that is the one thing a hosted heartbeat would have
provided for free, and the alternative is an outbound-only ping to something Jas already
operates.

---

## Windows session constraints

The WebView tier needs an **interactive desktop session** — Chromium cannot render
meaningfully from Session 0 — so the poster cannot be installed as a Windows service. It
must run as a startup item inside Rin's logged-in session. Consequences:

- A Windows Update reboot leaves the machine at the lock screen with the poster dead
  until someone logs in. Mitigation: enable *"Use my sign-in info to automatically finish
  setting up after an update"* so Windows restores her session, plus heartbeat alerting so
  a failure to come back is noticed within minutes rather than at the next missed post.
- **Powered 24×7 is not the same as awake 24×7.** Sleep and Modern Standby settings must
  be confirmed, not assumed.
- The existing GUI keeps working as-is; service mode is a second entry point into the same
  process, not a fork of it.

---

## Code reuse

Measured against the current tree (~17,043 LOC in `src/`):

| Area | LOC | Disposition |
|------|-----|-------------|
| `src/core/` — config, auth, media, OAuth, logging | 3,679 | Reused as-is |
| API adapters — `twitter`, `bluesky`, `meta_*`, `base` | 1,853 | Reused as-is |
| WebView tier — `base_webview.py` + adapters | 3,113 | **Reused as-is** — stays on Qt WebEngine, desktop-only |
| `src/utils/` — constants, helpers | 537 | Reused as-is |
| `src/gui/` + `theme.py` + `main.py` | 7,857 | Reused; gains a headless/tray mode |

New code: schedule queue, embedded HTTPS server and its API, device pairing/auth, PWA client.

For contrast, the superseded plan's Option B was 3–5 months and reimplemented the
1,813-line WebView base against a second engine; Option C discarded `src/` and `tests/`
outright. Neither is required to satisfy R1 and R2.

---

## Phases

### Phase 0 — Spike and confirmation (~1 week)

| # | Deliverable | Owner | Pass criteria |
|---|-------------|-------|---------------|
| 0.1 | Confirm Rin's sleep + autologon settings | Jas | Written into this doc |
| 0.2 | Delegated scheduling spike | Agent + operator | Existing automation sets a *future* post on Fansly **or** OnlyFans; operator confirms it fires |
| 0.3 | Facebook-via-Instagram crosspost | Agent + operator | A *scheduled* Instagram post reaches the linked Facebook Page; coupling constraints documented |
| 0.4 | PWA media upload from iPhone Safari | Agent + operator | Photo and short video reach a local endpoint from a home-screen web app |
| 0.5 | Go/no-go | Both | Delegation viable for the platforms that support it; local queue scoped to the remainder |

0.2 is the highest-value item: it is what keeps the unattended scheduler down to four
platforms and keeps the Cloudflare-sensitive automation attended.

### Phase 1 — Scheduler in the desktop app (~2–3 weeks)

Schedule queue, due-time poller, background/tray operation, missed-window handling, and
delegated-vs-local routing per platform. Deliverable: **a post scheduled from the existing
desktop GUI fires correctly with the app minimized**, on both Windows and Linux. No phone
involved yet. This alone satisfies R2.

### Phase 2 — Embedded HTTPS server + PWA (~3–4 weeks)

The desktop app gains a TLS-terminating HTTP server that serves the PWA and its API: draft
submission, media upload, platform selection, schedule picker, status. Touch-first client,
home-screen installable, Declarative Web Push for post results, Persistent Storage API to
protect the auth token from eviction, chunked/resumable upload for video.

Includes the certificate story from
[TLS is mandatory](#the-one-constraint-lan-direct-imposes-tls-is-mandatory) and device
pairing/auth. Bind, TLS, auth, and pairing must work identically on Windows and Linux
(R6). Completing this phase satisfies **R1** outright.

### Phase 3 — Onboarding (R5) (~1 week)

Treated as engineering, not documentation: installer defaults that enable autostart, a
first-run flow that ends with her phone paired and the PWA on her home screen, a
one-page setup guide, and a way for Jas to see whether her side is healthy. **Success is
Rin completing setup unaided, not the existence of instructions.**

**Total: ~6–9 weeks**, sequential, with Phases 1 and 2 each independently useful — Phase 1
delivers scheduling on its own, Phase 2 delivers phone posting.

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Rin does not complete setup (historical precedent) | **High** | High | Phase 3 as a real phase; minimize her step count; no VPN or account signup on her side |
| Windows Update reboot strands the poster at the lock screen | Medium | High | Autologon + session restore; heartbeat alerting |
| Desktop sleeps despite being powered | Medium | High | Confirm in 0.1; disable sleep; wake timers |
| Delegated scheduling breaks when a composer changes | Medium | Medium | Same fragility as posting today; reconcile after the fact |
| **Windows** drifts out of parity — development and first-pass testing happen on Kubuntu | Medium | High | Existing practice already covers this: releases ship as pre-releases and are promoted to stable only after explicit Windows verification, now via the `galefling-win11` VM. Windows is Rin's platform, so the promotion gate is the control that matters. |
| Certificate expiry silently breaks the phone client | Medium | Medium | Automated renewal; surface cert validity in the desktop GUI rather than only in logs |
| Embedded server listening on the LAN | Medium | Medium | TLS plus device auth from the first commit, not retrofitted; explicit bind address, never `0.0.0.0` by default |
| Large video upload from Safari over cellular stalls | Medium | Medium | Chunked/resumable upload; no background upload on iOS |
| iOS evicts PWA storage, losing the auth token | Low | Low | Persistent Storage API; re-pair flow |
| No Web Share Target on iOS | Certain | **Accepted** | Rin opens the app and picks media — confirmed acceptable |
| Cloudflare behavior changes on Fansly/OnlyFans | Medium | High | Unchanged from today; posting stays on her machine and IP |

Note that the top risks are operational rather than technical, which is the expected shape
once the architecture stops fighting the platforms.

---

## Open questions

1. Rin's sleep settings and autologon state — Jas to confirm; expected to already be correct.
2. Which domain issues the LAN certificate, and does DNS-01 renewal fit existing tooling?
3. How does the phone find the desktop — fixed hostname resolving to a DHCP reservation,
   or mDNS/`.local` discovery? Affects R5 more than anything technical.
4. Should Rin's instance ping something Jas operates so a total outage is noticed
   out-of-band? Outbound-only, no inbound exposure — but it is the one hosted-adjacent
   piece worth reconsidering.

---

## Appendix A — Mobile-native port analysis (deferred)

Retained from the superseded `ANDROID_PORT.md` and the follow-on stack analysis. Relevant
only if the PWA proves insufficient. Because the client is thin, a native client at that
point would be a small app, not a port of GaleFling.

### Qt / Python on mobile

- Qt WebEngine is supported on Windows, Linux, and macOS only. `QtWebView` (in
  PySide6-Addons, Android and iOS, wrapping the native engines) implements
  `runJavaScript` on both but offers no per-account profile isolation, no cookie
  database, no `chooseFiles` override, and no synthetic mouse events — all four of which
  `src/platforms/base_webview.py` depends on.
- PyQt6 has no Android or iOS deployment path; PySide6 is the only route, making a
  full PyQt6 → PySide6 migration a prerequisite for any Python-on-mobile approach.
- PySide6 on iOS exists as of Qt 6.12 but is a research preview: static linking, manually
  generated Xcode projects, no simulator, and **no third-party packages with C
  extensions** — which excludes `Pillow` and `atproto`/`libipld`.

### Media on mobile

`imageio-ffmpeg` ships no mobile builds. Android has blocked executing binaries from the
app's writable data directory since API 29 (W^X), and iOS forbids subprocess execution
outright, so ffmpeg must be linked as a library on both. `ffmpeg-kit` was retired with its
native binaries removed from Maven Central, CocoaPods, and npm on 2025-04-01;
FFmpegKitNext is the successor.

### If a native client were ever required

Ranked by the only criterion that matters for this app — a WebView with automation hooks
on all four OSes:

1. **Kotlin Multiplatform + Compose Multiplatform** — all four targets, one UI,
   `expect`/`actual` matching the port/adapter shape, and JCEF (Chromium) on desktop.
2. **Avalonia + .NET** — all four targets, one UI; community WebView wrappers are the
   weak link.
3. Qt 6 in C++ — same WebView ceiling; LGPL static linking on iOS pushes toward a
   commercial licence.
4. Rejected: Flutter (desktop WebView is third-party, Linux worst), Tauri v2 (WebKitGTK
   on Linux vs Chromium elsewhere means selectors and fingerprints diverge per OS),
   .NET MAUI and React Native (no Linux).

### iOS distribution, if it ever applies

The App Store is not realistic for this app's destinations. Internal TestFlight requires
no Beta App Review but caps at team members and expires builds after 90 days; external
TestFlight requires Beta App Review against the App Review Guidelines. **Ad hoc
distribution** avoids review entirely and never uploads to App Store Connect — which also
exempts it from the requirement, effective 2026-04-28, that uploads be built with Xcode 26
and the iOS 26 SDK. Xcode 26 needs macOS Sequoia 15.6+; among Intel Macs only the 2019
16-inch MacBook Pro, 2020 13-inch four-port MacBook Pro, 2020 27-inch iMac, and 2019 Mac
Pro reach macOS 26. For build capacity, GitHub Actions macOS runners bill per minute with
no minimum; AWS EC2 Mac has a 24-hour minimum. An Apple silicon Mac mini is cheaper than
sustained rental and is the only option that supports an interactive debug loop.

---

## References

- `docs/ARCHITECTURE_OVERVIEW.md` — two-tier posting model
- `docs/platforms/PLATFORM_SPECS.md` — platform limits and API vs WebView
- `src/platforms/base_webview.py` — WebView tier retained unchanged by this plan
- `AGENTS.md` — mandatory agent rules and release checklist
- [Apple upcoming SDK requirements](https://www.developer.apple.com/news/upcoming-requirements/)
- [Android 10 behavior changes (W^X)](https://developer.android.com/about/versions/10/behavior-changes-10)
- [Qt for Python on iOS](https://www.qt.io/blog/python-mobile-app-development-bringing-pyside6-on-ios)

---

## Changelog

| Date | Change |
|------|--------|
| 2026-08-13 | Initial draft. Supersedes `ANDROID_PORT.md`; re-framed from mobile port to desktop-resident scheduler + relay + PWA. |
| 2026-08-13 | Relay/Tailscale dropped entirely (Jas): phone and desktop are on the same router, so they connect directly. Off-LAN access moved to explicit non-goals. Added R7 and the TLS/secure-context constraint that LAN-direct imposes. Corrected the parity risk — Linux is the primary development platform since the move to Kubuntu; Windows is the side that drifts, controlled by the existing pre-release-then-promote gate. Noted the WSL functional path as effectively dead. |
| 2026-08-13 | Facebook Page scheduling reframed as delegable indirectly, by letting a scheduled Instagram post crosspost to the linked Page (Jas). Added as Phase 0.3. |
| 2026-08-13 | Native-scheduling table confirmed by Jas (Threads and Instagram yes; Facebook and FetLife no). Added R6 — full functionality on both Windows and Linux, with the desktop app itself serving mobile clients. Relay demoted to optional off-LAN transport; phases reordered so LAN-only phone posting lands before any hosted component. |
