# WebView Functional Testing — Multi-Phase Plan

**Status:** Phase 1 implemented; Phases 2–7 not started
**Created:** 2026-08-10
**Owner:** Jas
**Tracks:** GitHub issue #1 (WebView2 migration), `debug_state.md`

## Purpose

Establish a reproducible loop for debugging the three long-standing WebView defect
classes — renderer crashes, checkbox clicks not registering, and sessions not
persisting — by making Linux the primary test host and adding a scriptable Windows
VM for target-platform confirmation.

Windows remains the primary target platform. Linux does not replace Windows testing;
it narrows the gap so Windows testing can be targeted and infrequent.

## How to use this document

Each phase is self-contained: goal, prerequisites, tasks with explicit file paths,
acceptance criteria, and non-goals. Phases 1 and 2 are independent of each other and
of all hardware work. A phase may be handed to another agent by giving it this
document plus the phase number.

Phases 3–4 depend on hardware/BIOS changes only Jas can perform (Appendix A).

---

## Verified baseline

Established 2026-08-10 on `typhoon` by direct measurement. Re-verify before relying
on any of it — these are point-in-time observations.

| Fact | Evidence |
|---|---|
| Repo is on **Chromium 140**, not 134 | `QWebEngineProfile.httpUserAgent()` → `QtWebEngine/6.11.1 Chrome/140.0.0.0`; `requirements.txt` pins `PyQt6-WebEngine>=6.11.0` |
| The bump was untested | Arrived via Dependabot batch `e54b858` (2026-05-07), "Bump the python-dependencies group with 18 updates" |
| `www.snapchat.com/web/` did **not** crash the renderer | 45 s probe, offscreen, no `renderProcessTerminated`. **Logged out** — redirected to `/?original_referrer=none`, so the 8.3 MB bundle likely never executed. Not conclusive. |
| Hardware WebGL works from a non-interactive shell | `DISPLAY=:0` → `ANGLE (NVIDIA GeForce RTX 2080 SUPER, OpenGL 4.5.0)`; `WAYLAND_DISPLAY=wayland-0` → `ANGLE (… OpenGL ES 3.2)`; both WebGL 2.0 |
| Qt cookie layout matches Windows | Probe profile contains `Cookies` (SQLite), `Service Worker/`, `Session Storage/`, `Network Persistent State` |
| CI never ran functional tests | `.github/workflows/release.yml:77` → `make test-cov` → `pytest -m "not functional"` |

**Issue #1's central premise is stale.** It states "there is no newer PyQt6-WebEngine
version to upgrade to." Six Chromium majors have landed since. Phase 2 exists to
determine whether the WebView2 migration is still necessary before anyone starts it.

---

## Phase 1 — Split CI from functional; make functional tests fail

**Goal:** Functional tests report defects instead of hiding them.
**Prerequisites:** None.
**Blocks:** Every later phase's ability to report anything trustworthy.

### Background

`pytest.skip` appears ~20 times across `tests/functional/test_webview_*.py` for
conditions that are defects, not environment gaps. The worst case is
`test_webview_snapchat.py:95`: a renderer crash makes `run_js` return `None`, which
is caught and reported as `pytest.skip('JS execution unavailable — needs real
display with WebGL')`. **The blocker in issue #1 currently classifies itself as an
environment limitation and the suite stays green.**

These skips were added to protect CI, but CI was never at risk — the `functional`
marker already deselects every one of these tests.

### Tasks

1. `Makefile` — rename for intent, keep old names as aliases for one release:
   - `test-ci` → what `test-cov` does today (marker-excluded, coverage). Point
     `.github/workflows/release.yml:77` at it.
   - `test-functional` → add `GALEFLING_STRICT_FUNCTIONAL=1`.
   - `test-functional-linux` → borrow the live desktop session environment so
     QtWebEngine uses its hardware GPU (new; see Phase 2).
   - Keep `test-functional-xvfb`, `test-functional-cmd` unchanged.
2. `tests/functional/conftest.py` — add a `strict_functional` session fixture reading
   `GALEFLING_STRICT_FUNCTIONAL`. When set, a helper `fail_or_skip(reason)` raises
   `pytest.fail` instead of `pytest.skip`.
3. `tests/functional/conftest.py` — add an autouse fixture that registers a
   `renderProcessTerminated` handler and fails any test whose renderer died,
   regardless of what else the test asserted.
4. Convert every non-credential skip in `test_webview_{snapchat,onlyfans,fansly,fetlife,sessions}.py`
   to `fail_or_skip`. **Leave the credential fixtures alone** — absent credentials
   remain a legitimate skip.
5. `docs/testing/FUNCTIONAL_TESTING.md` — document strict mode and the new targets.

### Acceptance criteria

- `make test-ci` passes and collects zero functional tests.
- `make test-functional` with credentials present and a deliberately broken selector
  **fails**, and the failure names the selector.
- Absent credentials still skip, with the platform named.
- A renderer crash fails the test even if assertions would otherwise pass.
- `make lint` and `make test-cov` pass.

### Non-goals

Do not change test logic, selectors, or timings. Do not touch `webview_helpers.py`
(that is Phase 5). This phase only changes how outcomes are *reported*.

---

## Phase 2 — Re-test the Snapchat crash on Chromium 140

**Goal:** Determine whether the renderer crash still exists. This may retire the
largest item on the roadmap.
**Prerequisites:** None (Phase 1 improves reporting but is not required).
**Cost:** Hours. Read-only; commits nothing.

### Tasks

1. Run with a **live session** — the logged-out probe is not a valid test, because
   Snapchat bounces logged-out users away from the crashing bundle:
   ```bash
   DISPLAY=:0 GALEFLING_STRICT_FUNCTIONAL=1 \
     .venv/bin/python -m pytest tests/functional/test_webview_snapchat.py -m functional -v
   ```
2. Drive the full SSO flow via `login_snapchat` in `tests/functional/webview_helpers.py:479`
   so the `web.snapchat.com/#ticket=<token>` redirect executes — that is the path that
   crash-looped 82 times in the recorded session.
3. Instrument `renderProcessTerminated` with status, exit code, URL, and time since
   `loadFinished`. The historical signature is `STATUS_ACCESS_VIOLATION` /
   `-1073741819` at ~1200 ms (variance < 20 ms).
4. Repeat ≥10 cycles — the original was highly reproducible, so a single clean run
   proves little.
5. Record the result in this document and on issue #1.

### Acceptance criteria

- ≥10 authenticated load cycles of `www.snapchat.com/web/` on Chromium 140, with the
  crash either reproduced (timing + exit code captured) or absent across all cycles.
- Result posted to issue #1 with the Chromium version stated.

### Decision gate

- **No crash on Linux** → proceed to Phase 4, confirm on Windows, then re-scope
  issue #1. The WebView2 migration may reduce to a version pin.
- **Crash reproduces** → the migration stands. Capture a fresh renderer stack first;
  Chromium 140 may have moved the fault.

### Non-goals

Do not begin the WebView2 migration in this phase. Do not change platform code.

---

## Phase 3 — Provision the Windows 11 VM (no GPU)

**Goal:** A scriptable, snapshot-capable Windows test target that needs no reboot.
**Prerequisites:** Windows 11 ISO + key (Visual Studio Subscriptions); Appendix B
software installed. **No BIOS change required for this phase.**

### Why GPU-less first

Windows ships WARP, a full software D3D11/D3D12 rasterizer, and DXGI enumerates it
as "Microsoft Basic Render Driver." So `EnumAdapters1` succeeds and the real DXGI
code path executes — including `QDxgiVSyncService`, which is implicated in the
`debug_state.md` abort. Note that log's own line: `VSyncService: Failed to find
adapter (via EnumAdapters1)` was recorded **on real hardware with an RTX 2080 SUPER
present**, which points at a Qt lifecycle bug rather than a GPU-capability problem.

Three of the four known defect classes need no GPU at all:

| Defect | Needs GPU? | Rationale |
|---|---|---|
| Snapchat renderer crash | No | Issue #1 states `--disable-gpu` does not prevent it |
| OnlyFans checkbox clicks | No | Blink hit-tests the layout tree, not the compositor |
| Session persistence | No | SQLite cookie flush on shutdown |
| `VSyncService`/`QDxgi` abort | Unknown | DXGI runs under WARP — test rather than assume |

### Tasks

1. Create the VM per Appendix B. **UEFI + TPM 2.0 + Secure Boot are mandatory** for
   Windows 11 — OVMF firmware plus `swtpm`.
2. Install `virtio-win` guest drivers (storage, network, balloon).
3. In the guest: enable the OpenSSH Server optional feature, install Python 3.12,
   create `.venv`, `pip install -r requirements.txt -r requirements-dev.txt`.
4. Share the repo — virtiofs (needs WinFsp + the VirtioFS service from `virtio-win`).
   Fall back to a host Samba share if virtiofs proves unstable on the guest.
5. `Makefile` — add `test-functional-win-vm`, dispatching over SSH. Mirror the shape
   of the existing `test-functional-cmd` PowerShell dispatch; only the transport changes.
6. Take a baseline snapshot (`clean-loggedout`) immediately after setup, before any
   platform login.
7. `docs/testing/FUNCTIONAL_TESTING.md` — document the VM workflow.

### Acceptance criteria

- `make test-functional-win-vm` runs the suite in the guest from a Linux shell, with
  no interactive steps and no window on the host desktop.
- `virsh snapshot-revert` returns the guest to `clean-loggedout` in under 60 s.
- `tests/functional/test_media_processing.py` (no credentials needed) passes in the guest.

### Non-goals

No GPU passthrough. No BIOS changes. Do not attempt to run the app's GUI interactively.

---

## Phase 4 — Probe the DXGI abort; decide on a GPU

**Goal:** Determine whether the `VSyncService`/`QDxgiVSyncService` abort needs real
GPU hardware to reproduce.
**Prerequisites:** Phase 3.

### Tasks

1. Reproduce the `debug_state.md` sequence in the GPU-less guest: open a WebView
   login window from Settings, close it, open it again. The historical signature is
   `VSyncService: Failed to find adapter (via EnumAdapters1)` ×2, then
   `QDxgiVSyncService not destroyed in time`, then `Fatal Python error: Aborted` on
   `CrBrowserMain`.
2. Note that `debug_state.md` records a fix already applied (`dialog.deleteLater()`
   in `settings_dialog.py` and `setup_wizard.py`) that was **never built or
   installed**. Verify whether it is still present in the tree and whether it holds.

### Decision gate

- **Reproduces under WARP** → no GPU needed. Skip the hardware work entirely.
- **Does not reproduce** → add a GPU to the VM. Jas has prioritised **Intel iGPU
  passthrough** (Appendix A) over a second discrete card, because it needs no slot,
  no clearance, no power, and no purchase, and leaves the RTX untouched. Revisit the
  spare card in PCIE3 only if the iGPU path fails.

### Non-goals

Do not perform the BIOS change before this phase reports. It may prove unnecessary.

---

## Phase 5 — Test the shipped code, not a parallel implementation

**Goal:** Make the production WebView code reachable by tests.
**Prerequisites:** Phase 1.

### Background

`tests/functional/webview_helpers.py` (604 lines) builds its own `QWebEngineProfile`,
its own page, and its own login JS. `src/platforms/base_webview.py` (950 lines) does
all of it differently — a class-level `_profile_registry` for Cloudflare fingerprint
stability, `_LoggingWebEnginePage`, `renderProcessTerminated` handlers,
`SESSION_EXPIRED_SELECTORS`, and platform-specific timing constants.

The tests validate a reimplementation. Every defect under investigation lives in the
code the tests do not touch: the checkbox fix is
`src/platforms/onlyfans.py:_inject_2fa_checkbox_fix` (never invoked by any test), and
the abort is dialog/profile lifecycle in `src/gui/settings_dialog.py` (never invoked).
The tests create a fresh profile per test where the app deliberately shares one.

### Tasks

1. Replace `webview_helpers.create_webview` with the real
   `BaseWebViewPlatform.create_webview()`, patching `get_app_data_dir` to the test
   data directory (the pattern already used in `test_webview_sessions.py:57`).
2. Retire the duplicate login JS in favour of the platform classes' own logic.
   Keep `load_page`, `run_js`, `wait_ms` — those are genuine test utilities.
3. Confirm the shared-profile registry behaves under test (it is process-lifetime
   state; tests must not leak profiles between cases).

### Acceptance criteria

- No functional test constructs a `QWebEngineProfile` directly.
- A deliberate break in `base_webview.py` fails at least one functional test.
- `make lint` and `make test-cov` pass.

---

## Phase 6 — Real persistence and interaction tests

**Goal:** Cover the two defect classes that no current test can detect.
**Prerequisites:** Phase 5; Phase 3 for the Windows half.

### Session persistence

`test_webview_sessions.py` asserts only that a cookie file exists and is non-empty.
That cannot detect "sessions not persisted." The real test is **multi-process**:

1. Subprocess A logs in and exits **cleanly** (Chromium flushes cookies to SQLite
   asynchronously on shutdown — a prime suspect).
2. Assert cookies on disk.
3. Subprocess B starts cold, asserts `has_valid_session()`, then loads a real page
   and asserts it stays authenticated.

Run on both hosts. In the VM, `virsh snapshot-revert` to `clean-loggedout` first, so
every run starts from identical state — a capability neither dual-boot nor EC2 offers
cheaply.

### Interaction / clicks

Replace "assert `checked === true` after our JS ran" with a genuine
`QTest.mouseClick` at the element's viewport coordinates, then assert the resulting
Vue state. That distinguishes *"our workaround sets the property"* from *"a user's
click reaches the input"* — precisely the OnlyFans `.b-chckbox` failure mode, where
decorator `<span>` and icon elements absorb the click before it reaches the hidden
`<input>`.

### Acceptance criteria

- Persistence test fails if cookies are not durable across a process boundary.
- Click test fails if a real click is absorbed before reaching the input, even when
  `_inject_2fa_checkbox_fix` has run.
- Both pass on Linux and in the Windows VM.

---

## Phase 7 — Re-scope issue #1

Update issue #1 with the Chromium 140 finding and the Phase 2 result. Decide whether
the WebView2 migration proceeds, narrows, or closes. Do not begin the migration
before this phase.

Per repo convention, ask before adding references that create cross-links on
third-party trackers.

---

## Appendix A — Enabling the Intel iGPU in BIOS

**Do not perform this before Phase 4 reports.** It may be unnecessary.

**Goal:** Make UHD 630 available for passthrough while the RTX remains the boot and
host display adapter. Monitors stay on the RTX throughout; no cables move.

The i7-9700K has UHD 630 silicon, but no Intel display device appears in `lspci`,
which means the iGPU is disabled in firmware — the standard ASRock behaviour when a
discrete card is present.

### Steps (ASRock Z390 Phantom Gaming 4S/ac)

1. Reboot, press `F2` or `Del`, enter **Advanced Mode** (`F6` if it opens in EZ Mode).
2. **Advanced → Chipset Configuration**.
3. **Set this first:** confirm `Primary Graphics Adapter` = **`PCI Express`**.
   If it reads `Onboard`, change it before step 4.
4. Set `iGPU Multi-Monitor` = **`Enabled`**. This initialises the iGPU alongside the
   discrete card rather than instead of it.
5. Optional, helps IGD passthrough: set `Share Memory` / DVMT pre-allocated to
   **64 MB or higher** (relates to QEMU's `x-igd-gms`).
6. `F10` to save and exit.

### Safety

- **Never set `Primary Graphics Adapter` to `Onboard`.** That is the one setting that
  moves display output to the motherboard ports and blanks your monitors.
- Order matters: verify step 3 before step 4.
- **If the display goes dark:** move one monitor to the motherboard HDMI/DP to regain
  video and correct the setting, or clear CMOS (jumper or battery, board manual).
- Enabling the iGPU reserves a small amount of system RAM for stolen memory. Harmless
  at 62 GB.

### Verify after boot

```bash
lspci | grep -iE "vga|display"     # expect BOTH Intel and NVIDIA
lspci -nn -s 00:02.0                # note the [8086:XXXX] ID for vfio-pci binding
```
Confirm KDE still drives all three displays from the RTX, and that
`for d in /sys/kernel/iommu_groups/*/devices/*` places `00:02.0` in its own group.
That group assignment cannot be checked until the device exists.

### Then, for passthrough

Bind `vfio-pci` before `i915` claims the device — kernel cmdline
`vfio-pci.ids=8086:XXXX` plus `softdep i915 pre: vfio-pci`, then rebuild initramfs.
Assign in QEMU with the `x-igd-*` options (QEMU 10.2.1 supports
`x-igd-legacy-mode` (auto), `x-igd-opregion`, `x-igd-gms`, `x-igd-lpc`).

Headless IGD sometimes will not initialise its guest driver without an attached
display. Jas has a dummy HDMI plug on hand; the motherboard ports are free.

**Known risk:** IGD passthrough as a *secondary* adapter is less well-trodden than
discrete passthrough. Budget more time than a discrete card would need, and expect
black-screen / code-43 / host-hang-on-unbind as the common failure modes.

**Do not use GVT-g.** It is compiled in (`CONFIG_DRM_I915_GVT=y`,
`CONFIG_DRM_I915_GVT_KVMGT=m`) but deprecated, with poor Windows 11 guest support.
Its purpose is *sharing* an iGPU between host and guest; the host has no need for it
here, so full passthrough is simpler and higher fidelity.

---

## Appendix B — VM storage and software

### Storage location

**Use the ext4 root filesystem.** Confirmed correct — every other mount is NTFS:

```
/dev/sda2       ext4     916G  727G  143G  84%  /
/dev/nvme0n1p4  fuseblk  465G  372G   93G  81%  /mnt/freya-m2
/dev/nvme0n1p6  ntfs3    3.2T  2.8T  465G  86%  /mnt/loki-m2
/dev/sdc2       fuseblk  932G  847G   85G  91%  /mnt/mjolnir-ssd
/dev/sdb2       fuseblk  3.7T  2.5T  1.2T  69%  /mnt/thor-hdd
```

`fuseblk` mounts lack proper sparse-file support and `O_DIRECT`, which qcow2 wants;
`ntfs3` is a kernel driver but still not advisable for live VM images. Suggested
path: `/var/lib/libvirt/images/` (default) or `~/vms/`.

### Sizing

Create the qcow2 with a **120 GB virtual size**. It is sparse and grows on demand.

| Component | Actual disk |
|---|---|
| Windows 11 + updates | 35–45 GB |
| Python 3.12 + `.venv` (PyQt6-WebEngine is large) | ~2.5 GB |
| Chromium `webprofiles/` + caches | 2–5 GB |
| Snapshots (budget ~5–10 GB each) | 10–20 GB |
| **Realistic total** | **60–75 GB** |

143 GB is currently free, so this fits with roughly 70 GB to spare — but the root
filesystem is already 84% used. Keep to **three snapshots or fewer** and watch
`df -h /`.

RAM: **16 GB** of 62 GB. vCPUs: **4** of 8 (i7-9700K is 8 cores with no SMT — do not
allocate all 8).

### Host packages

```bash
sudo apt install qemu-system-x86 qemu-utils libvirt-daemon-system libvirt-clients \
                 virt-manager virtinst ovmf swtpm swtpm-tools virtiofsd \
                 dnsmasq-base virt-viewer
sudo usermod -aG libvirt,kvm "$USER"   # log out and back in
```

Already present: QEMU 10.2.1, `/dev/kvm`. Missing: libvirt, virt-manager, `virtinst`,
OVMF, swtpm.

`ovmf` and `swtpm` are **not optional** — Windows 11 requires UEFI, Secure Boot, and
TPM 2.0, and the install will refuse without them.

### Downloads

- **Windows 11 ISO + key** — Visual Studio Subscriptions (formerly MSDN).
- **virtio-win ISO** — Fedora's guest driver ISO; provides storage/network drivers
  and the VirtioFS service.

### Networking

libvirt's default NAT network is sufficient — the host reaches the guest directly on
`192.168.122.x`. No bridge required. SSH from host to guest over that address is the
transport for `make test-functional-win-vm`.

---

## Appendix C — Environment variables

`tests/functional/.env.example` is the authoritative skeleton. Copy it:

```bash
cp tests/functional/.env.example tests/functional/.env
```

`tests/functional/.env` is gitignored (`.gitignore:56`); `.env.example` is not, and
must never contain real values.

> **Never log, echo, print, or display any value read from `tests/functional/.env`.**
> This includes passwords, API keys, and TOTP secrets — in tool arguments, comments,
> assistant output, or debug output of any kind.

### Known drift in the existing `.env` (2026-08-10)

The live `.env` on `typhoon` has drifted from `.env.example`, which silently disables
tests:

- It defines `AWS_MEDIA_STAGING_ACCESS_KEY_ID`, `AWS_MEDIA_STAGING_SECRET_ACCESS_KEY`,
  `AWS_MEDIA_STAGING_REGION`, `AWS_MEDIA_STAGING_BUCKET`. **No code reads these names**
  — they appear only in `CHANGELOG.md` and `docs/plans/`.
- The `meta_aws_credentials` fixture (`tests/functional/conftest.py:224`) reads
  `META_AWS_ACCESS_KEY_ID`, `META_AWS_SECRET_ACCESS_KEY`, `META_AWS_REGION`,
  `META_AWS_BUCKET`. These are **absent**.

Consequence: Instagram media, Threads media, and Facebook Page media tests skip. Rename
the four keys in the local `.env`. It also defines `META_*_APP_ID` / `META_*_APP_SECRET`
/ `META_OAUTH_REDIRECT_URI`, which no test reads — harmless, and probably left from
OAuth relay work.

This is exactly the failure mode Phase 1 addresses: a silent skip is indistinguishable
from a pass.
