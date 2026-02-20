# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.115] - 2026-02-20
- Theme the no-updates dialog title bar.
- Update the update dialog button to “Download and Install”.
- Defer setup wizard opening to reduce access violations and log more markers.
- Add tests for new update dialog button text and no-updates theming.

## [0.2.114] - 2026-02-20
- Defer setup wizard opening, add more fatal markers, and expand wizard logging.
- Log user actions for posting, test connections, and image attachments.
- Add tests for action logging and adjust setup wizard logging test.

## [0.2.112] - 2026-02-20
- Center the About icon and improve log clearing for fatal crash logs.
- Add file-handle compatibility to fatal crash logging.
- Update release workflow badge formatting.

## [0.2.111] - 2026-02-20
- Fix bundled resource lookup for frozen builds (icon.png now resolves correctly).
- Skip title bar theming on the setup wizard to avoid Win11 access violations.
- Include fatal/crash logs in log uploads and clear them via Help → Clear Logs.
- Prefix fatal error logs with timestamps.

## [0.2.108] - 2026-02-20
- Wire APP_ORG into app metadata and capture unhandled exceptions in logs.
- Ensure update/download dialogs apply theme to title bar.
- Add test coverage for themed update download dialogs.
- Update build badges to shields.io.

## [0.2.107] - 2026-02-20
- Update build/CI badges to track the correct workflow status.

## [0.2.106] - 2026-02-20
- Ensure About dialog icon renders reliably.

## [0.2.105] - 2026-02-20
- Apply theme settings to all dialogs, including update available.
- Add coverage for dialog theming via update check tests.

## [0.2.104] - 2026-02-20
- Expand Bluesky app password guidance (DM checkbox warning and safety notes).
- Link username instructions to Bluesky settings page.

## [0.2.103] - 2026-02-20
- Show Bluesky secondary account as “Bluesky (username)” in the composer.
- Improve setup wizard test buttons for dark theme readability.
- Make Test Connections report usernames with explicit success/failure text.
- Add tests for connection messaging and Bluesky label behavior.

## [0.2.102] - 2026-02-20
- Add About dialog icon and linkable credits.
- Add a second Bluesky account with logout actions and duplicate-check validation.
- Share Bluesky image previews between accounts.
- Improve setup wizard guidance for Bluesky app passwords.
- Expand test coverage for multi-account Bluesky and new UI behaviors.

## [0.2.101] - 2026-02-20
- Show update release notes inline with Markdown rendering and external links.
- Remove the update dialog “details” button.
- Add extensive unit tests across helpers, theming, logging, previews, settings, and platforms.
- Raise test coverage to ~76%.

## [0.2.100] - 2026-02-20
- Cache processed images across draft saves and resubmits.
- Track enabled platforms in drafts and restore cached previews.
- Add a Preview Images button that reuses cached variants.
- Skip regenerating previews when cached images exist, and clean up after success.
- Show a status message when drafts auto-save.
- Add tests for preview caching, draft persistence, and preview reopen.

## [0.2.99] - 2026-02-20
- Cache processed images across draft saves and resubmits.
- Skip regenerating previews when cached images exist, and clean up after success.
- Show a status message when drafts auto-save.
- Add tests for preview caching and draft persistence.

## [0.2.98] - 2026-02-20
- Require usernames for enabling platforms and handle missing username disablement.
- Reopen image previews when enabling a new platform with an attached image.
- Add tests for preview generation and username requirements.

## [0.2.97] - 2026-02-20
- Require usernames for platform enablement alongside API credentials.
- Add tests to ensure missing usernames disable platforms.

## [0.2.96] - 2026-02-20
- Display optional platform usernames in the selector and account settings.
- Add regression tests for theme label styles and username formatting.

## [0.2.95] - 2026-02-20
- Use theme-aware label colors for the main composer and platform selector.

## [0.2.94] - 2026-02-20
- Upload Codecov test results via the Codecov test-results action.
- Move Codecov uploads to v5 for CI and release workflows.

## [0.2.93] - 2026-02-20
- Add a separate badge for release build status alongside CI.

## [0.2.92] - 2026-02-20
- Add a CI workflow that uploads coverage on branch pushes/PRs.
- Point the build badge to the CI workflow.

## [0.2.91] - 2026-02-20
- Ignore coverage/test artifacts and remove generated files from the repo.

## [0.2.90] - 2026-02-20
- Generate JUnit XML alongside coverage in `make test-cov`.
- Enable verbose Codecov upload logging to aid troubleshooting.

## [0.2.89] - 2026-02-20
- Add dev dependency stubs and fix mypy errors in core, GUI, and platform code.
- Run `make lint` using the project virtualenv.

## [0.2.88] - 2026-02-20
- Add lint/test steps to the release checklist.
- Run `make lint` as part of the release process.

## [0.2.87] - 2026-02-20
- Run mypy as part of the lint target.

## [0.2.86] - 2026-02-20
- Match the Test Connections button style to Post Now.
- Keep test/attach actions disabled when no platforms are enabled.

## [0.2.85] - 2026-02-20
- Prevent update dialog tests from hanging in CI.

## [0.2.84] - 2026-02-20
- Force Qt tests to run offscreen in CI to avoid headless crashes.

## [0.2.83] - 2026-02-20
- Allow manually dispatching the release workflow against a specific tag.
- Upload Codecov coverage only when a token is configured without invalid workflow syntax.

## [0.2.82] - 2026-02-20
- Bump version for release workflow rerun.

## [0.2.75] - 2026-02-19
- Use the latest release (including prereleases) as the previous release for notes.
- Force the setup wizard header and button panels to a mid-grey background in dark mode.

## [0.2.76] - 2026-02-19
- Disable platform options and counters when credentials are missing or unchecked.
- Skip image processing for disabled platforms and disable posting when nothing is enabled.
- Update About dialog copyright line to include Winds of Storm.

## [0.2.78] - 2026-02-19
- Add additional GUI and updater tests for platform gating, updates, and dialogs.
- Add coverage reporting in CI and badges in the README.
- Move developer documentation to docs/CONTRIBUTING.md and simplify README for end users.

## [0.2.81] - 2026-02-19
- Show release notes in update prompts for more context.

## [0.2.80] - 2026-02-19
- Add roadmap documentation and link docs from the README.

## [0.2.79] - 2026-02-19
- Skip Codecov upload when no token is configured to avoid CI failures.

## [0.2.77] - 2026-02-19
- Disable attach/post buttons when no platforms are checked.
- Add GUI tests for platform enable/disable state and counters.

## [0.2.74] - 2026-02-19
- Force wizard header/button widgets to adopt theme colors via object names.

## [0.2.73] - 2026-02-19
- Label update prompts as beta or stable releases.

## [0.2.72] - 2026-02-19
- Force theme colors on the setup wizard header and button row after widgets render.

## [0.2.71] - 2026-02-19
- Theme the setup wizard header and button panels for dark mode.

## [0.2.70] - 2026-02-19
- Rename the prerelease update toggle to "Enable beta updates".

## [0.2.69] - 2026-02-19
- Add a prerelease update toggle and optionally include prereleases in update checks.
- Publish GitHub releases as prereleases instead of drafts.

## [0.2.68] - 2026-02-19
- Launch the app from the installer without elevation.
- Abort with a fatal error if the app is started as administrator.

## [0.2.67] - 2026-02-19
- Theme the setup wizard button row and title bar to match the active palette.
- Stop auto-launching the app from the installer finish page to avoid elevated runs.

## [0.2.66] - 2026-02-19
- Force the setup wizard pages to use the active theme background.

## [0.2.65] - 2026-02-19
- Regenerate the Windows ICO from the high-resolution PNG.

## [0.2.64] - 2026-02-19
- Launch the installer with a direct UAC prompt using ShellExecute.

## [0.2.63] - 2026-02-19
- Apply the active theme consistently in the setup wizard.
- Add a Settings menu action to rerun the setup wizard.

## [0.2.62] - 2026-02-19
- Apply the active theme to the setup wizard.
- Trigger UAC elevation when launching the installer from the auto-updater.

## [0.2.61] - 2026-02-19
- Upload installer assets from any path and log what the release job finds.

## [0.2.60] - 2026-02-17
- Remove portable zip files before attaching release assets.

## [0.2.59] - 2026-02-17
- Ensure release job downloads artifacts without an extra subfolder so installer uploads succeed.

## [0.2.58] - 2026-02-17
- Fix NSIS output path so the installer writes into the build directory.

## [0.2.57] - 2026-02-17
- Write the NSIS installer output into the build directory so releases pick it up.

## [0.2.56] - 2026-02-17
- Keep the portable zip build but exclude it from release artifacts.

## [0.2.55] - 2026-02-17
- Launch the installer via a helper script that waits for the app process to exit.

## [0.2.54] - 2026-02-17
- Retry process termination before installing, and fail with a clear message if the app stays running.

## [0.2.53] - 2026-02-17
- Launch the updater installer as a detached process and quit the app immediately.
- Force-kill the running app before installer file copy.

## [0.2.52] - 2026-02-17
- Add a View menu action to revert to the system theme preference.

## [0.2.51] - 2026-02-17
- Add View menu actions to toggle Light/Dark mode and persist the choice in settings.

## [0.2.50] - 2026-02-17
- Apply a dark Windows title bar when the OS prefers dark mode.

## [0.2.49] - 2026-02-17
- Rebrand GalePost to GaleFling across the app, build outputs, and docs while keeping the log endpoint on `galepost.jasmer.tools`.

## [0.2.48] - 2026-02-14
- Verify auto-update installer size against the release asset before launching.

## [0.2.47] - 2026-02-14
- Validate auto-update installer downloads before launching them.

## [0.2.46] - 2026-02-14
- Include hostname/username/os version in log upload emails and use hostname in subject.

## [0.2.45] - 2026-02-14
- Clear and reset the active log file when using Help > Clear Logs.

## [0.2.44] - 2026-02-14
- Add a Help menu action to clear saved logs and screenshots.

## [0.2.43] - 2026-02-14
- Promote image preview file path logs to info level for better visibility.

## [0.2.42] - 2026-02-14
- Expand Pillow debug logging with input/output paths and exceptions.
- Clear the composer after successful posts.

## [0.2.41] - 2026-02-14
- Fix SES raw email submission for log attachments.

## [0.2.40] - 2026-02-14
- Keep the image preview OK button disabled until all previews finish successfully.

## [0.2.39] - 2026-02-14
- Expand the release checklist to cover all version references.
- Document the updated SES sender address.

## [0.2.38] - 2026-02-14
- Bundle the Python runtime DLL explicitly in Windows builds to prevent missing DLL errors.

## [0.2.37] - 2026-02-14
- Send log uploads as SES email attachments instead of storing in S3.
- Drop S3 dependencies from the log upload infrastructure.

## [0.2.36] - 2026-02-14
- Simplify log upload diagnostics to only include OS platform details.
- Improve Windows 11 detection for OS platform reporting.
- Remove redundant OS fields from log upload payloads and emails.

## [0.2.35] - 2026-02-14
- Update deploy helper to reference SES sender morgan@windsofstorm.net.
- Include region/profile in printed AWS CLI follow-up commands.

## [0.2.34] - 2026-02-14

### Changed
- SES sender default updated to morgan@windsofstorm.net

## [0.2.33] - 2026-02-14

### Fixed
- Installer now closes any running GaleFling instance before copying files
- Update download now exits the app after saving drafts

## [0.2.32] - 2026-02-14

### Changed
- Linting now runs shellcheck on all scripts

## [0.2.31] - 2026-02-14

### Changed
- Added shellcheck to linting and fixed deploy script warnings

## [0.2.30] - 2026-02-14

### Changed
- Suppressed a benign shellcheck warning in the deploy script

## [0.2.29] - 2026-02-14

### Changed
- Deploy script now derives AWS region from the ACM certificate ARN
- Release checklist notes that new scripts should be included in linting/testing

## [0.2.28] - 2026-02-14

### Changed
- CloudFormation no longer assumes Route53; deploy script supports AWS profiles and waits for stack completion
- Stack outputs now include the CNAME target for manual DNS setup

## [0.2.27] - 2026-02-14

### Changed
- Log upload error details now include OS info, hostname, and username by default
- Log uploader payload includes OS details for the backend

### Added
- Lambda tests cover OS metadata fields

## [0.2.26] - 2026-02-14

### Changed
- Log upload error details now include hostname and username (user notes removed)

## [0.2.25] - 2026-02-14

### Changed
- Log upload failure details now include timestamps, exception info, and user notes

## [0.2.24] - 2026-02-14

### Added
- Tested release notes generation script used by GitHub Actions

### Fixed
- Release notes script now handles missing previous tags without including extra sections

## [0.2.23] - 2026-02-14

### Added
- Release notes extraction moved into a tested script

### Fixed
- Draft release notes no longer error in CI when parsing changelog

## [0.2.22] - 2026-02-14

### Added
- Verbose log upload failure details with copy-to-clipboard option

### Changed
- Draft release notes now reliably include changelog sections between the current and last published release

## [0.2.21] - 2026-02-14

### Changed
- Draft release notes now include only the changelog sections between the current tag and last published release
- Removed redundant commits list from release notes (full changelog link remains)

## [0.2.20] - 2026-02-14

### Changed
- Release assets now omit the standalone `GaleFling.exe` (installer + portable zip only)

## [0.2.19] - 2026-02-14

### Changed
- Draft release notes now include all changelog sections since the last published release

## [0.2.18] - 2026-02-14

### Fixed
- Logs now write to the user profile instead of Program Files

### Added
- Installer now shows MIT license, optional desktop shortcut, and launch-on-finish

## [0.2.17] - 2026-02-14

### Fixed
- Installer now requires admin privileges and installs under Program Files correctly

## [0.2.16] - 2026-02-14

### Fixed
- Release workflow now uploads and attaches the NSIS installer from the build output path

## [0.2.15] - 2026-02-14

### Fixed
- Draft releases now attach installer and portable zip assets
- Release notes now compare against the last published release (not the last tag)

## [0.2.14] - 2026-02-14

### Added
- Required user description when sending logs; lambda stores it and includes it in email
- Tests for the log upload lambda

### Changed
- Image preview dialog now includes Cancel and only enables OK when all resizes finish

### Fixed
- Release assets now attach installer and portable zip correctly

## [0.2.13] - 2026-02-14

### Changed
- Image preview OK button now waits for all selected platform resizes to finish

## [0.2.12] - 2026-02-14

### Fixed
- GHA NSIS build now resolves the Chocolatey install path before running `makensis`

### Changed
- Phase 2 notes now include a macOS build pipeline goal

## [0.2.11] - 2026-02-14

### Added
- Commit helper script to avoid shell interpolation in commit messages

### Changed
- Release checklist now references the commit helper script

## [0.2.10] - 2026-02-14

### Fixed
- Draft release titles now use a single `v` prefix

### Added
- GitHub Actions builds and uploads the NSIS installer executable

## [0.2.9] - 2026-02-14

### Fixed
- Corrected Bluesky URL regex grouping so tests pass

### Changed
- Release checklist now requires running tests after lint and before commit, and uses verbose commit messages

## [0.2.8] - 2026-02-14

### Added
- Unit test coverage for Bluesky URL facets with full paths

### Fixed
- Bluesky link facet detection now includes full URL paths

### Changed
- Renamed CLAUDE.md to AGENTS.md and updated release workflow notes

## [0.2.7] - 2026-02-14

### Fixed
- Bluesky link facet detection now includes full URL paths

## [0.2.6] - 2026-02-14

### Fixed
- Bluesky post timestamps no longer rely on removed client internals
- Apply Windows dark mode palette when the system prefers dark

## [0.2.5] - 2026-02-14

### Added
- Image processing progress indicators in the preview dialog and posting flow
- Debug logging around image processing stages

### Changed
- Use system UI style to respect Windows light/dark mode
- Adjusted hint and placeholder label colors to follow system palette

## [0.2.4] - 2026-02-14

### Fixed
- Clean up temporary processed images after posting to avoid unbounded storage growth

## [0.2.3] - 2026-02-14

### Fixed
- Moved image preview processing off the UI thread to prevent hangs when attaching large images

## [0.2.2] - 2026-02-14

### Fixed
- Fixed `.gitignore` excluding `build/` directory and `*.spec` files from git, causing CI build failure

## [0.2.1] - 2026-02-14

### Changed
- Applied ruff formatting across entire codebase
- Updated git remote to new repository URL (`jasmeralia/GaleFling`)

## [0.2.0] - 2026-02-14

### Changed
- Rebranded application from "Social Media Poster" to "GaleFling"
- Repository renamed to `jasmeralia/galefling`
- Log upload endpoint moved to `galepost.jasmer.tools`
- All build artifacts now use GaleFling naming (exe, installer, portable zip)
- Windows AppData directory changed to `GaleFling`
- Updated GitHub Actions workflow for GaleFling build artifacts

### Added
- Help > About dialog with copyright, MIT license, and module credits
- LICENSE.md (MIT, Copyright Morgan Blackthorne)

## [0.1.1] - 2026-02-14

### Changed
- Migrated API domain from `crosspost.windsofstorm.net` to `social.jasmer.tools`
- Switched linting/formatting toolchain from black + flake8 to ruff
- SES sender address updated to `noreply@jasmer.tools`

### Added
- Makefile with targets for lint, test, build, and installer
- `pyproject.toml` with ruff and pytest configuration
- CHANGELOG.md for tracking release history
- README.md with full project documentation
- GitHub Actions workflow for automated draft releases on tag push

## [0.1.0] - 2026-02-14

### Added
- Initial Phase 0 implementation
- Twitter posting via Tweepy (OAuth 1.0a + v2 API)
- Bluesky posting via AT Protocol with automatic link facets
- PyQt5 GUI with post composer, live character counters, and platform selection
- Tabbed image preview dialog with per-platform resize/compression
- Image processing pipeline (RGBA conversion, LANCZOS resize, iterative compression)
- Results dialog with clickable post URLs and copy buttons
- Error code system (PLATFORM-CATEGORY-DETAIL format) with user-friendly messages
- First-run setup wizard for credential configuration
- Settings dialog (General, Accounts, Advanced tabs)
- File logging with automatic screenshot capture on errors
- Log upload to remote endpoint via HTTP POST
- Auto-update checker via GitHub Releases API
- Draft auto-save with restore prompt on restart
- CloudFormation template for AWS Lambda + API Gateway + S3 + SES backend
- PyInstaller build spec and NSIS installer script
