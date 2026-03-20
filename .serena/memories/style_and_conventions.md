# GaleFling — Code Style & Conventions

## Formatting
- Line length: 100
- Quote style: single quotes (ruff enforced)
- Imports: isort with `src` as first-party

## Type Hints
- Used throughout; Python 3.11+ union syntax (`X | Y`, `X | None`)
- `@dataclass` for data structures (PlatformSpecs, AccountConfig, PostResult)

## Naming
- Classes: PascalCase
- Functions/methods: snake_case
- Private: `_prefix`
- Constants: UPPER_SNAKE
- Qt overrides that violate naming (e.g. `closeEvent`, `paintEvent`): `# noqa: N802`

## Error Handling
- Platform errors use typed error codes from `ERROR_CODES` dict in `constants.py`
- `PostResult(success, error_code, error_message, ...)` returned from post()
- UI shows `USER_FRIENDLY_MESSAGES[error_code]` to the user
- WebView error codes prefixed `WV-`, API errors platform-prefixed (TW-, BS-, IG-)

## Qt Patterns
- Background work: `QThread` subclass with `pyqtSignal` for results
- Nested event loops: `QEventLoop` + `QTimer` for WebView async operations
- Dialog theming: always call `self._apply_dialog_theme(dialog)` after creating any dialog
- GC guard pattern: `self._pending_login_platform = temp` keeps platform alive during async login flow
- `QTimer.singleShot(0, fn)` to defer work until after the current event loop tick

## Mandatory Agent Rules (from AGENTS.md)
1. After code/docs changes, run the Release Checklist unless user says not to
2. Do not skip linting or tests; fix failures before concluding
3. Make smallest effective change unless broader refactor requested
4. Before bumping a minor version (Y in X.Y.Z), confirm with user first
5. New menu options must log: `User selected <Menu> > <Action>`
6. Functional tests and core code must stay in sync (session expiry, login detection, DOM behavior)

## Version Files to Update on Bump
- `src/utils/constants.py` — `APP_VERSION`
- `resources/default_config.json` — `"version"`
- `build/installer.nsi` — all version strings
- `build/version_info.txt` — all version strings
- `README.md` — Current Version + Release Build badge tag
- `CHANGELOG.md` — new entry at top
