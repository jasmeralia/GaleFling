# Emoji Picker — Design Spec

Status: locked for implementation. All decisions below are final; do not leave
open design questions — if something genuinely blocks implementation, stop
and ask rather than guessing.

## Goal

Add a full emoji picker to `PostComposer`'s caption/text field so Rin can
browse/search and insert emoji into a post's text without leaving the app or
relying on the OS emoji picker.

## Non-goals

- Do not change character-counting behavior. `_update_counters` already uses
  `len(text)` (Python codepoint count) for every platform, including
  manually-typed or pasted emoji today. Emoji inserted via the picker go
  through the exact same `textChanged` path — this is not a new correctness
  problem and is out of scope to "fix."
- Do not add emoji support to `log_submit_dialog.py`'s notes field or any
  other non-caption `QTextEdit`. `PostComposer._text_edit` is the only
  target (see Architecture below for why).
- Do not add per-platform emoji stripping/validation (e.g. if some platform
  mangles certain emoji server-side). Functional tests should surface this
  if it happens; fixing a specific platform's emoji handling is separate
  follow-up work, not part of this task.
- Do not run functional tests as part of this implementation task. Unit
  tests (`make test-cov`) must pass; functional tests will be run
  separately by the requester after review.

## Architecture

There is exactly one free-text caption/post-body widget in the whole GUI:
`PostComposer._text_edit` (`src/gui/post_composer.py:75`, a plain
`QTextEdit`). `MainWindow` holds one `PostComposer` instance
(`src/gui/main_window.py:476`). The picker is added directly inside
`PostComposer` — no new shared base widget is needed since there is nothing
else to share it with.

### New file: `src/gui/emoji_picker.py`

Two classes:

**`EmojiPickerButton(QToolButton)`**
- Text/icon: `'\U0001F60A'` (😊) as button text (no icon asset needed — Qt
  renders the glyph via the system font).
- `emoji_selected = pyqtSignal(str)` — emitted with a single emoji grapheme
  string when the user picks one from the popup.
- `set_recent_emoji(recent: list[str]) -> None` — seeds the "Recent"
  category from persisted state. Called once by `PostComposer` after
  construction.
- `get_recent_emoji() -> list[str]` — current MRU list, most-recent-first.
- On click, constructs and shows an `EmojiPickerPopup` positioned just below
  the button (`popup.move(self.mapToGlobal(QPoint(0, self.height())))`),
  then `popup.show()`.
- When the popup emits a selection, the button:
  1. re-emits it via `emoji_selected`
  2. updates its internal recent list (move-to-front if already present,
     insert at front otherwise, dedupe, cap at 24 entries)
  3. does **not** close the popup (see popup behavior below)

**`EmojiPickerPopup(QFrame)`**
- Constructed with `Qt.WindowType.Popup` window flag so it closes
  automatically on outside click and on focus loss (native Qt popup
  behavior) — no manual close button required, but pressing `Escape` must
  also close it explicitly (connect a shortcut or override `keyPressEvent`).
- Takes the current recent-emoji list and full emoji dataset at construction.
- Layout top to bottom:
  1. `QLineEdit` search box, placeholder `'Search emoji...'`, given focus
     immediately on show (`setFocus()` after `show()`/via `showEvent`).
  2. A row of category buttons/tabs: Recent, Smileys & Emotion, People &
     Body, Animals & Nature, Food & Drink, Travel & Places, Activities,
     Objects, Symbols, Flags. "Recent" is selected by default if non-empty,
     otherwise "Smileys & Emotion".
  3. A `QListWidget` grid (`setViewMode(QListView.ViewMode.IconMode)`,
     `setFlow(QListView.Flow.LeftToRight)`, `setWrapping(True)`,
     `setResizeMode(QListView.ResizeMode.Adjust)`,
     `setUniformItemSizes(True)`, `setSpacing(2)`, fixed popup size around
     360x420px) showing emoji glyphs as plain item text at a larger point
     size (e.g. 20pt) — no icon assets, this is just a differently-sized
     font on `QListWidgetItem`.
- Search behavior: when the search box is non-empty, the grid shows every
  dataset emoji whose name or any alias/keyword contains the search text
  (case-insensitive substring match), across all categories, and the
  category row is disabled/ignored while searching. When the search box is
  cleared, the grid reverts to showing the currently selected category.
- Selecting an item (single click) emits `emoji_selected(str)` and keeps the
  popup open, so multiple emoji can be inserted in one session — this is a
  deliberate UX choice (matches Discord/Slack-style pickers), not an
  oversight.
- Hovering an item should show a tooltip with the emoji's name (accessibility
  / discoverability, since names aren't otherwise visible in grid mode).

### Emoji dataset

Add `emoji>=2.14.0` to `requirements.txt` (PyPI package `emoji`,
https://github.com/carpedm20/emoji — MIT licensed, no native/binary
components, pure-Python Unicode CLDR data, ~50M downloads/month; this is a
plain data dependency, not a trust-sensitive binary swap). Use its
`EMOJI_DATA` table as the source of truth for: the emoji glyph, its
canonical English name, and searchable aliases. Filter to "fully-qualified"
base emoji only (exclude standalone Unicode component/modifier codepoints
that aren't meaningful on their own, e.g. bare skin-tone modifiers or
regional indicator letters) — do not attempt to enumerate every
skin-tone/gender variant combination; showing the default/base glyph for
each concept is sufficient for v1.

For category grouping, the `emoji` package does not ship a stable public
"category" field across versions. Build a small static mapping module,
`src/resources/emoji_categories.py`, generated once (by a short one-off
script, not committed) from Unicode's own `emoji-test.txt` group headers,
mapping each emoji's codepoint sequence to one of the nine category names
listed above. If a dataset entry has no category mapping, place it in
"Objects" rather than dropping it. This mapping only needs to be generated
once during implementation; it ships as a static Python data file
(dict/tuple literal), not runtime-fetched.

### `src/gui/post_composer.py` changes

- Import and instantiate `EmojiPickerButton` in `_init_ui`, placed
  immediately to the right of the `_text_label` "Post Text:" label (same
  row, small `QHBoxLayout`) — not inside the text edit itself.
- New signal: `recent_emoji_changed = pyqtSignal(list)`.
- New method `set_recent_emoji(recent: list[str]) -> None` — forwards to
  `self._emoji_button.set_recent_emoji(recent)`, mirroring the existing
  `set_last_image_dir` pattern (`post_composer.py:57`).
- Connect `self._emoji_button.emoji_selected` to a new private slot
  `_on_emoji_selected(self, emoji_char: str) -> None` that:
  1. calls `self._text_edit.insertPlainText(emoji_char)`
  2. calls `self._text_edit.setFocus()` (so typing can continue immediately)
  3. emits `self.recent_emoji_changed.emit(self._emoji_button.get_recent_emoji())`
  4. logs `get_logger().info('User selected Post Composer > Insert Emoji')`
     (log the action, not the individual emoji character each time — no
     per-character log spam)
- Log `get_logger().info('User selected Post Composer > Open Emoji Picker')`
  when the picker button is clicked (connect alongside the existing click
  handling, matching the `get_logger().info(f'User selected ...')` idiom
  used throughout `settings_dialog.py`/`setup_wizard.py` per AGENTS.md
  rule 6 — this applies to any discrete user action, not just literal
  `QMenu` entries).

### `src/core/config_manager.py` changes

- Add `'recent_emoji': []` to `DEFAULT_CONFIG`.
- Add property pair, following the exact pattern of `last_selected_accounts`
  (`config_manager.py:187-193`):
  ```python
  @property
  def recent_emoji(self) -> list[str]:
      value = self._config.get('recent_emoji', [])
      return value if isinstance(value, list) else []

  @recent_emoji.setter
  def recent_emoji(self, value: list[str]) -> None:
      self.set('recent_emoji', list(value)[:24])
  ```

### `src/gui/main_window.py` changes

Immediately after the existing composer wiring block
(`main_window.py:476-493`), add, mirroring the `set_last_image_dir` line:
```python
self._composer.set_recent_emoji(self._config.recent_emoji)
self._composer.recent_emoji_changed.connect(
    lambda recent: setattr(self._config, 'recent_emoji', recent)
)
```

### `src/gui/main_window.py` — About dialog dependency list

Add one entry to `_ABOUT_DEPENDENCIES` (`main_window.py:336-351`), keeping
alphabetical order (case-insensitive) among the existing tuples:
```python
('emoji', 'https://github.com/carpedm20/emoji', 'Emoji data for the picker'),
```
(goes between `'boto3'` and `'ffmpeg'`).

### `requirements.txt`

Add `emoji>=2.14.0` in alphabetical position among the existing pinned
packages.

## Unit tests

Framework: pytest-qt, `qtbot` fixture, matching `tests/test_post_composer.py`
conventions (direct access to private widget attributes is the established
idiom here — do not add getters solely for test access).

New file `tests/test_emoji_picker.py`:
- Picker popup builds without error and contains at least one item per
  default/"Smileys & Emotion" category.
- Search filters the grid: typing a known emoji name (e.g. `'grinning'`)
  leaves only matching items visible/present; clearing the search restores
  the category view.
- Selecting an item emits `emoji_selected` with the expected glyph string.
- Selecting an item does not close the popup (`popup.isVisible()` still
  `True` after a simulated click — use `qtbot.mouseClick` or directly
  invoke the item-activation slot, whichever is reliable off-screen).
- Category switching changes the displayed set of items.
- `EmojiPickerButton.get_recent_emoji()`/`set_recent_emoji()` round-trip,
  MRU ordering, dedup, and the 24-entry cap.

Extend `tests/test_post_composer.py`:
- `composer._emoji_button` exists and clicking it (or directly invoking
  its handler) inserts an emoji at the current cursor position of
  `composer._text_edit` — assert on `composer._text_edit.toPlainText()`.
- `composer.set_recent_emoji([...])` forwards correctly (assert via
  `composer._emoji_button.get_recent_emoji()`).
- Emitting an emoji selection updates `composer.recent_emoji_changed` (use
  `qtbot.waitSignal` or a connected spy).
- Character counter (`composer._char_count_label`) updates correctly after
  an emoji insertion (sanity check that the existing `_update_counters`
  path still fires — not a test of counting *correctness* for multi-
  codepoint emoji, which is explicitly out of scope).

Extend `tests/test_config_manager.py` (or create it if it does not already
exist — check first) with a `recent_emoji` get/set/cap/default test
mirroring the existing property tests for other list-valued config keys.

All new/changed code must pass `make lint` and `make test-cov` with no
regressions.

## Functional tests (write, but do NOT run)

Add non-mutating functional coverage proving an emoji survives the actual
posting path end-to-end, without publishing anything. Codex must write
these tests but must **not** execute `make test-functional-cmd` or any
direct `pytest tests/functional/...` invocation — the requester will run
them separately, non-mutating, on both Linux and Windows.

1. **WebView platform (Fansly), text-injection style** — extend or add
   alongside `TestFanslyTextInjection.test_text_injection_via_platform`
   (`tests/functional/test_webview_fansly.py:663-688`) with a case that
   injects text containing at least one multi-codepoint/ZWJ emoji (e.g.
   `'\U0001F468‍\U0001F469‍\U0001F467'` family emoji, or simpler
   `'\U0001F600'` 😀 plus one ZWJ sequence) via `platform._inject_text(...)`
   and reads it back via `_read_composer_text(page)`, asserting exact
   round-trip. Mark `@pytest.mark.functional @pytest.mark.non_mutating`.
   Use `mutating_post_text()`/`mutating_post_tag()` helpers if the test
   needs any tagged text — but since this is non-mutating text-injection
   only (nothing gets submitted), a bare literal emoji string is fine and
   does not need to go through the neutral-tag helpers (those exist to
   keep *published* content neutral per AGENTS.md rule 15; this test
   never publishes).
2. **API platform (Bluesky)** — add a non-mutating unit-style check in the
   Bluesky functional suite (model on the text-building/encoding parts of
   `tests/functional/test_bluesky_post.py`, but do not add a new mutating
   post) confirming the adapter's text-preparation path preserves emoji
   byte-for-byte (e.g. a round-trip through whatever text-normalization the
   adapter applies before sending, without actually calling the network
   post endpoint). If no non-mutating hook exists for this, it is
   acceptable to skip this one and note why in the PR description rather
   than inventing a mutating test.

Both new/modified functional test files must still satisfy
`tests/functional/conftest.py`'s hard requirement that every
`@pytest.mark.functional` test carries exactly one of
`non_mutating`/`mutating`.

## Documentation

- `docs/ARCHITECTURE_OVERVIEW.md` needs no changes (it's subsystem-level,
  not widget-level, per existing convention).
- `AGENTS.md`/`CLAUDE.md` need no changes — this feature doesn't introduce a
  new project-wide convention, just applies existing ones (menu-logging,
  About-dialog dependency list).
- Add a short "Emoji Picker" entry to `CHANGELOG.md` under `[Unreleased]`.

## Acceptance criteria

1. `make lint` passes.
2. `make test-cov` passes, including new tests listed above.
3. New non-mutating functional tests are written (not run by Codex) and are
   correctly marked per the functional-test marker requirements.
4. `emoji` dependency added to `requirements.txt` and to the About dialog's
   dependency list, alphabetically ordered in both places.
5. `CHANGELOG.md` has an `[Unreleased]` entry for the feature.
6. Every new discrete user action (opening the picker, inserting an emoji)
   logs via the existing `get_logger().info('User selected ...')` idiom.
7. No changes to any file outside: `src/gui/emoji_picker.py` (new),
   `src/resources/emoji_categories.py` (new), `src/gui/post_composer.py`,
   `src/core/config_manager.py`, `src/gui/main_window.py`,
   `requirements.txt`, `CHANGELOG.md`, `tests/test_emoji_picker.py` (new),
   `tests/test_post_composer.py`, `tests/test_config_manager.py`,
   `tests/functional/test_webview_fansly.py`, and optionally
   `tests/functional/test_bluesky_post.py`.
