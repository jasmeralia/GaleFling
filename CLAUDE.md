# GaleFling - Claude Code Context

See [AGENTS.md](AGENTS.md) for mandatory rules, the release checklist, project structure, architecture, and conventions. **Always read AGENTS.md before starting any task.**

## Additional Documentation

| File | Contents |
|------|----------|
| [docs/ARCHITECTURE_OVERVIEW.md](docs/ARCHITECTURE_OVERVIEW.md) | Subsystem architecture and behavior |
| [docs/MEDIA_PROCESSING.md](docs/MEDIA_PROCESSING.md) | Image/video processing and conversion |
| [docs/BUILD_AND_RELEASE.md](docs/BUILD_AND_RELEASE.md) | Build tooling, packaging, release mechanics |
| [docs/platforms/PLATFORM_SPECS.md](docs/platforms/PLATFORM_SPECS.md) | Platform limits, account caps, posting constraints |
| [docs/platforms/](docs/platforms/) | Per-platform setup guides (credentials, limits, quirks) |
| [docs/testing/RELEASE_TESTING.md](docs/testing/RELEASE_TESTING.md) | Manual pre-release testing scenarios |
| [docs/testing/FUNCTIONAL_TESTING.md](docs/testing/FUNCTIONAL_TESTING.md) | Functional test setup, credentials, troubleshooting |

## Quick Reference

- **Platforms:** Bluesky, Instagram, OnlyFans, Fansly, Snapchat, Threads, Twitter/X
- **Target user:** Rin (non-technical content creator)
- **Developer/operator:** Jas

## Commands — Linux / WSL

- **Run lint:** `make lint PYTHON=.venv/bin/python`
- **Run tests:** `make test-cov PYTHON=.venv/bin/python`
- **Run functional tests:** `make test-functional-cmd` (via cmd.exe for native Windows GPU/display) or `python -m pytest tests/functional/ -v` (offscreen/WSL)

## Commands — Windows

- **Run lint:** `make lint PYTHON=.venv/Scripts/python.exe`
- **Run tests:** `make test-cov PYTHON=.venv/Scripts/python.exe`
- **Run functional tests:** `.venv/Scripts/python.exe -m pytest tests/functional/ -v`

> **Release checklist note:** `make test-cov` excludes functional tests via the `not functional` marker. Do not run functional tests as part of the release checklist on Windows (they require a display and live credentials).
- **Build exe:** `.venv/Scripts/python.exe -m PyInstaller build/build.spec --noconfirm`
- **Build installer:** `"C:/Program Files (x86)/NSIS/makensis.exe" build/installer.nsi`

## Paths

| Resource | Windows | WSL |
|----------|---------|-----|
| App data root | `C:\Users\storm\AppData\Roaming\GaleFling\` | `/mnt/c/Users/storm/AppData/Roaming/GaleFling/` |
| Logs | `C:\Users\storm\AppData\Roaming\GaleFling\logs\` | `/mnt/c/Users/storm/AppData/Roaming/GaleFling/logs/` |
| WebView profiles | `C:\Users\storm\AppData\Roaming\GaleFling\webprofiles\<account_id>\` | `/mnt/c/Users/storm/AppData/Roaming/GaleFling/webprofiles/<account_id>/` |
| Cookie DB | `C:\Users\storm\AppData\Roaming\GaleFling\webprofiles\<account_id>\Cookies` | `/mnt/c/Users/storm/AppData/Roaming/GaleFling/webprofiles/<account_id>/Cookies` |

## Debug Workflow

Use the debug-state workflow skill for iterative debugging.

Available triggers:
- `triage_logs`
- `triage_crash`
- `save_debug`
- `resume_debug`
- `clean_debug`

Rules:
- `debug_state.md` is the single source of truth across debug sessions.
- Do not rely on long-lived chat history for iterative debugging.
- After a failed run, use `triage_logs` unless the user reports a crash.
- After a crash, use `triage_crash`.
- After triage, use `save_debug` to persist the current issue state.
- After a session reset or `/clear`, use `resume_debug`.
- If `debug_state.md` becomes noisy or bloated, use `clean_debug`.
- If a trigger is used, invoke the corresponding skill behavior directly.
