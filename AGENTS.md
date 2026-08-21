# GaleFling - Agent Context

## Project Overview
GaleFling is a Windows GUI application for posting to multiple social platforms from one composer.

- Target user: non-technical content creator (Rin)
- Developer/operator: Jas
- Product priorities: simplicity, reliability, clear guidance, strong troubleshooting support
- Status: active v1.x development (multi-account + API/WebView hybrid posting + media processing)

## Mandatory Agent Rules
1. After any code change, run the full Release Checklist (`make lint` + `make test-cov`) unless the user explicitly says not to. After a **docs-only change** — no files under `src/`, `tests/`, `tools/`, `scripts/`, `infrastructure/`, or `build/` touched; only documentation such as `README.md`, `CHANGELOG.md`, `AGENTS.md`/`CLAUDE.md`, or `docs/**` — run `make lint` only. Skip `make test-cov`: nothing under test can be affected by a docs-only change, so running the full suite is pure overhead.
2. Do not skip linting. Do not skip tests for a code change — the docs-only exception in rule 1 is the only case where `make test-cov` may be skipped.
3. If lint/tests fail, fix them before concluding.
4. Make the smallest effective change unless the user requests a broader refactor.
5. If project knowledge changes materially, update `AGENTS.md` and/or docs in `docs/`.
6. Any new menu option must add a log entry in the form: `User selected <Menu> > <Action>`.
7. **Tests and core code must stay in sync.** If a test (unit or functional) reveals that behavior differs from what the core code assumes, update *both* the test logic and the corresponding core code. Do not fix the test without fixing the core, or vice versa. For unit tests that mock dependencies, ensure the mock assumptions still match the real behavior of what is being mocked.
8. **Never log, echo, print, or display the values of any variables read from `tests/functional/.env`** — this includes passwords, API keys, TOTP secrets, and any other credentials. Do not include credential values in tool call arguments, code comments, assistant responses, or debug output of any kind.
9. **Ask for cleanup of a live test artifact only after inspection is finished.** A mutating functional test creates real platform state — a post, an upload — that only the operator can remove. Report the tag as soon as it prints so the operator knows it exists, then **state your own status accurately** — the two halves of this rule are not the same claim. Say it must stay up **only while you actually need it**: mid-investigation, or awaiting an answer to a clarification whose resolution could depend on the artifact. Once every assertion about it is verified and no follow-up question could need its DOM, say plainly that it is **safe to delete**. Never say "it should stay up for now" as a default courtesy when you have no further use for it — that misreports your own state and keeps live artifacts on a real account longer than anything requires. "I don't need it deleted" and "it should stay up" are opposite claims; do not write both. The tests' own `CLEANUP PENDING` line (WebView) and `artifact left up` line (API, under `--leave-mutating-artifacts`) fire unconditionally at creation and are **not** the request — do not relay either as one. Deleting early has already cost a re-run: the artifact was the only evidence that could confirm a rewritten assertion, and a probe against an already-deleted post returns "not found", which reads identically to a real measurement. API mutating tests delete by default; when a run needs to be inspectable, use `make test-functional-mutating-leave-up` and clean up from the printed tags or `tests/functional/.artifacts.jsonl` afterwards. See [docs/testing/FUNCTIONAL_TESTING.md](docs/testing/FUNCTIONAL_TESTING.md#leaving-mutating-artifacts-up-for-inspection).

10. **Durable feedback belongs in this file, not only in agent-specific memory.** When the user gives guidance that is not specific to one agent or tool — a working convention, a hazard, a sequencing rule, a correction worth keeping — record it in `AGENTS.md` (or the relevant page under `docs/`) so it reaches every agent, every session, and every human contributor. An agent's own private memory store is an acceptable *additional* safeguard, never the only one: it is invisible to other agents, to other contributors, and to code review, so guidance kept solely there is guidance the project does not actually have. When both exist, `AGENTS.md` is canonical and the memory should point at it rather than restate it, so the two cannot drift apart.

11. **Shut the Windows test VM down when you are done with it, and check before committing.** `galefling-win11` is a 16 GiB, 4-vCPU guest; anything that starts it (`make test-functional-win-vm`, `tools/spikes/run-in-win-vm.sh`, `start-vm.sh`) leaves it running afterwards, because none of those scripts stop it. Run `tools/windows-vm/stop-vm.sh` once testing is finished. Before committing, run `sudo virsh --connect qemu:///system list` and stop the VM if it is still up — a guest left running for days holds host RAM, and its disk keeps drifting from the `clean-loggedout` baseline that snapshot reversion assumes. Leave it running only while you are actively mid-run, and say so.

12. **Never stage with `git add -A` or `git add .`.** Stage the paths you actually changed, by name. A blanket add sweeps up whatever else is sitting in the working tree — scratch files, sample media, a credential export, a log dump — and commits it under a message that does not mention it. This has already happened: a `test.txt` the operator had created to measure FetLife's caption limit was silently committed as part of an unrelated change to the WebView activation primitive, and was only noticed because the operator offered to delete it. Run `git status` first, stage explicitly, and check `git show --stat` before pushing. The hazard is worst for exactly the files that must never be committed, since those are untracked by design.

13. **Platform names, credits, and trademark disclaimers must stay accurate.** Use canonical platform-name casing everywhere humans read the name (GUI strings, logs, user-facing errors, tests, comments, and docs): Fansly, OnlyFans, FetLife, Bluesky, Snapchat, Instagram, Threads, and Twitter (never "X"). Do not rename filenames, identifiers, account IDs, platform keys, URLs, selectors, or env var names. `PlatformSpecs.platform_name` is a display value and must use canonical casing. Keep the **Help > About** dependency list aligned with significant `requirements.txt` entries (sorted alphabetically, case-insensitive, with links to official project sites). Keep AI-tooling credits current. Maintain the trademark disclaimer in both `README.md` and the About dialog.

14. **Content sent to a live platform must be neutral — never name the product or address a reader.** Anything a functional test types into a real composer or publishes to a real account is public content on Morgan's own accounts. It must carry nothing but the run's opaque tag: no product name, no "test", no "safe to delete" or similar instruction to whoever sees it. Build post text with `mutating_post_text()` / `mutating_post_tag()` in `tests/functional/conftest.py`, never an ad-hoc f-string. This applies to non-publishing probes too — text entered into a live composer can be autosaved as a draft, and a test that does not submit today may submit after a later change. Captions like `f'GaleFling PNG test {tag} — safe to delete'` shipped to live accounts before commit `45c56ca` neutralised them, and six such posts were still discoverable on the Threads account afterwards. The tag alone is enough to find an artifact for cleanup; everything beyond it is disclosure with no benefit, and on an adult platform that disclosure is a real cost.


Trigger phrase: **"follow the release checklist"**
- When the user says this, execute every step in the checklist below.

## Version Management

**Version is derived from git tags — it is not stored in source.**

`src/utils/_version.py` is generated by `scripts/write_version.py` and is gitignored. It is the only place `APP_VERSION` originates from. Do not create version strings anywhere else in the codebase.

| What | How it gets the version |
|------|------------------------|
| Running app | Imports `APP_VERSION` from `constants.py` → `_version.py` |
| `build/version_info.txt` | Generated by `build/build.spec` from `_version.py` at PyInstaller time |
| `build/version.nsh` | Generated by `build/build.spec` from `_version.py` at PyInstaller time |
| `build/installer.nsi` | Reads `${VERSION}` / `${VERSION_TUPLE}` from `version.nsh` |
| GitHub release tag | Created by `.github/workflows/release.yml` via `release_info.py` |

On `master` pushes, the release workflow calls `release_info.py` to compute the next patch tag from git history. If HEAD is not already tagged, it creates the tag via the GitHub API and triggers the build. No files are committed back to master.

## Release Checklist

> **Sync notice:** This checklist is duplicated in `CLAUDE.md`. Any changes must be made in **both** files.
1. Run `make lint` and confirm success.
2. Run `make test-cov` and confirm success.
3. Before any **minor** version bump (`Y` in `X.Y.Z`), confirm with the user first.
4. Add the new version entry at the top of `CHANGELOG.md` (optional for patch releases — `[Unreleased]` section is used if no versioned entry exists).
5. Commit with message: `Release vX.Y.Z` (or any descriptive message for patch releases driven by Dependabot).
6. Push `master`; GitHub Actions computes the next tag from git history, creates it via API, and builds.
7. Summarize checklist results (lint, tests, version/tag state) in your final response.

## Project Structure
```
galefling/
├── src/
│   ├── main.py
│   ├── gui/                  # MainWindow, setup wizard, composer, previews, dialogs
│   ├── platforms/            # API + WebView platform adapters
│   ├── core/                 # media processing, logging, config, auth, updates
│   └── utils/                # constants, helpers, theme
├── tests/
├── resources/
├── build/
├── infrastructure/
├── tools/windows-vm/       # Portable libvirt Windows test-VM harness
├── docs/
└── AGENTS.md
```

## Key Architecture Concepts
- Multi-account model: account objects (`platform_id`, `account_id`, `profile_name`, `enabled`) drive platform creation and selector state.
- Two-tier posting:
  - Tier 1: API platforms (background post worker)
  - Tier 2: WebView platforms (user confirms in `WebViewPanel`)
- Per-account WebView isolation: each WebView account uses a dedicated persistent profile/cookie store.
- Media prep is platform-aware and cached per platform-group before posting.
- Drafts auto-save and restore; logs/screenshots support remote debugging.
- WebView SPA platforms may legitimately report posted results without a captured permalink.

## Critical Conventions
- **Posts are never paywalled.** The same post is cross-published to platforms with no
  paywall concept (Twitter, Instagram, Bluesky), so gating it on one destination breaks
  parity with every other. On Fansly, media uploads must **uncheck Require Subscription**
  (checked by default) and **check Require Follow**; Advanced Permissions and Require
  Purchase stay unchecked. On OnlyFans, posts must not be PPV. Set these by exact field
  name, never by keyword-matching labels — permission blocks sit next to controls that
  change monetization or the account avatar.
- Use account-labeled platform names in UI/results (`Platform (profile_name)` where available).
- Platform failures should not block posting to other platforms.
- Keep behavior non-destructive and understandable for non-technical users.
- Keep lint/tests green as the default quality gate.
- Use `make deps` to set up the `.venv` and install dependencies; all `make` targets use the venv Python automatically.

## Development Platforms

- **Linux (Kubuntu) is the primary development platform**, not a secondary target. Features
  are built and exercised natively via `make run`, and functional tests are normally
  written and run under Linux first. Do not treat Linux support as something to be added
  or verified after the fact.
- **Windows is the release target** — it is Rin's platform — and is therefore the side more
  likely to drift, since it is not where daily development happens. The control for that is
  the release process rather than extra CI: builds ship as **pre-releases**, and promotion
  to latest-stable follows the operator's own Windows verification, now via the
  `galefling-win11` VM.
- **Agents never promote releases.** Do not mark a release as latest, flip a pre-release to
  stable, or otherwise change release visibility — no `gh release edit --latest`, no
  equivalent API call. That decision rests on Windows verification the operator performs
  and is theirs alone, in the same way that CI creates version tags and agents do not push
  them by hand.
- **The WSL functional-testing path is effectively dead.** It remains supported and should
  not be removed, but it is unlikely to be exercised — active development happens under
  Kubuntu rather than by booting into Windows. Do not assume WSL-only instructions have
  been validated recently, and do not treat WSL as a validation route for new work.

## Windows WebView Test VM

- Reusable VM scripts and answer-file templates live in `tools/windows-vm/`.
- Copy `tools/windows-vm/vm.env.example` to the gitignored `vm.env` for local paths
  and resource settings. `GALEFLING_VM_CONFIG` may point to a config elsewhere.
- Keep the actual SSH keypair in `~/.ssh`; store only `SSH_PRIVATE_KEY` and
  `SSH_PUBLIC_KEY` paths in `vm.env`.
- Never commit `vm.env`, Windows license keys, VM passwords, ISOs, installers,
  generated answer files, generated unattended ISOs, or VM disk images.
- Use `create-vm.sh`/`finish-vm.sh` for provisioning and `start-vm.sh`, `stop-vm.sh`,
  and `snapshot-vm.sh` for routine lifecycle operations. `stop-vm.sh` is graceful
  unless `--force` is explicitly supplied; snapshot reversion discards newer guest
  changes.
- Run functional tests in the VM with `make test-functional-win-vm`
  (`PYTEST_ARGS="..."` for a subset, `-clean` variant to revert first). Tests execute
  from a `C:\GaleFling` copy that is re-synced with `robocopy /MIR` each run, so it is
  never stale. Credentials are read from the share via `GALEFLING_FUNCTIONAL_ENV` and
  must never be written to the guest disk or captured in a snapshot.
- The copy exists because a `logs` symlink to an absolute Linux path once broke pytest's
  rootdir walk over VirtIO-FS. That symlink is gone and the share no longer fails that
  way, but a share-rooted run was seen collecting the whole suite instead of the
  requested subset, so the copy is retained. `GUEST_REPO='Z:\'` with `--no-sync` runs
  from the share for anyone revisiting it; without `--no-sync` the script refuses, since
  mirroring the share onto itself would aim `robocopy /MIR` at its own source.
- Do not put an absolute path in `GALEFLING_DATA_DIR`: both the Linux host and the
  Windows guest read the same `.env` over the share, so a path valid on one is wrong on
  the other. Leave it unset and each side resolves its own application data directory.
- The host repository is shared to Windows as `Z:` through VirtIO-FS. WinFsp is a
  guest dependency for that mount, not an application dependency.
- The configured baseline snapshot defaults to `clean-loggedout` and must contain
  no authenticated platform sessions.
- See `tools/windows-vm/README.md` and `docs/testing/WEBVIEW_TEST_PLAN.md` for the
  complete setup and testing workflow.

## Additional Documentation
- `docs/ARCHITECTURE_OVERVIEW.md` — deeper architecture and subsystem behavior
- `docs/EMAIL_NOTIFICATIONS.md` — SMTP credential import, notification email setup, testing
- `docs/MEDIA_PROCESSING.md` — image/video processing and conversion behavior
- `docs/BUILD_AND_RELEASE.md` — build, tooling, packaging, and release mechanics
- `docs/platforms/PLATFORM_SPECS.md` — platform limits, account caps, and posting constraints
- `docs/platforms/<PLATFORM>.md` — per-platform credential setup, limits, and quirks
- `docs/testing/RELEASE_TESTING.md` — recommended manual pre-release testing scenarios
- `docs/testing/FUNCTIONAL_TESTING.md` — functional test setup, credentials, and troubleshooting
- `tools/windows-vm/README.md` — Windows 11 libvirt test-VM setup and lifecycle
