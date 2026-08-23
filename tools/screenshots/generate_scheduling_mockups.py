#!/usr/bin/env python3
"""Generate deterministic scheduling design mockups.

The scheduling implementation now exists, but these remain fake-data design
renders so documentation regeneration never touches a user's real queue.
They use the app's real
theme, tokens, and icon assets (`apply_theme`, `src/utils/tokens.py`,
`src/resources/icons/`) so they read as GaleFling rather than a generic
wireframe. The composer render uses the real `PostComposer`; the settings
mockup injects its controls into the real `SettingsDialog`.

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
from PyQt6.QtCore import QDate, QDateTime, QPoint, Qt, QTime
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
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
    QVBoxLayout,
)

from src.core.auth_manager import AuthManager
from src.core.config_manager import ConfigManager
from src.gui.post_composer import PostComposer
from src.gui.results_dialog import _render_svg_colored
from src.gui.schedule_dialog import _danger_button_style, _section_heading, _status_label
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


_BADGE_BORDER = 3  # reserved on all sides so failed/ok badges share one footprint


def _platform_badge(platform_key: str, size: int = 28, *, failed: bool = False) -> QPixmap:
    spec = PLATFORM_SPECS_MAP[platform_key]
    total = size + _BADGE_BORDER * 2
    pixmap = QPixmap(total, total)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if failed:
        pen = QPen(QColor(tokens.DANGER))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(1, 1, total - 2, total - 2)
    painter.setBrush(QColor(spec.platform_color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(_BADGE_BORDER, _BADGE_BORDER, size, size)

    icon_file = _BRAND_ICON_FILES.get(platform_key)
    if icon_file:
        icon_size = round(size * 0.55)
        icon_pixmap = _render_svg_colored(
            _ICONS_DIR / 'brands' / icon_file, icon_size, QColor(tokens.TEXT)
        )
        offset = _BADGE_BORDER + (size - icon_size) // 2
        painter.drawPixmap(offset, offset, icon_pixmap)
    painter.end()
    return pixmap


def _badge_label(platform_key: str, size: int = 28, *, failed: bool = False) -> QLabel:
    label = QLabel()
    pixmap = _platform_badge(platform_key, size, failed=failed)
    label.setPixmap(pixmap)
    label.setFixedSize(pixmap.size())
    return label


def capture_composer_schedule_icon(app: QApplication) -> None:
    """Capture the real composer's calendar and emoji controls."""
    composer = PostComposer()
    apply_theme(app, composer)
    composer.set_text('Trying out scheduled posts today ✨')

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


# One of each state real ScheduledPostsDialog.refresh() can render, matching its
# Pending / Recent Activity split and per-state action buttons (schedule_dialog.py's
# _build_row). The due/updated text is baked in as static strings rather than
# computed from datetime.now(), like _build_row's _format_relative_due /
# _format_time_ago do, so re-running this script doesn't churn the PNG on every
# regeneration.
_QUEUE_ITEMS = [
    {
        'state': 'pending',
        'platforms': ('bluesky', 'meta_instagram'),
        'failed_platforms': frozenset(),
        'caption': 'Trying out scheduled posts today ✨',
        'due_line': 'Sat, Aug 22, 2026 · 9:00 AM  ·  in 18 hours',
    },
    {
        # Mixed outcome: bluesky succeeded, facebook failed. The still-failed
        # platform gets a danger-colored ring so a partial failure reads as
        # partial, not as "everything here failed" -- see schedule_dialog.py's
        # _platform_badge / _target_summary for the real (non-mockup) version.
        'state': 'failed',
        'platforms': ('bluesky', 'meta_facebook_page'),
        'failed_platforms': frozenset({'meta_facebook_page'}),
        'caption': 'Behind-the-scenes from this week’s shoot',
        'due_line': 'Was due Thu, Aug 20, 2026 · 6:00 PM · updated 2 hours ago',
    },
    {
        'state': 'posted',
        'platforms': ('twitter',),
        'failed_platforms': frozenset(),
        'caption': 'Quick update for everyone — more soon!',
        'due_line': 'Was due Wed, Aug 19, 2026 · 11:30 AM · updated 1 day ago',
    },
]


def _queue_row(item: dict) -> QFrame:
    frame = QFrame()
    frame.setFrameShape(QFrame.Shape.StyledPanel)
    layout = QVBoxLayout(frame)
    # Contents margins, not frame.setStyleSheet('QFrame { padding; margin }') --
    # that combination corrupts child layout under the offscreen backend (see
    # the results_dialog.py finding in SCHEDULING_UI_DESIGN.md's changelog).
    layout.setContentsMargins(8, 8, 8, 8)

    badges_row = QHBoxLayout()
    for key in item['platforms']:
        badges_row.addWidget(_badge_label(key, size=26, failed=key in item['failed_platforms']))
    badges_row.addStretch()
    layout.addLayout(badges_row)

    caption = QLabel(item['caption'])
    caption.setWordWrap(True)
    layout.addWidget(caption)

    due_label = QLabel(item['due_line'])
    due_label.setStyleSheet(f'color: {tokens.TEXT_MUTED};')
    layout.addWidget(due_label)

    actions = QHBoxLayout()
    actions.addWidget(_status_label(item['state']))
    actions.addStretch()
    if item['state'] == 'pending':
        actions.addWidget(QPushButton('Edit'))
        cancel_btn = QPushButton('Cancel')
        cancel_btn.setStyleSheet(_danger_button_style())
        actions.addWidget(cancel_btn)
    else:
        actions.addWidget(QPushButton('View Results'))
        if item['state'] == 'failed':
            actions.addWidget(QPushButton('Edit && Retry'))
        dismiss_btn = QPushButton('Dismiss')
        dismiss_btn.setStyleSheet(_danger_button_style())
        actions.addWidget(dismiss_btn)
    layout.addLayout(actions)

    return frame


def build_queue_dialog() -> QDialog:
    """Queue management: pending, successful, and failed posts, satisfying R2."""
    dialog = QDialog()
    dialog.setWindowTitle('Scheduled Posts')
    dialog.setMinimumWidth(580)
    layout = QVBoxLayout(dialog)

    heading = QLabel('<b>Scheduled Posts</b>')
    heading.setStyleSheet('font-size: 18px;')
    layout.addWidget(heading)

    pending_items = [item for item in _QUEUE_ITEMS if item['state'] == 'pending']
    history_items = [item for item in _QUEUE_ITEMS if item['state'] != 'pending']

    layout.addWidget(_section_heading('Pending'))
    for item in pending_items:
        layout.addWidget(_queue_row(item))

    layout.addWidget(_section_heading('Recent Activity'))
    for item in history_items:
        layout.addWidget(_queue_row(item))

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
    """Capture the real Settings > Advanced startup controls."""
    config = ConfigManager()
    auth_manager = AuthManager()
    dialog = SettingsDialog(config, auth_manager)
    apply_theme(app, dialog)

    startup_group = next(g for g in dialog.findChildren(QGroupBox) if g.title() == 'Startup')
    autostart_cb = startup_group.findChild(QCheckBox)
    assert autostart_cb is not None
    autostart_cb.setChecked(True)
    launch_mode = startup_group.findChild(QComboBox)
    assert launch_mode is not None
    launch_mode.setCurrentIndex(1)

    dialog.show()
    QApplication.processEvents()
    _select_settings_nav_item(dialog, 'Advanced')
    QApplication.processEvents()

    _save(_grab(dialog), 'settings-start-at-login.png')
    dialog.close()


def capture_tray_menu(app: QApplication) -> None:
    """The tray icon's right-click menu -- alphabetical, matching tray_icon.py."""
    menu = QMenu()
    apply_theme(app)
    menu.addAction('About')
    menu.addAction('Check for Updates')
    menu.addAction('Exit')
    menu.addAction('Scheduled Posts (3)')
    menu.addAction('Show GaleFling')
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
