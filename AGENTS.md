# GaleFling - Agent Context

## Project Overview
GaleFling is a Windows GUI application for posting to multiple social platforms from one composer.

- Target user: non-technical content creator (Rin)
- Developer/operator: Jas
- Product priorities: simplicity, reliability, clear guidance, strong troubleshooting support
- Status: active v1.x development (multi-account + API/WebView hybrid posting + media processing)

## Mandatory Agent Rules
1. After any code or docs change, run the full Release Checklist unless the user explicitly says not to.
2. Do not skip linting or tests.
3. If lint/tests fail, fix them before concluding.
4. Make the smallest effective change unless the user requests a broader refactor.
5. Before bumping a **minor** version (`Y` changes in `X.Y.Z`), ask the user to confirm.
6. If project knowledge changes materially, update `AGENTS.md` and/or docs in `docs/`.
7. Any new menu option must add a log entry in the form: `User selected <Menu> > <Action>`.

Trigger phrase: **"follow the release checklist"**
- When the user says this, execute every step in the checklist below.

## Release Checklist
1. Run `make lint PYTHON=.venv/bin/python` and confirm success.
2. Run `make test-cov PYTHON=.venv/bin/python` and confirm success.
3. Bump version in:
   - `src/utils/constants.py`
   - `resources/default_config.json`
   - `build/installer.nsi`
   - `build/version_info.txt`
   - `README.md`
4. Before any **minor** version bump, confirm with the user first.
5. Add the new version entry at the top of `CHANGELOG.md`.
6. Update the `README.md` **Release Build** badge tag query (`branch=vX.Y.Z`).
7. Commit with message: `Release vX.Y.Z`.
8. Tag: `vX.Y.Z`.
9. Push `master` and tags.
10. Summarize checklist results (lint, tests, version/tag state) in your final response.

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
- Use account-labeled platform names in UI/results (`Platform (profile_name)` where available).
- Platform failures should not block posting to other platforms.
- Keep behavior non-destructive and understandable for non-technical users.
- Keep lint/tests green as the default quality gate.
- Prefer `.venv/bin/python` for project automation commands.

## Additional Documentation
- `docs/architecture-overview.md` — deeper architecture and subsystem behavior
- `docs/platform-specs.md` — platform limits, account caps, and posting constraints
- `docs/media-processing.md` — image/video processing and conversion behavior
- `docs/build-and-release.md` — build, tooling, packaging, and release mechanics
- `docs/threads-integration.md` — Threads selector/cookie verification workflow
- `docs/RELEASE-TESTING.md` — recommended manual pre-release testing scenarios
