# GaleFling — Scheduling Design

## Status

**Draft — Phase 0 resolved, Phase 1 not started.** Split out of the combined
`SCHEDULING_AND_MULTI_CLIENT.md` plan on 2026-08-21 (Jas) — scheduling and mobile/LAN
access are handled in entirely different phases and no longer need to share one
document. See [docs/plans/MOBILE_LAN_ACCESS.md](MOBILE_LAN_ACCESS.md) for the mobile
client / embedded server work; that document remains the canonical source for the
overall desktop-resident-server architecture, the IP-identity rationale for why posting
never leaves Rin's machine, and R1/R5/R6/R7. This document owns scheduling only: R2,
R4, and everything under [Scheduling design](#scheduling-design).

Tracked in Odoo **#450**. Mobile/LAN access is tracked separately in Odoo **#451**
(both split from the original combined plan/index, Odoo **#426**, on 2026-08-16).

OnlyFans and Fansly are paused in the app as of 2026-08-16 (`available=False` —
aggressive automation-detection/banning risk; see `docs/platforms/ONLYFANS.md` /
`docs/platforms/FANSLY.md`). Every reference to them below as delegated-scheduling
targets is historical: if reactivated, they would delegate via UI automation (drive the
composer once, set a future time) — a different mechanism from the API-scheduling
question this document resolves, and unaffected by the decision below.

Canonical repo path: `docs/plans/SCHEDULING.md`

---

## Executive summary

Rin asked for scheduled posts: hold several drafts, pick a future time for each, and be
able to see, edit, or cancel anything still pending. The scheduler that fires those
posts has to be **something that is already always-on** — Rin's desktop, powered 24×7 —
because scheduled posting cannot run on a phone (see
[MOBILE_LAN_ACCESS.md](MOBILE_LAN_ACCESS.md#executive-summary) for why) and cannot run
server-side (see [Why the poster stays on her machine](MOBILE_LAN_ACCESS.md#why-the-poster-stays-on-her-machine)
for the IP-identity reasoning).

The scheduling-specific design question this document resolves is narrower: **for each
platform, does GaleFling hand the future-dated post to the platform's own API, or hold
it in a local queue and fire it itself at the due time?** As of 2026-08-21 the answer is
uniform — every schedulable platform holds in one local queue, even though one platform
(Facebook Page) does support real API-level scheduling. See
[Delegation investigated, decided against](#delegation-investigated-decided-against--local-queue-for-every-schedulable-platform).

---

## Requirements

From Rin, carried over from the combined plan:

- **R2** — Schedule a post for a future time, and **manage what is queued**: hold
  several pending posts at once, see them, and edit or cancel any of them before it
  fires. Carried over from Odoo #392, whose research fed into the original combined plan.

Derived:

- **R4** — When GaleFling attempts a scheduled post and it fails, that failure must be
  reported, not swallowed. Scope is GaleFling reporting its own failures; the health of
  the machine it runs on is out of scope (see
  [MOBILE_LAN_ACCESS.md](MOBILE_LAN_ACCESS.md#explicitly-not-in-scope-monitoring-rins-machine)).

R3 (posting must continue to originate from Rin's own machine and network) is defined in
[MOBILE_LAN_ACCESS.md](MOBILE_LAN_ACCESS.md#why-the-poster-stays-on-her-machine) and
applies here without restatement: the local queue's due-time poller runs in the same
process, on the same machine, under the same IP-identity constraint as interactive
posting.

---

## Scheduling design

### Delegation investigated, decided against — local queue for every schedulable platform

There is a useful inversion in theory: the platforms that are hardest to automate are the
ones that can absorb the scheduling themselves, and driving a composer once to set a future
post in the platform's own scheduler survives the desktop being off, rebooting, or losing its
network at post time. In practice, only one active platform actually offers that.

**Resolved 2026-08-21 (Odoo #450).** Checked against Meta's current developer docs (Pages API
"Posts" guide, updated Apr 17 2026; Graph API Reference v26.0 Feed; Instagram Platform
"Content Publishing," updated Jun 22 2026):

- **Facebook Page — the only platform with real API-level scheduling.** `POST /{page-id}/feed`
  with `published=false` and a future `scheduled_publish_time` is live in both current doc
  pages, resolving a contradiction between earlier research (Odoo #392, 2026-07-31) and a
  2026-08-13 review that reached the opposite conclusion, in favor of "it works."
- **Instagram — no API scheduling.** The Content Publishing API has no
  `scheduled_publish_time` parameter or equivalent. Publishing is a two-step container model
  (`POST /media` → `POST /media_publish`) where the publish call goes live immediately, and
  containers expire 24 hours after creation regardless, so pre-staging far ahead isn't
  possible either way. Meta's 2021 "schedule and publish" announcement language described
  third parties building their own scheduler on top of the API, not a native capability.
- **Threads — no API scheduling**, same shape as Instagram: no schedule parameter on the
  public Threads API. Meta runs a private scheduling beta with select partners (Hootsuite,
  Sprinklr, EmbedSocial) that GaleFling has no access to.
- **Instagram→Facebook crosspost, Page vs. personal account** (asked separately): crossposting
  requires a Facebook Page — a personal Instagram account can't crosspost at all, and a
  professional Instagram account can only link to a Page, never a personal profile. Not
  relevant to the design decision below, but noted for completeness.

**Decision (Jas, 2026-08-21): don't delegate to Facebook either — hold every schedulable
platform in the local queue, uniformly.** With only one platform actually supporting API
scheduling, splitting the implementation into two code paths (delegate vs. local queue) buys
one platform's worth of off-desktop resilience at the cost of a second scheduling mechanism to
build, test, and maintain — including reaching back into Facebook's own scheduler to edit or
cancel an item, which the queue-management requirement (R2) needs to support symmetrically
either way. Consistency wins: every schedulable platform behaves identically from the user's
perspective, and the discrepancy between Meta's two current docs pages on Facebook's actual
scheduling window (Pages API guide: 10 minutes–30 days; Graph API Reference v26.0: 10
minutes–75 days) becomes moot, since GaleFling's own poller enforces whatever window the local
queue design settles on instead of inheriting Facebook's. **Revisit if warranted** — e.g. if
Instagram or Threads ever gain real API scheduling, making delegation's off-desktop-resilience
case apply to more of the unattended workload, or if Facebook's local-queue reliability proves
worse than delegating in practice.

- **FetLife — ineligible for scheduling, not local-queued.** This is unaffected by the
  delegation decision above; it was never a delegation candidate. Its posting path is WebView,
  human-confirmed (`docs/ARCHITECTURE_OVERVIEW.md`), and its own session check deliberately
  skips the headless connection test because Cloudflare fingerprints a headless
  `QWebEnginePage` and bounces it to `/login` (`docs/platforms/FETLIFE.md`). An unattended
  local-queue fire at 2 a.m. would either break against Cloudflare running headless, or pop an
  unexpected browser window demanding a manual click at an arbitrary future time — neither is
  scheduled posting. FetLife is excluded from the schedulable-platform picker outright, with
  an explanation, rather than treated as a queue member alongside the API platforms.

| Platform | Native API scheduling exists? | Used by GaleFling? |
|----------|-------------------------------|---------------------|
| OnlyFans *(paused)* | Product-level yes (UI automation, not API) | Was **Delegate** — drive the composer once, set a future time. Not pursued while paused. Different mechanism from the API-scheduling question above; unaffected by the 2026-08-21 decision. |
| Fansly *(paused)* | Product-level yes (UI automation, not API) | Was **Delegate**, same as OnlyFans. Not pursued while paused. |
| Facebook Page | **Yes** — `scheduled_publish_time` confirmed working | **No — local queue**, by decision, for cross-platform consistency |
| Instagram | No — two-step container, no schedule param | Local queue |
| Threads | No — no schedule param | Local queue |
| Bluesky | No | Local queue |
| Twitter | Not in the v2 API | Local queue |
| FetLife | No — WebView, human-confirm required | **Ineligible for scheduling** (excluded, not local-queued) |

Every currently-active schedulable platform (Facebook, Instagram, Threads, Bluesky, Twitter)
now goes through the same local queue and due-time poller. FetLife alone is excluded from
scheduling. OnlyFans/Fansly's UI-automation delegation model is orthogonal to this decision
and stays as documented if either is reactivated.

### Local queue

Every schedulable platform — Facebook, Instagram, Threads, Bluesky, Twitter — goes through one
SQLite-backed queue in the existing app data directory, a due-time poller in the poster
process, and per-item state (`pending` → `in_flight` → `posted` / `failed`). **FetLife is not
part of this queue**: see the resolved table above — it is excluded from the
schedulable-platform picker entirely, because its posting path requires a human present to
confirm in a WebView tab and cannot run headless against Cloudflare.

**Queue management is part of R2, not a later nicety.** Several posts may be pending at
once, and Rin must be able to see the queue, edit a pending item, and cancel one — from
the desktop GUI and, once it exists, from the mobile client (see
[MOBILE_LAN_ACCESS.md](MOBILE_LAN_ACCESS.md)) alike. With the no-delegation decision above,
every schedulable platform's pending items are held identically, so this editing/cancelling
behavior is symmetric across platforms — there is no platform whose pending item lives in a
remote scheduler instead of this queue.

### Not failing silently (R4)

R4 covers exactly one thing: **GaleFling tried to post something and it did not work.**
Interactive posting already fails loudly, since Rin is present and sees the error.
Scheduled posting is the case that can fail unobserved, because nobody is watching at post
time.

Three channels, none of which need a service worker or a notification model:

- **Email over SMTP.** The natural channel for something that happens while nobody is
  looking: it reaches Rin and Jas on any device without the phone client being open, and
  needs no service worker, no notification model, and no secure context. See
  [Email configuration](#email-configuration) — this is chosen over SES specifically
  because it can be pre-configured for Rin rather than set up by her.
- **Visible failure state in the desktop GUI**, alongside the existing results dialog.
- **The existing log-upload path**, for diagnosis after the fact.

**Startup reconciliation** covers the adjacent correctness problem — not losing work when
the app restarts. On launch the queue is re-examined and anything whose due time passed
while the app was down is resolved rather than silently skipped. Open design question:
whether to post it late, or past some staleness threshold to mark it missed and notify
instead. A caption tied to a specific time or event is worse posted three days late than
not posted at all, so the threshold should probably be short and configurable.

Delegated posts (OnlyFans and Fansly while paused — their UI-automation delegation model is
unaffected by the 2026-08-21 no-Facebook-delegation decision) sidestep this entirely — the
platform fires them whether or not the desktop was up — and are reconciled on the next
session by checking whether the platform actually published. Every other schedulable
platform, Facebook included, now goes through startup reconciliation like the rest of the
local queue.

A Windows Update reboot is a common way for the desktop to miss a due time unattended; see
[MOBILE_LAN_ACCESS.md#windows-session-constraints](MOBILE_LAN_ACCESS.md#windows-session-constraints)
for why the poster can't be installed as a Windows service and what that implies for
autologon and session restore. Startup reconciliation, above, is what catches anything
whose due time passed during that kind of outage.

### Shutdown awareness (R4)

**Resolved 2026-08-21 (Phase 0.1, Jas): Rin does not have sleep configured, but she does
sometimes fully shut down the machine when not in active use.** This retires the "desktop
sleeps despite being powered" risk — nothing to mitigate there — but surfaces a more
consequential one: unlike sleep, a full shutdown doesn't self-heal on its own the way
autologon + session restore handles a Windows Update reboot (see
[MOBILE_LAN_ACCESS.md#windows-session-constraints](MOBILE_LAN_ACCESS.md#windows-session-constraints));
the machine stays off until Rin manually turns it back on, so a scheduled post's window can
pass with nobody around to notice. This is routine behavior for her, not an edge case, so it
needs a real mitigation rather than just startup reconciliation catching it after the fact.

Two pieces, both scoped to Windows (Rin's platform — see the Linux note below):

1. **Composer-time warning.** The schedule picker shows a persistent reminder that
   scheduled posts require the computer to stay on and logged in, and that shutting down
   will prevent them from firing on time. Static, not conditional on anything — she should
   see this every time she schedules, not just when something is already pending.
2. **Shutdown-block prompt while a post is pending.** While the local queue holds ≥1
   pending item, the poster process (running as the tray/background entry point — see
   [MOBILE_LAN_ACCESS.md#windows-session-constraints](MOBILE_LAN_ACCESS.md#windows-session-constraints))
   handles `WM_QUERYENDSESSION` and calls `ShutdownBlockReasonCreate` with a reason string
   naming the pending post(s), so Windows shows its native "this app is preventing
   shutdown" dialog instead of GaleFling silently losing the window. Rin can proceed with
   the shutdown from that dialog if she means to — this is a courtesy prompt, not a lock.

**Reboot vs. shutdown — open technical question, needs a Phase 0/1 spike before relying on
it.** The ask is that a restart shouldn't trigger the same prompt, since autologon +
session restore already means a restart self-heals. But `WM_QUERYENDSESSION`'s `lParam`
does not cleanly expose "this is a restart" vs. "this is a full power-off" to a listening
application — only `ENDSESSION_LOGOFF`, `ENDSESSION_CRITICAL`, and `ENDSESSION_CLOSEAPP`
are documented flags, none of which distinguish reboot from shutdown. Two candidate
approaches:

   - **Query the System event log for Event ID 1074** (logged by the component that
     requested the shutdown/restart, with a human-readable reason that does distinguish
     them) shortly after the query fires. Fragile: needs Event Log read permissions, and
     there's no guarantee the 1074 entry is written and readable before GaleFling has to
     decide whether to return `FALSE` from the handler.
   - **Don't try to distinguish upfront.** Show the block/prompt on every
     `WM_QUERYENDSESSION` uniformly, and satisfy "reboots shouldn't need the same prompt"
     through the already-planned autologon + startup reconciliation making a restart
     self-heal quickly — so in practice a restart costs Rin, at worst, one extra dialog
     dismissal rather than a real failure. This is the pragmatic default unless the spike
     finds event-log detection reliable enough to trust.

Either way, **`ENDSESSION_CRITICAL` shutdowns cannot be blocked by any app** — some
Windows-Update-forced restarts fall into this category, and the OS proceeds regardless of
what the handler returns. The block/prompt is a best-effort courtesy on top of startup
reconciliation, which remains the actual safety net for anything that gets through
unprompted.

**Linux note:** this entire mechanism is Windows-specific because Rin's machine is
Windows. Linux has an analogous inhibitor-lock mechanism (`systemd-logind`'s `Inhibit()`
D-Bus call, or the `systemd-inhibit` CLI wrapper) if parity is ever wanted for R6, but it
is not scoped now — nothing in this design requires it to ship.

#### Email configuration

SMTP is preferred over SES for an R5 reason rather than a technical one: **it can ride the
credential import Jas already hands Rin.** `src/core/credential_importer.py` is versioned,
accepts partial imports, and already carries `meta`, `twitter`, and `aws` sections; an
`smtp` section alongside them means host, port, username, app password, and recipients all
arrive pre-filled. Rin configures nothing and sees no mail settings unless she goes
looking. SES would mean AWS identity verification and a sending-domain setup with no
corresponding benefit at this volume.

Gmail specifics worth pinning down before implementation:

- `smtp.gmail.com` port 587 with STARTTLS (or 465 implicit TLS). Outbound only, and no
  different in posture from the platform APIs and S3 uploads the app already makes.
- **An App Password is required** — Google removed plain-password SMTP access, and
  generating an App Password requires 2-Step Verification on the account.
- The `From:` header is rewritten to the authenticated account unless a verified alias is
  used, so the sending identity is whoever owns the mailbox.
- Free-account sending limits are around 500 messages/day, which is irrelevant here.

**Mailbox — decided: a dedicated Google Workspace account**, roughly $5/month for the
extra user.

The reasoning is a trust-boundary one rather than a technical one. gelfling, rinling, and
TrueNAS are single-operator machines, so personal credentials on them are acceptable.
Rin's desktop is not: an application running on a machine someone else uses should not
hold a credential tied to a personal identity, however narrowly that credential is scoped.
Having her generate her own is equally wrong — it would require walking her through
enabling 2-Step Verification, exactly the class of step R5 exists to remove.

A dedicated account contains the blast radius to "can send mail from a mailbox that holds
nothing," and it is the same account intended to consolidate server-generated mail — see
Odoo task **#427**, routing exim on rin-city.com through the Workspace SMTP relay instead
of sending directly from EC2.

Use a **separate App Password per host**, so Rin's machine can be revoked independently of
the servers. The App Password is a credential like any other: stored through `AuthManager`
(`keyring` is already a dependency), never logged, and covered by the same handling rules
as platform credentials.

---

## Phase 0 — Spike and confirmation (scheduling-relevant items)

| # | Deliverable | Owner | Pass criteria |
|---|-------------|-------|---------------|
| ~~0.2~~ | ~~Delegated scheduling spike~~ | **Resolved 2026-08-21 via docs — no delegation, no spike needed** | Instagram and Threads Content Publishing APIs have no `scheduled_publish_time` equivalent — confirmed against current Meta docs. Moot regardless of the finding, since delegation isn't being pursued for any active platform (see decision above). |
| ~~0.3~~ | ~~Facebook: direct Graph API scheduling~~ | **Resolved 2026-08-21 via docs, then decided against** | `published=false` + `scheduled_publish_time` on `/{page-id}/feed` is confirmed current and working, but Jas decided 2026-08-21 not to use it — every schedulable platform holds in the local queue instead, for a single consistent mechanism. No live-fire spike needed since it won't be built. |
| ~~0.3b~~ | ~~Facebook-via-Instagram crosspost~~ | — | Not needed — moot twice over: 0.3 resolved positively, and delegation isn't being pursued anyway. |

0.2 and 0.3 are resolved by documentation research; 0.2's finding (no Instagram/Threads
delegation) and the decision to skip Facebook delegation too both point the same direction —
**no platform-side delegation for Phase 1**, one local queue for every schedulable platform,
FetLife excluded from scheduling entirely. Delegation stays documented as an option to revisit
if more platforms gain real API scheduling later.

Phase 0.1 (confirm Rin's sleep + autologon settings) and 0.4 (mDNS + media upload spike)
are mobile/LAN-access items — see
[MOBILE_LAN_ACCESS.md#phase-0--spike-and-confirmation](MOBILE_LAN_ACCESS.md). 0.1 also
matters here, since the scheduler needs the desktop actually awake to fire on time, but it
is tracked as one item rather than duplicated.

## Phase 1 — Scheduler in the desktop app (~2–3 weeks)

Schedule queue, due-time poller, background/tray operation, missed-window handling, and the
Windows shutdown-block prompt (see [Shutdown awareness](#shutdown-awareness-r4)) — one
uniform path for every schedulable platform, no delegated-vs-local routing to build for the
active platform set (OnlyFans/Fansly's separate UI-automation delegation stays dormant while
paused). Deliverable: **a post scheduled from the existing desktop GUI fires correctly with
the app minimized**, on both Windows and Linux. No phone involved yet. This alone satisfies R2.

This is the entire scheduling-side deliverable; mobile client work is
[Phase 2](MOBILE_LAN_ACCESS.md#phase-2--embedded-server--mobile-client-34-weeks) and does not
block it.

---

## Risk register (scheduling-relevant)

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Windows Update reboot strands the poster at the lock screen | Medium | High | Autologon + session restore; startup reconciliation posts anything missed during the outage, late and flagged |
| ~~Desktop sleeps despite being powered~~ | — | — | **Resolved 2026-08-21 (Phase 0.1):** confirmed Rin does not have sleep configured. Not a real risk; nothing to mitigate. |
| Rin manually shuts down the machine when not in active use, silently dropping pending scheduled posts | **High** — confirmed routine behavior, not an edge case | High | See [Shutdown awareness](#shutdown-awareness-r4): composer-time warning plus a `WM_QUERYENDSESSION`/`ShutdownBlockReasonCreate` prompt while a post is pending, backstopped by startup reconciliation for anything that still gets through |
| Local-queue posting breaks when a platform's API changes | Medium | Medium | Same fragility as posting today; reconcile after the fact |
| Cloudflare behavior changes on Fansly/OnlyFans | Medium | High | Unchanged from today; posting stays on her machine and IP. Not a scheduling risk per se — those platforms are paused — but retained here since a reactivation would restore their delegated-scheduling model. |

Windows drift, mDNS failure, and the mobile-specific risks live in
[MOBILE_LAN_ACCESS.md#risk-register](MOBILE_LAN_ACCESS.md#risk-register).

---

## Open questions

1. What staleness threshold should startup reconciliation use before marking a due post
   missed rather than posting it late?
2. Can GaleFling reliably distinguish a restart from a full shutdown at
   `WM_QUERYENDSESSION` time, well enough to skip the block/prompt on restarts
   specifically? See [Shutdown awareness](#shutdown-awareness-r4) — needs a spike before
   Phase 1 build-out; the pragmatic fallback (prompt uniformly, lean on autologon +
   startup reconciliation for restarts) doesn't need this answered first.

Rin's autologon state and mDNS resolution are mobile/LAN-access open questions — see
[MOBILE_LAN_ACCESS.md#open-questions](MOBILE_LAN_ACCESS.md#open-questions). Her sleep
settings are resolved above (Phase 0.1) — not configured, not a risk.

---

## References

- `docs/plans/MOBILE_LAN_ACCESS.md` — architecture, IP-identity rationale, R1/R3/R5/R6/R7,
  Phase 0.1/0.4/2/3
- `docs/ARCHITECTURE_OVERVIEW.md` — two-tier posting model
- `docs/platforms/PLATFORM_SPECS.md` — platform limits and API vs WebView
- `docs/platforms/FETLIFE.md` — WebView session/Cloudflare behavior behind the
  scheduling-ineligibility decision
- `AGENTS.md` — mandatory agent rules and release checklist

---

## Changelog

| Date | Change |
|------|--------|
| 2026-08-21 | Resolved Phase 0.1 (Jas): Rin does not have sleep configured, retiring that risk, but she does routinely fully shut down the machine when not in active use — a bigger risk than sleep would have been, since it doesn't self-heal the way a reboot does. Added [Shutdown awareness](#shutdown-awareness-r4): a composer-time warning plus a Windows `WM_QUERYENDSESSION`/`ShutdownBlockReasonCreate` prompt while a post is pending, added to Phase 1 scope. Flagged reboot-vs-shutdown detection as an open technical question (`ENDSESSION_CRITICAL` shutdowns can't be blocked by any app regardless), with a pragmatic fallback that doesn't depend on resolving it before Phase 1. |
| 2026-08-21 | Split out of `docs/plans/SCHEDULING_AND_MULTI_CLIENT.md` into this scheduling-only document (Jas): scheduling and mobile/LAN access are handled in entirely different phases and no longer need one shared file. Content carried over verbatim from the combined plan's scheduling-relevant sections; mobile/LAN content moved to `docs/plans/MOBILE_LAN_ACCESS.md`. |
| 2026-08-21 | Resolved the API-vs-product scheduling gap flagged in Odoo #450, against Meta's current developer docs. Facebook Page is confirmed to support real API-level scheduling (`scheduled_publish_time` live on `/{page-id}/feed`), resolving the #392-vs-2026-08-13 contradiction — but Jas then decided **not** to delegate to it: every schedulable platform (Facebook, Instagram, Threads, Bluesky, Twitter) holds in one uniform local queue instead, trading Facebook's off-desktop resilience for a single scheduling mechanism instead of two, and mooting the scheduling-window discrepancy between Meta's own doc pages (30 vs 75 days) since GaleFling's poller no longer needs it. Revisit if more platforms gain real API scheduling later. Separately, confirmed Instagram and Threads have **no** API scheduling at all — neither Graph API exposes a scheduling parameter, only a two-step immediate-publish container model — so they were never delegation candidates regardless of the Facebook decision. FetLife reclassified from "local queue" to **ineligible for scheduling, excluded from the picker**: its posting path is WebView/human-confirmed and its session check already skips headless validation due to Cloudflare fingerprinting, so an unattended fire would either break or ambush the user with a surprise composer window. Also answered: Instagram→Facebook crossposting requires a linked Facebook Page and cannot use a personal profile at all — moot for the design now, noted for completeness. |
| 2026-08-13 | Carried forward the findings of Odoo #392 ("Look into scheduling support"), a research task now completed. Added queue management to R2 — multiple pending posts, editable and cancellable — which the plan had not stated. Flagged a direct contradiction on Facebook: #392 recorded `scheduled_publish_time` as working, a 2026-08-13 review did not; resolving it became Phase 0.3, and an Instagram-crosspost workaround was demoted to a fallback (later dropped entirely — see 2026-08-21 entries above). |
| 2026-08-13 | Separated two problems that had been conflated (Jas): GaleFling reporting its own posting failures is in scope and best served by email; whether Rin's machine is up is **not** monitored and not Jas's responsibility. Dead-man's switch dropped entirely rather than scoped. Startup reconciliation reframed as queue correctness rather than alerting, with a staleness threshold noted as an open design question. |
| 2026-08-13 | Rewrote R4/alerting: split app-running from app-not-running failures, promoted startup queue reconciliation to the primary defence, scoped the dead-man's switch to sustained outages only, and removed a stale reference to pushing to paired devices — there is no push channel in the baseline. |
| 2026-08-13 | Failure notification settled on SMTP over SES (Jas), delivered through the existing credential-import file as a new `smtp` section so Rin configures nothing. Gmail App Password requirements documented. Mailbox decided: a dedicated Google Workspace account, on the trust-boundary reasoning that a machine someone else uses should not hold personal credentials. Shared with Odoo #427 (exim relay). |
| 2026-08-13 | Facebook Page scheduling reframed as delegable indirectly, by letting a scheduled Instagram post crosspost to the linked Page (Jas). Added as Phase 0.3. (Superseded 2026-08-21 — direct delegation confirmed working, then decided against entirely.) |
| 2026-08-13 | Native-scheduling table confirmed by Jas at the product level (Threads and Instagram yes; Facebook and FetLife no). (Superseded 2026-08-21 — API-level verification found the opposite for Instagram/Threads vs. Facebook.) |
| 2026-08-13 | Initial draft, as part of the combined `SCHEDULING_AND_MULTI_CLIENT.md` plan. See that document's changelog (now `MOBILE_LAN_ACCESS.md`) for the full original history. |
