# GaleFling — Mobile / LAN Access

## Status

**Draft — Phase 0 partially resolved, Phase 2/3 not started.** Split out of the combined
`SCHEDULING_AND_MULTI_CLIENT.md` plan on 2026-08-21 (Jas) — scheduling and mobile/LAN
access are handled in entirely different phases and no longer need to share one
document. See [docs/plans/SCHEDULING.md](SCHEDULING.md) for the scheduling design (R2,
R4, delegate-vs-local-queue) — this document owns everything else: the desktop-resident
server topology, R1, R3, R5, R6, R7, and the mobile web client.

Tracked in Odoo **#451**. Scheduling is tracked separately in Odoo **#450** (both split
from the original combined plan/index, Odoo **#426**, on 2026-08-16). Per Odoo #451,
mobile/LAN access is **not currently an active priority** for Rin — this document
remains the design record for when it is picked up.

Supersedes an earlier `ANDROID_PORT.md` plan that framed this work as an Android/iOS
port of the desktop app. That framing was wrong; see
[Why this is not a port](#why-this-is-not-a-port). That document has been removed — its
still-relevant feasibility analysis is preserved in
[Appendix A](#appendix-a--mobile-native-port-analysis-deferred), and the surrounding
discussion is in Odoo #426.

Canonical repo path: `docs/plans/MOBILE_LAN_ACCESS.md`

---

## Executive summary

Rin asked for posting from her phone. That reads as "port the app to mobile." It isn't.
The correct response is a **topology change, not a rewrite**:

| Component | Runs on | Status |
|-----------|---------|--------|
| **GaleFling desktop** — the whole app: composer, posting, media pipeline, scheduler, **and the web server that serves mobile clients** | Windows or Linux, always-on (Rin: Win11, 24×7) | Existing app + scheduler + embedded server |
| **Mobile client** | iPhone, Android tablet, any browser — served *by the desktop app itself, reached over the LAN at `galefling.local`* | New |

**There is no relay, no VPN, and no hosted component.** Rin's desktop is on the router by
ethernet and her phone by wifi; they talk to each other directly. Off-LAN access is
explicitly out of scope — see [Out of scope](#out-of-scope).

The decisive constraint is that **scheduled posting cannot run on a phone**. Android's
WorkManager schedules into maintenance windows, not at times; iOS `BGTaskScheduler` is
explicitly opportunistic with no timing guarantee and does not run at all after a force
quit. The WebView tier additionally needs a live browser rendering a DOM, which neither
mobile OS permits from a background task. Something that is already always-on has to do
the posting — and Rin's desktop already is. This is why GaleFling's scheduler
([SCHEDULING.md](SCHEDULING.md)) lives on the desktop rather than the phone, even though
this document's mobile client is what lets Rin *create* a scheduled post from her phone.

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

- **R1** — Compose and post from her phone (iPhone).

Derived:

- **R3** — Posting must continue to originate from her own machine and network
  (see [IP identity](#why-the-poster-stays-on-her-machine)). This also underlies
  scheduling's local queue — see
  [SCHEDULING.md](SCHEDULING.md#requirements) — since the due-time poller runs on the
  same machine under the same constraint.
- **R5** — Rin must be able to complete setup herself. She was sent setup instructions
  for the current desktop app months ago and has not gotten through them; onboarding
  friction is the empirically binding constraint on this project, not implementation
  effort. Treated as a deliverable, not a documentation afterthought.
- **R6** — **Windows and Linux both run the full application**, with every capability
  enabled, including serving mobile clients. There is no reduced or headless-only build:
  the desktop app is the composer, the poster, the scheduler, *and* the server the phone
  talks to. A mobile client is always a view onto some desktop instance, never a
  standalone posting agent.
- **R7** — Phone and desktop connect **directly over the LAN**. No relay, no VPN, no
  hosted component, no third party in the path.

R2 and R4 (scheduling and its failure reporting) are defined in
[SCHEDULING.md](SCHEDULING.md#requirements).

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
                      direct HTTP over the LAN, via  |  ethernet
                      mDNS (galefling.local)         |
                                                     |
    +----------------------------------------------------------+
    |  GaleFling desktop  —  Windows or Linux, always-on        |
    |                                                            |
    |  full GUI: composer, setup wizard, settings, WebView tabs  |
    |  embedded web server: serves the mobile client + its API   |
    |  schedule queue (SQLite) — see SCHEDULING.md                |
    |  API tier: Twitter, Bluesky, Meta                          |
    |  WebView tier: FetLife (Qt WebEngine); OnlyFans, Fansly paused |
    |  media pipeline: ffmpeg, Pillow                            |
    |  credentials + platform sessions — never leave this host   |
    +----------------------------------------------------------+
```

The desktop app is a peer, not a headless daemon: everything it can do from its own GUI it
can also do on behalf of a mobile client, and the mobile client is served by the same
process. Nothing leaves the house, and there is no third party in the path.

### Discovery and TLS

Two separate problems, and it is worth not conflating them: **how the phone finds the
desktop**, and **whether the connection is a secure context**.

Neither may assume a known or stable IP address. Rin's desktop takes a DHCP lease from a
UniFi Dream Machine; nobody knows its address, it is not reserved, and configuring a
reservation is not something to ask of her — nor is it obvious to a non-technical user why
it would matter. Any design that starts with "point a record at 192.168.x.y" has pushed
its hardest step onto the person least able to do it, which fails R5.

#### Discovery: mDNS

**`http://galefling.local:<port>`.** The app advertises itself over mDNS; the name
resolves with no configuration anywhere, and it keeps working when DHCP hands out a
different address. iOS implements RFC 6762 natively — Bonjour is Apple's own technology,
so `.local` resolution in Safari is a first-class path. Android has resolved `.local` in
Chrome since the DNS Resolver Mainline update, roughly Android 12+, which covers Jas's
tablet.

Caveat: mDNS is link-local, so phone and desktop must share a subnet. A default Dream
Machine setup puts wifi and ethernet clients on the same LAN, so this holds; VLAN
segregation would require mDNS reflection on the UDM.

#### Secure context: the real constraint

Service workers, push notifications, and offline support require HTTPS. **There is no
exemption for private IP addresses** — `localhost` is the only non-HTTPS exception — so
`http://192.168.1.x` yields "not served from a secure origin" and no service worker.
`.local` cannot be certified either: publicly-trusted CAs have been barred from issuing
for internal names since 2015.

What plain HTTP does **not** cost, contrary to an earlier draft of this document:

- **Add to Home Screen still works on iOS.** It is a manual user action, not Chrome's
  `beforeinstallprompt` install criteria, and has never required HTTPS. With
  `apple-mobile-web-app-capable` the app still opens standalone, without browser chrome.
- **Picking photos and videos still works.** `<input type="file">` is not a
  secure-context-gated API, unlike `getUserMedia`.

So over plain HTTP Rin can add the app to her home screen, open it standalone, compose,
attach media from her library, choose platforms and a time, and watch status.

Exactly two things are lost, and neither is currently worth paying for:

- **Push notifications** — moot. GaleFling has no notification model at all today; post
  results are shown in the results dialog. There is nothing to push. R4
  ([SCHEDULING.md](SCHEDULING.md#not-failing-silently-r4)) is satisfied by the desktop
  GUI and by Jas's alerting.
- **Offline capability** — narrower than it sounds. Without a service worker the page
  loads only while the desktop is reachable, so tapping the home-screen icon while away
  from home produces a browser error rather than opening the app, and there is no
  compose-while-away-then-sync-on-return. That is a weaker relative of the off-LAN access
  already ruled [out of scope](#out-of-scope) — compose-now-send-later rather than posting
  remotely — and it has a zero-cost workaround in drafting elsewhere and pasting in. Rin
  has not asked for it.

#### Recommendation

**Baseline for Phase 2: HTTP over mDNS.** Zero configuration for Rin, immune to DHCP
changes, no certificates, no secrets on her machine, and it delivers R1 in full.

**Upgrade path, if compose-while-away is ever wanted:** both losses sit behind the same
gate — secure context — so there is no partial upgrade to reason about, and one piece of
work buys both. That work is a publicly-trusted certificate for a real hostname whose
**public** DNS A record points at her private IP — legal in DNS, and the model Plex uses. The app knows its own address and updates the record itself, so there
is still no static IP and nothing for Rin to configure; the certificate comes from a
DNS-01 challenge needing no inbound connectivity. Costs: a scoped DNS API credential
living on her machine, propagation lag when the address changes, and exposure to DNS
rebinding protection, which some resolvers apply by discarding public answers that contain
RFC 1918 addresses. Worth doing deliberately later, not as a precondition for shipping.

Self-signed certificates are rejected outright: trusting one on iOS is a per-device
configuration-profile dance, which is exactly the kind of step R5 exists to eliminate.

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
This is R3, and it applies equally to scheduling's local queue — see
[SCHEDULING.md](SCHEDULING.md#requirements).

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

This is a defensible feature to add later — the client speaks HTTP to the same API
regardless of how the packets arrive, so a relay or Tailscale could be introduced without
touching the client — but it is a separate feature with its own hosting, exposure, and
onboarding costs, and shipping any mobile support at all comes first. Treat a request for
it as new scope, not as something this plan half-delivers.

Also out of scope: native mobile clients (see [Appendix A](#appendix-a--mobile-native-port-analysis-deferred)),
any posting path that does not originate from the user's own machine, and
[monitoring whether Rin's machine is up](#explicitly-not-in-scope-monitoring-rins-machine).

### Explicitly not in scope: monitoring Rin's machine

Whether her desktop is powered on, and whether GaleFling is running on it, is **not
monitored and not alerted on**. That is her machine; if it is down for a week she either
knows or is not home, and proactively watching it is not Jas's responsibility. This is a
different problem from R4 ([SCHEDULING.md](SCHEDULING.md#not-failing-silently-r4)), which
is about GaleFling reporting *its own* failures while it is running.

An earlier revision of the combined plan treated the two as one and proposed a dead-man's
switch — an outbound heartbeat to something Jas operates, alerting when it stopped. That
is dropped. It solved a problem nobody has, and it was the only remaining piece that
reached outside the house.

---

## Windows session constraints

The WebView tier needs an **interactive desktop session** — Chromium cannot render
meaningfully from Session 0 — so neither the scheduler's poller nor the embedded mobile
server can be installed as a Windows service. Both must run as a startup item inside
Rin's logged-in session. Consequences:

- A Windows Update reboot leaves the machine at the lock screen with the poster and
  server both dead until someone logs in. Mitigation: enable *"Use my sign-in info to
  automatically finish setting up after an update"* so Windows restores her session, so a
  reboot self-heals rather than waiting on someone noticing. Anything whose due time
  passed during the reboot is caught by scheduling's startup reconciliation — see
  [SCHEDULING.md#not-failing-silently-r4](SCHEDULING.md#not-failing-silently-r4).
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

New code for this document's scope: embedded web server and its API, mDNS advertisement,
device auth, mobile client. (Scheduling's new code — schedule queue, due-time poller — is
tracked in [SCHEDULING.md](SCHEDULING.md).)

For contrast, the superseded plan's Option B was 3–5 months and reimplemented the
1,813-line WebView base against a second engine; Option C discarded `src/` and `tests/`
outright. Neither is required to satisfy R1.

---

## Phases

### Phase 0 — Spike and confirmation (mobile/LAN-relevant items)

| # | Deliverable | Owner | Pass criteria |
|---|-------------|-------|---------------|
| ~~0.1~~ | ~~Confirm Rin's sleep + autologon settings~~ | **Resolved 2026-08-21 (Jas)** | Sleep is not configured — not a risk. Autologon still needs separate confirmation (see [Open questions](#open-questions) #1 below). Surfaced a bigger finding for scheduling: Rin routinely fully shuts the machine down when not in active use — see [SCHEDULING.md#shutdown-awareness-r4](SCHEDULING.md#shutdown-awareness-r4). |
| 0.4 | mDNS + media upload from Rin's iPhone | Agent + operator | `galefling.local` resolves from her phone through the Dream Machine; a photo and a short video reach a local endpoint from a home-screen web app over plain HTTP |
| 0.5 | Go/no-go | Both | Local queue scoped to every schedulable platform per [SCHEDULING.md](SCHEDULING.md); mDNS + LAN delivery confirmed viable for the mobile client |

Scheduling's Phase 0 items (0.2, 0.3, 0.3b) are tracked in
[SCHEDULING.md#phase-0--spike-and-confirmation-scheduling-relevant-items](SCHEDULING.md#phase-0--spike-and-confirmation-scheduling-relevant-items)
and are already resolved.

### Phase 2 — Embedded server + mobile client (~3–4 weeks)

The desktop app gains an HTTP server that serves the mobile client and its API: draft
submission, media upload, platform selection, schedule picker, status. Touch-first,
addable to the home screen and standalone via `apple-mobile-web-app-capable`, with
chunked/resumable upload for video. No service worker in the baseline, so post results are
shown on open rather than pushed.

Includes mDNS advertisement and device auth per
[Discovery and TLS](#discovery-and-tls); no certificates in the baseline. Bind, TLS, auth, and pairing must work identically on Windows and Linux
(R6). Completing this phase satisfies **R1** outright. Depends on the schedule picker/queue
existing server-side, so in practice follows
[SCHEDULING.md Phase 1](SCHEDULING.md#phase-1--scheduler-in-the-desktop-app-23-weeks),
though nothing about the mobile client's design requires waiting on it.

### Phase 3 — Onboarding (R5) (~1 week)

Treated as engineering, not documentation: installer defaults that turn on the
[start-at-login setting](SCHEDULING.md#start-at-login) (which ships with scheduling in
Phase 1, not introduced fresh here — Phase 3 just needs the installer to default it on for
a new install, same as it would for scheduling alone), a first-run flow that ends with her
phone paired and the client on her home screen, a one-page setup guide, and a way for Jas
to see whether her side is healthy. **Success is Rin completing setup unaided, not the
existence of instructions.**

"Unaided" is load-bearing: Rin is in Nevada and Jas is in Washington, so there is no
in-person fallback. Every setup step and every subsequent troubleshoot happens either on
her own or over a screen share. Anything that would realistically need hands on the
machine is a design defect, not a support burden. (Both are on Pacific time, so scheduled
times carry no cross-timezone ambiguity between them — though the UI should still state
which clock a scheduled time refers to.)

**Total for this document's phases: ~5–6 weeks** (0.4, 2, 3), independent of
[SCHEDULING.md's Phase 1](SCHEDULING.md#phase-1--scheduler-in-the-desktop-app-23-weeks)
(~2–3 weeks) — scheduling can ship and be used from the desktop GUI before any mobile work
lands.

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Rin does not complete setup (historical precedent) | **High** | High | Phase 3 as a real phase; minimize her step count; no VPN or account signup on her side |
| **Windows** drifts out of parity — development and first-pass testing happen on Kubuntu | Medium | High | Existing practice already covers this: releases ship as pre-releases and are promoted to stable only after explicit Windows verification, now via the `galefling-win11` VM. Windows is Rin's platform, so the promotion gate is the control that matters. |
| mDNS fails — VLAN segregation, or a client that will not resolve `.local` | Low | Medium | Verify in Phase 0.4 on Rin's actual network; fall back to a discovery step in the desktop GUI that displays the current address |
| Compose-while-away later wanted, forcing the TLS upgrade path | Low | Low | Deliberate later work; the client and API are unchanged by it |
| Embedded server listening on the LAN | Medium | Medium | TLS plus device auth from the first commit, not retrofitted; explicit bind address, never `0.0.0.0` by default |
| Large video upload from Safari over cellular stalls | Medium | Medium | Chunked/resumable upload; no background upload on iOS |
| iOS clears the auth token from local storage | Medium | Low | Keep re-pairing cheap — a QR code or short code from the desktop GUI, not a credential re-entry |
| No Web Share Target on iOS | Certain | **Accepted** | Rin opens the app and picks media — confirmed acceptable |

Scheduling-specific risks (reboot strands the poster, desktop sleep, local-queue posting
breaking on API changes, Cloudflare on paused platforms) are tracked in
[SCHEDULING.md#risk-register-scheduling-relevant](SCHEDULING.md#risk-register-scheduling-relevant).

Note that the top risks here are operational rather than technical, which is the expected
shape once the architecture stops fighting the platforms.

---

## Open questions

1. Rin's autologon state — still to confirm. Sleep is resolved (Phase 0.1, 2026-08-21):
   not configured. (Phase 0.1)
2. Does mDNS resolve end-to-end on Rin's actual network — her iPhone to her desktop
   through the Dream Machine? Everything about discovery rests on this. (Phase 0.4)

Scheduling's staleness-threshold and reboot-vs-shutdown-detection open questions are
tracked in [SCHEDULING.md#open-questions](SCHEDULING.md#open-questions).

---

## Appendix A — Mobile-native port analysis (deferred)

Retained from the superseded Android-port plan and the follow-on stack analysis. Relevant
only if the web client proves insufficient. Because the client is thin, a native client at that
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

- `docs/plans/SCHEDULING.md` — scheduling design, R2/R4, delegate-vs-local-queue decision
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
| 2026-08-21 | Phase 3's installer-default autostart language now points to `SCHEDULING.md`'s new [Start at login](SCHEDULING.md#start-at-login) setting (Jas) — that setting ships with scheduling in Phase 1, not introduced fresh here; Phase 3 only needs the installer to default it on. |
| 2026-08-21 | Resolved the sleep half of Phase 0.1 (Jas): confirmed not configured, retiring that risk from scheduling's register. Surfaced a bigger finding in the process — Rin routinely fully shuts the machine down when not in active use — which fed a new "Shutdown awareness" design section in `docs/plans/SCHEDULING.md` rather than this document, since it's a scheduling-protection concern. Autologon confirmation remains an open question. |
| 2026-08-21 | Split out of `docs/plans/SCHEDULING_AND_MULTI_CLIENT.md` into this mobile/LAN-access-only document (Jas): scheduling and mobile/LAN access are handled in entirely different phases and no longer need one shared file. Content carried over verbatim from the combined plan's mobile/LAN-relevant sections; scheduling content moved to `docs/plans/SCHEDULING.md`. This document retains the full original changelog below for continuity, since it is the architectural/topology-level document the combined plan grew from. |
| 2026-08-13 | Initial draft. Supersedes `ANDROID_PORT.md`, since removed — its analysis survives as Appendix A. Re-framed from mobile port to desktop-resident scheduler + mobile web client. |
| 2026-08-13 | Noted that Rin (Nevada) and Jas (Washington) are remote from each other, so R5's "unaided" has no in-person fallback and support is screen-share only. Both on Pacific time. |
| 2026-08-13 | Clarified what plain HTTP actually costs (Jas): push is moot since GaleFling has no notification model, and "offline" means the app will not open at all while off-LAN, i.e. no compose-while-away. Both sit behind the same secure-context gate, so the TLS upgrade is one decision rather than two. |
| 2026-08-13 | Discovery reworked (Jas): Rin's desktop has no static IP or DHCP reservation and configuring one is not something to ask of her, so any address-based scheme fails R5. Baseline is now mDNS (`galefling.local`) over plain HTTP. Corrected an error in the previous revision — plain HTTP does **not** prevent Add to Home Screen on iOS, nor `<input type=file>`; only service workers, push, and offline are lost. TLS via dynamic public DNS pointing at the private IP is retained as a deliberate later upgrade. |
| 2026-08-13 | Relay/Tailscale dropped entirely (Jas): phone and desktop are on the same router, so they connect directly. Off-LAN access moved to explicit non-goals. Added R7 and the TLS/secure-context constraint that LAN-direct imposes. Corrected the parity risk — Linux is the primary development platform since the move to Kubuntu; Windows is the side that drifts, controlled by the existing pre-release-then-promote gate. Noted the WSL functional path as effectively dead. |
| 2026-08-13 | Added R6 — full functionality on both Windows and Linux, with the desktop app itself serving mobile clients. Relay demoted to optional off-LAN transport; phases reordered so LAN-only phone posting lands before any hosted component. |

For the scheduling-specific portions of the 2026-08-13 and 2026-08-21 history (delegate
vs. local-queue research, Facebook API verification, email/SMTP failure reporting), see
[SCHEDULING.md's changelog](SCHEDULING.md#changelog).
