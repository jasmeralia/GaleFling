# GaleFling Android Port — Planning Document

> **SUPERSEDED (2026-08-13) by `docs/plans/SCHEDULING_AND_MULTI_CLIENT.md`.**
>
> This document assumed the device Rin holds must also be the device that posts. Two
> later facts invalidated that: Rin also wants **scheduled posting**, which no mobile OS
> can run reliably in-process, and her Windows 11 desktop is already on 24×7. Moving the
> posting work to that desktop and making the phone a thin client removes every blocker
> catalogued below, with no rewrite of `src/`.
>
> Moved to `docs/plans/old/` to keep superseded plans out of the active planning
> directory. Retained for reference only. The still-useful feasibility analysis — Qt WebEngine and
> `QtWebView` limits, PySide6-on-iOS constraints, mobile ffmpeg, native stack ranking,
> and iOS distribution — is carried forward in Appendix A of the superseding document.
> **Do not plan against this file.**

## Status

**Draft — spike not started.** This document captures feasibility, scope options, phased
milestones, stop/go criteria, and agent-driven execution guidance for packaging GaleFling
as an Android APK (target **Android 16 / API 36**).

Canonical repo path: `docs/plans/ANDROID_PORT.md`

---

## Executive summary

GaleFling is a **Windows-first PyQt6 desktop app** (~17k LOC in `src/`, ~21k LOC in
`tests/`) with two posting tiers:

| Tier | Platforms | Mechanism |
|------|-----------|-----------|
| **API** | Twitter, Bluesky, Instagram, Threads, Facebook | Background worker threads |
| **WebView** | OnlyFans, Fansly, FetLife (Snapchat disabled) | Embedded **Qt WebEngine** + JS automation |

**Packaging the current codebase as an APK is not feasible.** Qt WebEngine is documented
as supported only on Windows, Linux, and macOS — not Android. ffmpeg for Android exists and
is one of the *easier* pieces; the WebView tier is the critical path.

| Scope option | Calendar LOE (operator + agents) | Delivers |
|--------------|----------------------------------|----------|
| **A — API-only mobile companion** | ~4–8 weeks | Phone posting to API platforms only |
| **B — Full parity (incl. WebView platforms)** | ~3–5 months | GaleFling-equivalent on Android (high risk) |
| **C — Native rewrite (Kotlin/Compose)** | ~5–10 months | Best long-term Android product |

**Recommendation:** Run a **1-week spike** (Phase 0) before committing to A or B. If
mobile WebView login + manual post for one adult platform is painful, Option B is telling
you no regardless of agent speed.

---

## Why this is a port, not packaging

### Hard blockers

1. **No PyQt6-WebEngine on Android** — `src/platforms/base_webview.py` (~1,800 lines) and
   platform adapters assume `QWebEngineProfile`, `runJavaScript`, Chromium cookie DB
   (`sqlite3`), synthetic file uploads, and Cloudflare fingerprint consistency across
   profile reuse.
2. **No PyInstaller → APK** — Android needs NDK/SDK, cross-compiled Python wheels,
   buildozer/`pyside6-android-deploy`, permissions, content-URI media picking, and a new
   release pipeline.
3. **Desktop UX assumptions** — multi-tab `WebViewPanel`, setup wizard, mouse-driven
   WebView activation, Windows `ctypes` shell integration, AppData paths, WER log
   collection.

### Relatively portable

- API adapters (`twitter.py`, `bluesky.py`, `meta_*.py`)
- Media pipeline structure (`video_processor.py`, `image_processor.py`) — swap bundled
  ffmpeg for Android binary/`.so`
- Config/auth (`config_manager.py`, `auth_manager.py`) — JSON + Android Keystore
- Platform limits (`PlatformSpecs` in `constants.py`)

### Distribution note

Core WebView destinations (OnlyFans, Fansly, FetLife) make **Google Play distribution
unlikely**. Plan for sideload APK or private distribution channel from the start.

---

## Agent-driven execution model

When implementation is done exclusively through Claude / Codex / Cursor:

| Agents accelerate | Agents do not replace |
|-------------------|----------------------|
| PyQt6 → PySide6 mechanical conversion | Device/emulator testing (operator) |
| Android scaffolding (buildozer, permissions, ABI splits) | Live login flows, OAuth/PIN on phone |
| API adapter porting, unit test updates | WebView DOM probing on mobile sites |
| ffmpeg path wiring, boilerplate docs | Toolchain debugging (NDK/SDK first setup) |
| Repetitive platform adapter patterns | Long-horizon architectural coherence without a written plan |

**New bottleneck:** operator time running the build/test loop daily. Token cost is usually
noise compared to integration and QA labor.

**Mandatory project conventions for agents:**

- Follow Release Checklist after code changes (`make lint`, `make test-cov`).
- Never stage with `git add -A` / `git add .`.
- Tests and core code stay in sync (rule 7 in `AGENTS.md`).
- Platform display names use canonical casing (Fansly, OnlyFans, FetLife, etc.).
- WebView platforms may not be marked “done” until operator confirms a live tagged post.
- Do not “finish” WebView work with mocks that diverge from real mobile browser behavior.

---

## Decision fork (choose during Phase 0)

### Option A — API-only mobile companion

**Include:** Twitter, Bluesky, Instagram, Threads, Facebook  
**Exclude (v1):** OnlyFans, Fansly, FetLife WebView automation  
**UI:** Touch-friendly composer; hide unavailable platforms in setup/post UI  
**Honest product message:** “Mobile companion for API platforms”

### Option B — Full parity

Everything in A, plus reimplement WebView tier on Android `WebView` (or Custom Tabs for
login only + embedded WebView for compose):

- Per-account cookie/session isolation
- JS prefill equivalent to desktop selectors
- Media attach via Android content URIs (not desktop file-input synthesis)
- Post confirmation and permalink capture (accept SPA “posted, link unavailable”)
- Cloudflare / bot-management re-challenges on mobile layouts

**High uncertainty:** mobile web UIs may differ enough from desktop Chromium that
automation breaks silently.

### Option C — Native rewrite

Kotlin/Jetpack Compose shell + WebView module; shared rules extracted or duplicated.
Only consider if B spike fails but mobile remains a hard requirement.

---

## Phase 0 — Spike (1 week, stop/go gate)

**Goal:** Prove toolchain + one API post + one raw WebView login before any large branch.

### Milestones

| # | Deliverable | Owner | Pass criteria |
|---|-------------|-------|---------------|
| 0.1 | Android dev environment doc | Agent | Linux host, SDK/NDK, emulator or device documented in `docs/testing/ANDROID_TESTING.md` |
| 0.2 | PySide6 shell APK | Agent | App launches on `arm64-v8a` emulator/device |
| 0.3 | One API post E2E | Agent + operator | Bluesky or Twitter test post from phone with functional-test tag |
| 0.4 | Raw WebView login page | Agent + operator | Operator logs into OnlyFans *or* Fansly in unautomated WebView |
| 0.5 | Manual post in WebView | Operator | Operator completes one post by hand on mobile web |
| 0.6 | Spike report | Agent | Go/no-go for A vs B with screenshots and blockers |

### Stop/go criteria

- **Go Option A** if 0.2 + 0.3 pass and WebView manual flow (0.4–0.5) is acceptable as
  future scope only.
- **Go Option B** only if 0.4–0.5 are tolerable *and* operator believes mobile DOM is
  automatable (file upload path identified, no hard blockers).
- **Stop / defer** if toolchain cannot produce a debug APK within spike week, or mobile
  sites are materially different from desktop automation assumptions.

### Agent PRs (spike)

1. `docs/testing/ANDROID_TESTING.md` — environment setup only  
2. `android-spike/` or `tools/android/` — minimal PySide6 deploy config (no GaleFling UI yet)  
3. Optional: `docs/plans/ANDROID_PORT.md` updates with spike results  

---

## Phase 1 — Foundation (Option A: ~2–3 weeks)

**Branch:** `feature/android-foundation`

### Work items

1. **Project layout**
   - `tools/android/` — buildozer / `pyside6-android-deploy` config
   - `build/android/` — signing templates (gitignored keystores)
   - Entry point `main_android.py` or adapt `src/main.py` with platform gate

2. **PyQt6 → PySide6 conversion strategy**
   - Prefer incremental: shared `src/` with `# platform android` branches only where
     necessary, or a thin Android shell importing shared core
   - Modules needed for Option A: QtCore, QtGui, QtWidgets, QtNetwork — **not** WebEngine

3. **App data paths**
   - Extend `get_app_data_dir()` in `helpers.py` for Android scoped storage
   - Auth dir, drafts, logs under app-private storage

4. **ffmpeg on Android**
   - Bundle `ffmpeg`/`ffprobe` for `arm64-v8a` (and `x86_64` for emulator)
   - Update `get_ffmpeg_path()` / `_run_subprocess()` in `video_processor.py`
   - Verify one video resize + thumbnail extraction on device

5. **Credentials**
   - File-based auth (existing JSON model) for v1
   - Optional: Android Keystore wrapper later

6. **Release checklist parity**
   - `make lint` / `make test-cov` unchanged on desktop branch
   - Document Android-specific verification steps in `ANDROID_TESTING.md`

### Exit criteria

- Debug APK installs on physical device
- App opens composer shell (even if minimal)
- ffmpeg probe succeeds in About/diagnostics

---

## Phase 2 — API posting on Android (Option A: ~2–3 weeks)

**Branch:** `feature/android-api-posting`

### Work items

1. Port GUI flows (touch-first):
   - Platform selector, composer, results dialog (subset)
   - Setup wizard simplified for mobile (OAuth/PIN flows need WebView or external browser)

2. API platforms (priority order):
   - Bluesky (simplest auth)
   - Twitter (PIN flow — needs UX for phone)
   - Meta family (OAuth redirect — may need Custom Tabs + deep link)

3. Media pipeline:
   - Photo/video picker via Android content URIs → temp files → existing processors
   - Platform-group media prep unchanged in logic

4. Background posting:
   - Respect Android background limits; keep worker on foreground service or in-process
     with clear “posting…” UI (no silent failure)

5. Unit tests:
   - Mock Android paths in processor tests
   - Do not claim functional parity without device tests

### Exit criteria

- Operator posts text + image to ≥2 API platforms from phone
- Logs capturable and shareable (existing log upload path or simplified export)
- Platforms not supported on Android are hidden, not broken

---

## Phase 3 — WebView tier (Option B only: ~8–12 weeks)

**Branch:** `feature/android-webview`

### Architecture

Replace `QWebEngine*` with Android WebView bridge:

```
src/platforms/android_webview/
  base_android_webview.py    # session, navigation, JS bridge
  onlyfans_android.py
  fansly_android.py
  fetlife_android.py
```

**Do not** pretend-drop-in `base_webview.py`; extract *behaviors* (selectors, timeouts,
success patterns) into shared constants, reimplement transport on Android.

### Work items per platform

| Concern | Desktop today | Android target |
|---------|---------------|----------------|
| Session cookies | `QWebEngineProfile` + Cookies DB | `CookieManager` + isolated WebView storage per `account_id` |
| Text prefill | `runJavaScript` | `@JavascriptInterface` or `evaluateJavascript` |
| Media attach | Synthetic file input events | `WebChromeClient.onShowFileChooser` + content URI |
| Success detection | URL regex + DOM polling | Same logic, revalidated on mobile DOM |
| Cloudflare | Shared profile fingerprint | Spike whether mobile WebView passes; may need login-only Custom Tabs |

### Testing

- New functional test harness (not Windows VM):
  - Physical device or dedicated Android emulator with credentials via env (never log secrets)
  - One mutating test per platform with cleanup-pending tag protocol from `AGENTS.md`
- Operator gate on every platform before merge

### Exit criteria

- Automated post (or operator-confirmed semi-auto) for OnlyFans, Fansly, FetLife
- Parity table in this doc updated with known gaps

---

## Phase 4 — Release engineering (~1–2 weeks)

1. **Signing** — release keystore (operator-held, never committed)
2. **ABI splits** — `arm64-v8a` minimum; optional universal APK
3. **Updates** — out-of-band APK + in-app version check (adapt `update_checker.py` or
   document manual updates for sideload)
4. **CI** — optional GitHub Action to build debug APK (no secrets in CI)
5. **Docs** — `docs/testing/ANDROID_TESTING.md`, README section (sideload install steps)

---

## LOE summary

| Phase | Option A | Option B |
|-------|----------|----------|
| Phase 0 Spike | 1 week | 1 week |
| Phase 1 Foundation | 2–3 weeks | 2–3 weeks |
| Phase 2 API posting | 2–3 weeks | 2–3 weeks |
| Phase 3 WebView | — | 8–12 weeks |
| Phase 4 Release | 1–2 weeks | 1–2 weeks |
| **Total** | **~4–8 weeks** | **~3–5 months** |

Estimates assume operator runs device verification daily. Add 50–100% if toolchain or
mobile site behavior blocks automation.

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Qt WebEngine absence forces full WebView rewrite | Certain | High | Phase 0 manual WebView test |
| Mobile site DOM ≠ desktop selectors | High | High | Per-platform mobile validation; shared selectors only where proven |
| PySide6 Android toolchain friction | Medium | Medium | Official Qt 6.11 wheels for `aarch64`; pin versions in doc |
| OAuth/PIN on phone UX | Medium | Medium | Custom Tabs + deep links; spike Meta/Twitter early |
| Play Store rejection | High (adult) | Low if sideload | Plan sideload from day one |
| Agent drift across sessions | Medium | Medium | This doc + checklists; small PRs |
| No Android regression harness | High | High | `ANDROID_TESTING.md` before Phase 1 merge |

---

## Agent work breakdown (suggested Odoo subtasks)

1. Phase 0.1 — Document Android dev environment  
2. Phase 0.2 — PySide6 hello-world APK  
3. Phase 0.3 — Spike API post (Bluesky)  
4. Phase 0.4–0.5 — WebView manual login/post spike + report  
5. Phase 1 — Foundation (paths, ffmpeg, shell)  
6. Phase 2 — API-only mobile companion  
7. Phase 3 — WebView reimplementation (Option B gate)  
8. Phase 4 — Signing, sideload release, CI  

---

## References

- `docs/ARCHITECTURE_OVERVIEW.md` — two-tier posting model  
- `docs/platforms/PLATFORM_SPECS.md` — platform limits and API vs WebView  
- `src/platforms/base_webview.py` — WebView assumptions to reimplement or exclude  
- [Qt WebEngine supported platforms](https://doc.qt.io/qtforpython-6/overviews/qtwebengine-overview.html) — desktop only  
- [Qt for Python Android deploy](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-android-deploy.html)  
- `AGENTS.md` — mandatory agent rules and release checklist  

---

## Changelog

| Date | Change |
|------|--------|
| 2026-08-13 | Initial draft from feasibility / agent-LOE discussion |
