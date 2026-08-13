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
| **GaleFling desktop** — the whole app: composer, posting, media pipeline, scheduler, **and the HTTP server that serves mobile clients** | Windows or Linux, always-on (Rin: Win11, 24×7) | Existing app + scheduler + embedded server |
| **PWA client** | iPhone, Android tablet, any browser — served *by the desktop app itself* | New |
| **Relay** *(optional)* | TrueNAS Docker behind nginx proxy manager | New, small — needed only for off-LAN access |

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
  [phone / tablet, same LAN]          [phone, away from home]
             |                                   |
             |  direct HTTP over LAN             |  via relay
             |                                   v
             |            +--------------------------------------------+
             |            |  Relay (optional; TrueNAS Docker, NPM+TLS)  |
             |            |  - draft + media queue, in transit only     |
             |            |  - status / heartbeat fan-out               |
             |            |  - NO credentials, NO platform sessions     |
             |            +--------------------------------------------+
             |                                   ^
             |                                   | outbound long-poll / WebSocket
             |                                   | (desktop dials out; nothing opened
             |                                   |  on the home network)
             v                                   |
    +----------------------------------------------------------+
    |  GaleFling desktop  —  Windows or Linux, always-on        |
    |                                                            |
    |  full GUI: composer, setup wizard, settings, WebView tabs  |
    |  embedded HTTP server: serves the PWA + its API            |
    |  schedule queue (SQLite)                                   |
    |  API tier: Twitter, Bluesky, Meta                          |
    |  WebView tier: OnlyFans, Fansly, FetLife (Qt WebEngine)    |
    |  media pipeline: ffmpeg, Pillow                            |
    |  credentials + platform sessions — never leave this host   |
    +----------------------------------------------------------+
```

The desktop app is a peer, not a headless daemon: everything it can do from its own GUI
it can also do on behalf of a mobile client, and the mobile client is served by the same
process. On the home LAN the phone talks to it directly and no hosted component exists at
all. The relay is purely a rendezvous for reaching that same server from outside the LAN,
and it is separable — see [Why a relay rather than Tailscale](#why-a-relay-rather-than-tailscale).

### Linux parity (R6)

Linux is already a real build and test target — `make build-linux`, AppImage
(`build/linux/appimage/`), nfpm deb/rpm (`build/linux/nfpm.yaml`), snap
(`build/linux/snap/`), and `make test-functional-linux` / `test-functional-xvfb`. Qt
WebEngine supports Linux, and the `sys.platform` gates in `src/` are confined to theme,
Windows shell integration, app-data paths, and log collection — none of them touch the
posting tiers. R6 is therefore mostly a **verification and CI obligation** rather than new
implementation: the embedded server and scheduler must be written without Windows-only
assumptions, and Linux must stay exercised rather than merely buildable. Jas's Kubuntu
26.04 side of the dual boot is the natural development host for the server and PWA work.

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

`rin-city.com` is excluded from the posting path for the same IP-identity reason. It
remains a fine host for the **relay**, which never contacts a platform, if exposing
TrueNAS is undesirable.

### Off-LAN transport: relay vs. Tailscale

Neither is needed while the phone is on the same network as the desktop, which is the
common case and the whole of Phase 2. Both are answers to the narrower question of
reaching that same server from elsewhere.

Tailscale is technically cleaner: put Rin's desktop, her iPhone, and Jas's devices on one
tailnet and there is no hosted component at all.

It loses on **R5**. Tailscale adds an app install and an account login to Rin's side of
setup. A relay makes her side "install GaleFling, it dials out" and her phone side "open a
URL and add it to the home screen." Given that the existing single-app setup has not been
completed in months, minimizing her step count outranks architectural tidiness.

The client speaks plain HTTP to the same API either way, so this is a deployment choice
rather than a design one, and Phase 3 can be decided — or skipped — on evidence from
Phase 2.

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

The poster sends a heartbeat to the relay. The relay alerts Jas when a desktop misses its
heartbeat window, and separately when a scheduled item passes its due time without
reaching a terminal state. Delegated posts are reconciled on the next session by checking
whether the platform actually published.

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

New code: schedule queue, relay client, local HTTP API, relay service, PWA client.

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

### Phase 2 — Embedded server + PWA (~3–4 weeks)

The desktop app gains an HTTP server that serves the PWA and its API: draft submission,
media upload, platform selection, schedule picker, status. Touch-first client, home-screen
installable, Declarative Web Push for post results, Persistent Storage API to protect the
auth token from eviction, chunked/resumable upload for video.

Reachable over the LAN only at this stage — which already satisfies **R1 whenever Rin is
at home**, with no hosted component in existence yet. Bind, auth, and pairing must work
identically on Windows and Linux (R6).

### Phase 3 — Off-LAN access (~1–2 weeks)

Only now does a hosted piece appear, and only to reach the Phase 2 server from outside the
LAN: a relay as a Docker Compose app on TrueNAS behind nginx proxy manager with TLS,
outbound-dialed from the desktop, draft/media queue with a retention policy, heartbeat and
alerting. Per the TrueNAS conventions in the global agent instructions: no `env_file` —
bind-mount a `.env` or use explicit `environment:` entries — and set `PYTHONUNBUFFERED=1`.

Deferrable if LAN-only proves sufficient in practice; Tailscale remains the alternative.

### Phase 4 — Onboarding (R5) (~1 week)

Treated as engineering, not documentation: installer defaults that enable autostart, a
first-run flow that ends in a working relay pairing, a printable/one-page setup guide for
Rin, and a remote way for Jas to see whether her side is healthy. **Success is Rin
completing setup unaided, not the existence of instructions.**

**Total: ~7–11 weeks**, sequential, with Phases 1 and 2 each independently useful — Phase 1
delivers scheduling on its own, Phase 2 delivers phone posting at home without any hosted
infrastructure.

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Rin does not complete setup (historical precedent) | **High** | High | Phase 5 as a real phase; minimize her step count; relay over Tailscale |
| Windows Update reboot strands the poster at the lock screen | Medium | High | Autologon + session restore; heartbeat alerting |
| Desktop sleeps despite being powered | Medium | High | Confirm in 0.1; disable sleep; wake timers |
| Delegated scheduling breaks when a composer changes | Medium | Medium | Same fragility as posting today; reconcile after the fact |
| Linux drifts out of parity because Windows is where testing happens | **High** | Medium | R6 is a CI obligation: keep `test-functional-linux`/`xvfb` green; develop the server and PWA on Kubuntu |
| Embedded server is listening on Rin's LAN | Medium | Medium | Auth required from the first commit, not added later; bind explicitly, never `0.0.0.0` by default |
| Relay is internet-exposed (Phase 3 only) | Medium | Medium | TLS, real auth, short media retention, no credentials ever stored |
| Large video upload from Safari over cellular stalls | Medium | Medium | Chunked/resumable upload; no background upload on iOS |
| iOS evicts PWA storage, losing the auth token | Low | Low | Persistent Storage API; re-pair flow |
| No Web Share Target on iOS | Certain | **Accepted** | Rin opens the app and picks media — confirmed acceptable |
| Cloudflare behavior changes on Fansly/OnlyFans | Medium | High | Unchanged from today; posting stays on her machine and IP |

Note that the top risks are operational rather than technical, which is the expected shape
once the architecture stops fighting the platforms.

---

## Open questions

1. Rin's sleep settings and autologon state — Jas to confirm; expected to already be correct.
2. Relay host, if Phase 3 happens at all: TrueNAS or `rin-city.com`? Either works, since the
   relay never contacts a platform; TrueNAS assumed.
3. Does the embedded server run on a fixed port with mDNS/`.local` discovery, or does
   pairing hand the client an address? Affects R5 more than anything technical.

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
| 2026-08-13 | Facebook Page scheduling reframed as delegable indirectly, by letting a scheduled Instagram post crosspost to the linked Page (Jas). Added as Phase 0.3. |
| 2026-08-13 | Native-scheduling table confirmed by Jas (Threads and Instagram yes; Facebook and FetLife no). Added R6 — full functionality on both Windows and Linux, with the desktop app itself serving mobile clients. Relay demoted to optional off-LAN transport; phases reordered so LAN-only phone posting lands before any hosted component. |
