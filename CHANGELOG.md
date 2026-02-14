# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
