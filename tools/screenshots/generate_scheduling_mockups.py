#!/usr/bin/env python3
"""Generate design mockups for the not-yet-built scheduling UI.

Scheduling is Phase 1 work that hasn't started (see docs/plans/SCHEDULING.md
and docs/plans/SCHEDULING_UI_DESIGN.md) -- there is no scheduler, queue, or
scheduling dialog in the codebase yet. These images are therefore *mockups*,
not screenshots of real behavior: every widget here is built ad hoc by this
script rather than driven from production classes. They use the app's real
theme, tokens, and icon assets (`apply_theme`, `src/utils/tokens.py`,
`src/resources/icons/`) so they read as GaleFling rather than a generic
wireframe, and the settings mockup goes one step further by injecting its
new controls into the real `SettingsDialog` so they sit alongside controls
that do exist today.

All data below (captions, handles, dates) is fabricated -- no resemblance to
real accounts or real scheduled content. Dates are hardcoded rather than
computed from `datetime.now()` so re-running this script doesn't churn the
output PNGs' bytes on every regeneration.

Usage:
    .venv/bin/python tools/screenshots/generate_scheduling_mockups.py
"""

# The HOME/QT_QPA_PLATFORM env vars below must be set before importing
# anything that touches app config paths or Qt.
# ruff: noqa: E402

import os
import sys
import tempfile
from pathlib import Path

_SCRATCH_HOME = tempfile.mkdtemp(prefix='galefling-scheduling-mockup-home-')
os.environ['HOME'] = _SCRATCH_HOME
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PIL import Image
from PyQt6.QtCore import QDate, QDateTime, QPoint, QSize, Qt, QTime
from PyQt6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.core.auth_manager import AuthManager
from src.core.config_manager import ConfigManager
from src.gui.icon_utils import tinted_icon
from src.gui.post_composer import PostComposer
from src.gui.results_dialog import _render_svg_colored
from src.gui.settings_dialog import SettingsDialog
from src.utils import tokens
from src.utils.constants import PLATFORM_SPECS_MAP
from src.utils.theme import apply_theme

OUT_DIR = Path(__file__).resolve().parent.parent.parent / 'docs' / 'images' / 'scheduling'
_ICONS_DIR = Path(__file__).resolve().parent.parent.parent / 'src' / 'resources' / 'icons'

# The five schedulable platforms per SCHEDULING.md -- FetLife is excluded
# from scheduling entirely, so it never appears in these mockups.
_BRAND_ICON_FILES = {
    'twitter': 'twitter.svg',
    'bluesky': 'bluesky.svg',
    'meta_threads': 'threads.svg',
    'meta_instagram': 'instagram.svg',
    'meta_facebook_page': 'facebook.svg',
}

PRIMARY_BUTTON_STYLE = (
    f'QPushButton {{ background-color: {tokens.SUCCESS}; color: {tokens.CANVAS}; '
    'font-weight: bold; padding: 8px 20px; border-radius: 4px; border: none; }'
    f'QPushButton:hover {{ background-color: {tokens.darken(tokens.SUCCESS, 0.85)}; }}'
)

DANGER_BUTTON_STYLE = f'QPushButton {{ color: {tokens.DANGER}; border-color: {tokens.DANGER}; }}'


def _qpixmap_to_pil(pixmap) -> Image.Image:
    qimage = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = qimage.width(), qimage.height()
    buf = qimage.bits().asstring(qimage.sizeInBytes())
    return Image.frombuffer('RGBA', (width, height), buf, 'raw', 'RGBA', 0, 1).copy()


def _grab(widget) -> Image.Image:
    QApplication.processEvents()
    return _qpixmap_to_pil(widget.grab())


def _save(image: Image.Image, name: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / name
    image.convert('RGB').save(path)
    print(f'Wrote {path} ({image.width}x{image.height})')


def _platform_badge(platform_key: str, size: int = 28) -> QPixmap:
    spec = PLATFORM_SPECS_MAP[platform_key]
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(spec.platform_color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(0, 0, size, size)

    icon_file = _BRAND_ICON_FILES.get(platform_key)
    if icon_file:
        icon_size = round(size * 0.55)
        icon_pixmap = _render_svg_colored(
            _ICONS_DIR / 'brands' / icon_file, icon_size, QColor(tokens.TEXT)
        )
        offset = (size - icon_size) // 2
        painter.drawPixmap(offset, offset, icon_pixmap)
    painter.end()
    return pixmap


def _badge_label(platform_key: str, size: int = 28) -> QLabel:
    label = QLabel()
    label.setPixmap(_platform_badge(platform_key, size))
    label.setFixedSize(size, size)
    return label


def _status_pill(text: str, color: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(
        f'QLabel {{ background-color: {tokens.with_alpha(color, 0.18)}; color: {color}; '
        'border-radius: 8px; padding: 2px 10px; font-weight: 600; }'
    )
    return label


def _calendar_icon(size: int, color: str) -> QIcon:
    """Render the repo's Material Symbols calendar asset in the requested color."""
    return tinted_icon(_ICONS_DIR / 'ui' / 'calendar_month.svg', color, size)


def _find_containing_layout(layout, widget):
    """Locate the nested QLayout that directly holds `widget`, and its index."""
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item.widget() is widget:
            return layout, i
        nested = item.layout()
        if nested is not None:
            found = _find_containing_layout(nested, widget)
            if found is not None:
                return found
    return None


def capture_composer_schedule_icon(app: QApplication) -> None:
    """Composer: a new calendar icon button, immediately left of the emoji picker.

    Injects into the real, running `PostComposer` (`post_composer.py:305-313`'s
    `emoji_row`), the same technique `capture_settings_start_at_login` uses for
    `SettingsDialog` -- not a from-scratch replica.
    """
    composer = PostComposer()
    apply_theme(app, composer)
    composer.set_text('Trying out scheduled posts today ✨')

    # Both icons at 30x30 -- up from EmojiPickerButton's real 20x20
    # (emoji_picker.py), a design change this mockup applies to the live
    # instance rather than a size the production button already has.
    icon_size = 30
    composer._emoji_button.setIconSize(QSize(icon_size, icon_size))

    calendar_btn = QToolButton()
    calendar_btn.setIcon(_calendar_icon(icon_size, tokens.TEXT))
    calendar_btn.setIconSize(QSize(icon_size, icon_size))
    calendar_btn.setToolTip('Schedule this post for a later time')

    found = _find_containing_layout(composer.layout(), composer._emoji_button)
    assert found is not None, 'post_composer.py restructured -- update this mockup'
    emoji_row, index = found
    emoji_row.insertWidget(index, calendar_btn)

    composer.show()
    composer.resize(560, 420)
    QApplication.processEvents()

    top = composer._text_label.mapTo(composer, QPoint(0, 0)).y() - 6
    bottom = (
        composer._emoji_button.mapTo(composer, QPoint(0, composer._emoji_button.height())).y() + 6
    )
    full = _grab(composer)
    crop = full.crop((0, top, full.width, bottom))
    _save(crop, 'composer-schedule-icon.png')
    composer.close()


def build_schedule_dialog() -> QDialog:
    """Schedule picker opened by the composer's new calendar icon button."""
    dialog = QDialog()
    dialog.setWindowTitle('Schedule Post')
    dialog.setMinimumWidth(440)
    layout = QVBoxLayout(dialog)

    warning = QLabel(
        'Scheduled posts require this computer to stay on, logged in, and running '
        'GaleFling until the post fires.'
    )
    warning.setWordWrap(True)
    warning.setStyleSheet(
        f'QLabel {{ background-color: {tokens.with_alpha(tokens.WARNING, 0.15)}; '
        f'color: {tokens.WARNING}; border: 1px solid {tokens.WARNING}; '
        'border-radius: 4px; padding: 8px; }'
    )
    layout.addWidget(warning)

    platforms_row = QHBoxLayout()
    platforms_row.addWidget(QLabel('Posting to:'))
    for key in ('bluesky', 'meta_instagram'):
        platforms_row.addWidget(_badge_label(key))
    platforms_row.addStretch()
    layout.addLayout(platforms_row)

    caption_preview = QLabel('“Trying out scheduled posts today ✨” + 1 image')
    caption_preview.setStyleSheet(f'color: {tokens.TEXT_SECONDARY};')
    caption_preview.setWordWrap(True)
    layout.addWidget(caption_preview)

    form = QFormLayout()
    date_edit = QDateTimeEdit()
    date_edit.setCalendarPopup(True)
    date_edit.setDateTime(QDateTime(QDate(2026, 8, 22), QTime(9, 0)))
    date_edit.setDisplayFormat('MMM d, yyyy  h:mm AP')
    calendar_path = (_ICONS_DIR / 'ui' / 'calendar_month.svg').as_posix()
    date_edit.setStyleSheet(
        f'QDateTimeEdit {{ background-color: {tokens.SURFACE_INSET}; color: {tokens.TEXT}; '
        f'border: 1px solid {tokens.BORDER}; border-radius: 4px; '
        f'padding: 5px 40px 5px 8px; selection-background-color: {tokens.ACCENT}; '
        f'selection-color: {tokens.CANVAS}; }} '
        f'QDateTimeEdit:focus {{ border-color: {tokens.ACCENT}; }} '
        'QDateTimeEdit::drop-down { subcontrol-origin: padding; '
        'subcontrol-position: top right; width: 34px; '
        f'background-color: {tokens.ACCENT}; border-left: 1px solid {tokens.BORDER}; '
        'border-top-right-radius: 3px; border-bottom-right-radius: 3px; } '
        f'QDateTimeEdit::down-arrow {{ image: url({calendar_path}); width: 18px; height: 18px; }}'
    )
    form.addRow('Post at:', date_edit)
    layout.addLayout(form)

    autostart_cb = QCheckBox('Start GaleFling automatically when I log in (recommended)')
    autostart_cb.setChecked(True)
    layout.addWidget(autostart_cb)
    autostart_hint = QLabel(
        '<i>Shown once, the first time you schedule a post while this is off.</i>'
    )
    autostart_hint.setStyleSheet(f'color: {tokens.TEXT_MUTED};')
    layout.addWidget(autostart_hint)

    btn_row = QHBoxLayout()
    btn_row.addStretch()
    btn_row.addWidget(QPushButton('Cancel'))
    schedule_btn = QPushButton('Schedule Post')
    schedule_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
    btn_row.addWidget(schedule_btn)
    layout.addLayout(btn_row)

    return dialog


_QUEUE_ITEMS = [
    {
        'platforms': ('bluesky', 'meta_instagram'),
        'caption': 'Trying out scheduled posts today ✨',
        'due': 'Aug 22, 2026 · 9:00 AM',
        'relative': 'in 18 hours',
    },
    {
        'platforms': ('meta_facebook_page',),
        'caption': 'Behind-the-scenes from this week’s shoot',
        'due': 'Aug 23, 2026 · 6:00 PM',
        'relative': 'in 2 days',
    },
    {
        'platforms': ('twitter',),
        'caption': 'Quick update for everyone — more soon!',
        'due': 'Aug 25, 2026 · 11:30 AM',
        'relative': 'in 4 days',
    },
]


def build_queue_dialog() -> QDialog:
    """Queue management: pending items with per-item Edit/Cancel, satisfying R2."""
    dialog = QDialog()
    dialog.setWindowTitle('Scheduled Posts')
    dialog.setMinimumWidth(580)
    layout = QVBoxLayout(dialog)

    header = QLabel(f'{len(_QUEUE_ITEMS)} posts pending')
    header.setStyleSheet(f'color: {tokens.TEXT_MUTED};')
    layout.addWidget(header)

    for item in _QUEUE_ITEMS:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        row = QHBoxLayout(frame)
        # Contents margins, not frame.setStyleSheet('QFrame { padding; margin }') --
        # that combination corrupts child layout under the offscreen backend (see
        # the results_dialog.py finding in SCHEDULING_UI_DESIGN.md's changelog).
        row.setContentsMargins(8, 8, 8, 8)

        badges_widget = QWidget()
        badges_row = QHBoxLayout(badges_widget)
        badges_row.setContentsMargins(0, 0, 0, 0)
        for key in item['platforms']:
            badges_row.addWidget(_badge_label(key, size=26))
        row.addWidget(badges_widget)

        content = QVBoxLayout()
        caption = QLabel(item['caption'])
        caption.setWordWrap(True)
        content.addWidget(caption)
        due_label = QLabel(f'{item["due"]}  ·  {item["relative"]}')
        due_label.setStyleSheet(f'color: {tokens.TEXT_MUTED};')
        content.addWidget(due_label)
        row.addLayout(content, 1)

        row.addWidget(_status_pill('Pending', tokens.ACCENT))

        actions = QVBoxLayout()
        actions.addWidget(QPushButton('Edit'))
        cancel_btn = QPushButton('Cancel')
        cancel_btn.setStyleSheet(DANGER_BUTTON_STYLE)
        actions.addWidget(cancel_btn)
        row.addLayout(actions)

        layout.addWidget(frame)

    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    layout.addWidget(sep)

    btn_row = QHBoxLayout()
    btn_row.addWidget(QPushButton('New Scheduled Post…'))
    btn_row.addStretch()
    btn_row.addWidget(QPushButton('Close'))
    layout.addLayout(btn_row)

    return dialog


def build_reconciliation_dialog() -> QDialog:
    """Startup reconciliation: one item at a time, stepped, plus a bulk action."""
    dialog = QDialog()
    dialog.setWindowTitle('Missed Scheduled Posts')
    dialog.setMinimumWidth(480)
    layout = QVBoxLayout(dialog)

    progress = QLabel('Post 2 of 4')
    progress.setStyleSheet(f'color: {tokens.TEXT_MUTED}; font-weight: 600;')
    layout.addWidget(progress)

    intro = QLabel('GaleFling was closed when this post was due to go out.')
    intro.setWordWrap(True)
    layout.addWidget(intro)

    card = QFrame()
    card.setFrameShape(QFrame.Shape.StyledPanel)
    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(10, 10, 10, 10)

    badges_row = QHBoxLayout()
    for key in ('meta_instagram', 'meta_threads'):
        badges_row.addWidget(_badge_label(key))
    badges_row.addStretch()
    card_layout.addLayout(badges_row)

    caption = QLabel('New merch drop this weekend — details in bio!')
    caption.setWordWrap(True)
    card_layout.addWidget(caption)

    media_placeholder = QLabel('[ image.jpg ]')
    media_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
    media_placeholder.setFixedHeight(60)
    media_placeholder.setStyleSheet(
        f'background-color: {tokens.SURFACE_INSET}; color: {tokens.TEXT_MUTED}; '
        f'border: 1px dashed {tokens.BORDER}; border-radius: 4px;'
    )
    card_layout.addWidget(media_placeholder)

    was_due = QLabel('Was due: Aug 20, 2026 · 9:00 AM — 22 hours ago')
    was_due.setStyleSheet(f'color: {tokens.DANGER}; font-weight: 600;')
    card_layout.addWidget(was_due)

    layout.addWidget(card)

    action_row = QHBoxLayout()
    post_now_btn = QPushButton('Post Now')
    post_now_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
    action_row.addWidget(post_now_btn)
    action_row.addWidget(QPushButton('Edit'))
    delete_btn = QPushButton('Delete')
    delete_btn.setStyleSheet(DANGER_BUTTON_STYLE)
    action_row.addWidget(delete_btn)
    layout.addLayout(action_row)

    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    layout.addWidget(sep)

    bulk_row = QHBoxLayout()
    bulk_row.addStretch()
    bulk_row.addWidget(QPushButton('Post All Remaining (3)'))
    layout.addLayout(bulk_row)

    return dialog


def _select_settings_nav_item(dialog, label: str) -> None:
    for list_widget in dialog.findChildren(QListWidget):
        for row in range(list_widget.count()):
            item = list_widget.item(row)
            if item.text().strip() == label:
                list_widget.setCurrentItem(item)
                return


def capture_settings_start_at_login(app: QApplication) -> None:
    """Settings > Advanced: the real SettingsDialog with a mockup 'Startup' group

    and launch-mode selector inserted above its real 'WebView' group, in the
    same QGroupBox style as every other Advanced-tab section.
    """
    config = ConfigManager()
    auth_manager = AuthManager()
    dialog = SettingsDialog(config, auth_manager)
    apply_theme(app, dialog)

    startup_group = QGroupBox('Startup')
    startup_layout = QVBoxLayout(startup_group)
    autostart_cb = QCheckBox('Start GaleFling automatically when I log in')
    autostart_cb.setChecked(True)
    startup_layout.addWidget(autostart_cb)
    hint = QLabel(
        '<i>Keeps scheduled posts firing after a reboot — GaleFling launches '
        'automatically instead of waiting for you to reopen it.</i>'
    )
    hint.setWordWrap(True)
    startup_layout.addWidget(hint)

    launch_mode_row = QHBoxLayout()
    launch_mode_row.addWidget(QLabel('When started automatically:'))
    launch_mode = QComboBox()
    launch_mode.addItems(['Open the main window', 'Start minimized to the system tray'])
    launch_mode.setCurrentIndex(1)
    launch_mode_row.addWidget(launch_mode, 1)
    startup_layout.addLayout(launch_mode_row)

    webview_group = next(g for g in dialog.findChildren(QGroupBox) if g.title() == 'WebView')
    parent_layout = webview_group.parentWidget().layout()
    parent_layout.insertWidget(parent_layout.indexOf(webview_group), startup_group)

    dialog.show()
    QApplication.processEvents()
    _select_settings_nav_item(dialog, 'Advanced')
    QApplication.processEvents()

    _save(_grab(dialog), 'settings-start-at-login.png')
    dialog.close()


def capture_tray_menu(app: QApplication) -> None:
    """The tray icon's right-click menu, offered once background/tray operation ships."""
    menu = QMenu()
    apply_theme(app)
    menu.addAction('Show GaleFling')
    menu.addSeparator()
    menu.addAction('Scheduled Posts (3)')
    menu.addSeparator()
    menu.addAction('Check for Updates')
    menu.addAction('About')
    menu.addSeparator()
    menu.addAction('Exit')
    menu.move(0, 0)
    menu.show()
    QApplication.processEvents()

    _save(_grab(menu), 'tray-context-menu.png')
    menu.close()


def main() -> None:
    app = QApplication(sys.argv)
    apply_theme(app)

    capture_composer_schedule_icon(app)

    schedule_dialog = build_schedule_dialog()
    apply_theme(app, schedule_dialog)
    schedule_dialog.show()
    _save(_grab(schedule_dialog), 'schedule-dialog.png')
    schedule_dialog.close()

    queue_dialog = build_queue_dialog()
    apply_theme(app, queue_dialog)
    queue_dialog.show()
    _save(_grab(queue_dialog), 'scheduled-posts-queue.png')
    queue_dialog.close()

    reconciliation_dialog = build_reconciliation_dialog()
    apply_theme(app, reconciliation_dialog)
    reconciliation_dialog.show()
    _save(_grab(reconciliation_dialog), 'missed-post-reconciliation.png')
    reconciliation_dialog.close()

    capture_settings_start_at_login(app)
    capture_tray_menu(app)


if __name__ == '__main__':
    main()
