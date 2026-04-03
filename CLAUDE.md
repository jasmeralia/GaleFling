# GaleFling - Claude Code Context

## Mandatory Agent Rules
1. After any code or docs change, run the full Release Checklist unless the user explicitly says not to.
2. Do not skip linting or tests.
3. If lint/tests fail, fix them before concluding.
4. Make the smallest effective change unless the user requests a broader refactor.
5. If project knowledge changes materially, update `AGENTS.md` and/or docs in `docs/`.
6. Any new menu option must add a log entry in the form: `User selected <Menu> > <Action>`.
7. **Tests and core code must stay in sync.** If a test (unit or functional) reveals that behavior differs from what the core code assumes, update *both* the test logic and the corresponding core code. Do not fix the test without fixing the core, or vice versa. For unit tests that mock dependencies, ensure the mock assumptions still match the real behavior of what is being mocked.
8. For iterative debugging, use the debug slash commands (`/triage_logs`, `/triage_crash`, `/save_debug`, `/resume_debug`, `/clean_debug`) instead of relying on long-lived chat history.
9. **Never log, echo, print, or display the values of any variables read from `tests/functional/.env`** — this includes passwords, API keys, TOTP secrets, and any other credentials. Do not include credential values in tool call arguments, code comments, assistant responses, or debug output of any kind.

Trigger phrase: **"follow the release checklist"**
- When the user says this, execute every step in the Release Checklist below.

## Release Checklist

> **Sync notice:** This checklist is duplicated from `AGENTS.md`. Any changes must be made in **both** files.

1. Run `make lint PYTHON=.venv/Scripts/python.exe` (Windows) or `make lint PYTHON=.venv/bin/python` (Linux/WSL) and confirm success.
2. Run `make test-cov PYTHON=.venv/Scripts/python.exe` (Windows) or `make test-cov PYTHON=.venv/bin/python` (Linux/WSL) and confirm success.
3. Before any **minor** version bump (`Y` in `X.Y.Z`), confirm with the user first.
4. Bump version in exactly two places:
   - `src/utils/constants.py` — `APP_VERSION = 'X.Y.Z'`
   - `README.md` — Current Version line and Release Build badge tag (`branch=vX.Y.Z`)
5. Add the new version entry at the top of `CHANGELOG.md`.
6. Commit with message: `Release vX.Y.Z`.
7. Tag: `vX.Y.Z`.
8. Push `master` and tags.
9. Summarize checklist results (lint, tests, version/tag state) in your final response.

---

See [AGENTS.md](AGENTS.md) for project structure, architecture, and conventions.

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
- **Run functional tests:** `make test-functional-cmd` — always use this in WSL; it dispatches via cmd.exe for native Windows GPU/display. Do NOT run functional tests directly with `python -m pytest` in WSL — WebView tests will be skipped.
- **Build exe + installer:** `make installer-wsl` (dispatches to Windows Python in `.venv-win` via PowerShell — run `make venv-win` once first)

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

## Security Rules

- **Never log, echo, print, or display the values of any variables read from `tests/functional/.env`** — this includes passwords, API keys, TOTP secrets, and any other credentials. Do not include credential values in tool call arguments, code comments, assistant responses, or debug output of any kind.

## Debug Workflow

Use the debug slash commands for iterative debugging across sessions.

Available commands:
- `/triage_logs` — analyze the newest app log and form hypotheses
- `/triage_crash` — analyze the newest crash log and form hypotheses
- `/save_debug` — persist current debug state to `debug_state.md`
- `/resume_debug` — resume from `debug_state.md` after a session reset or `/clear`
- `/clean_debug` — compact `debug_state.md` without losing live reasoning state

Rules:
- `debug_state.md` is the single source of truth across debug sessions.
- Do not rely on long-lived chat history for iterative debugging.
- After a failed run, use `/triage_logs` unless the user reports a crash.
- After a crash, use `/triage_crash`.
- After triage, use `/save_debug` to persist the current issue state.
- After a session reset or `/clear`, use `/resume_debug`.
- If `debug_state.md` becomes noisy or bloated, use `/clean_debug`.
