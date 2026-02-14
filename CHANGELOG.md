# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- Release assets now omit the standalone `GalePost.exe` (installer + portable zip only)

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
- Updated git remote to new repository URL (`jasmeralia/GalePost`)

## [0.2.0] - 2026-02-14

### Changed
- Rebranded application from "Social Media Poster" to "GalePost"
- Repository renamed to `jasmeralia/galepost`
- Log upload endpoint moved to `galepost.jasmer.tools`
- All build artifacts now use GalePost naming (exe, installer, portable zip)
- Windows AppData directory changed to `GalePost`
- Updated GitHub Actions workflow for GalePost build artifacts

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
