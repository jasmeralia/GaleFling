# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
