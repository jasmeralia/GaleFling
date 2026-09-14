"""Scheduling dialogs for creating and reconciling queued posts."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from PyQt6.QtCore import QDateTime, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QCalendarWidget,
    QCheckBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from src.core.scheduled_post_queue import ScheduledPost, ScheduledPostQueue
from src.gui.icon_utils import tinted_icon
from src.gui.results_dialog import _render_svg_colored
from src.utils import tokens
from src.utils.constants import PLATFORM_SPECS_MAP

_CALENDAR_ICON = (
    Path(__file__).resolve().parent.parent / 'resources' / 'icons' / 'ui' / 'calendar_month.svg'
)
_BRAND_ICONS_DIR = Path(__file__).resolve().parent.parent / 'resources' / 'icons' / 'brands'
_BRAND_ICON_FILES = {
    'twitter': 'twitter.svg',
    'bluesky': 'bluesky.svg',
    'meta_threads': 'threads.svg',
    'meta_instagram': 'instagram.svg',
    'meta_facebook_page': 'facebook.svg',
}


def _local_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.astimezone()
    return value.astimezone()


def _format_due(value: datetime) -> str:
    return _local_datetime(value).strftime('%a, %b %d, %Y · %I:%M %p').replace(' 0', ' ')


def _relative_amount_label(value: datetime) -> tuple[str, bool]:
    seconds = int((_local_datetime(value) - datetime.now().astimezone()).total_seconds())
    overdue = seconds < 0
    seconds = abs(seconds)
    if seconds < 3600:
        amount = max(1, seconds // 60)
        unit = 'minute'
    elif seconds < 86400:
        amount = max(1, seconds // 3600)
        unit = 'hour'
    else:
        amount = max(1, seconds // 86400)
        unit = 'day'
    return f'{amount} {unit}{"s" if amount != 1 else ""}', overdue


def _format_relative_due(value: datetime) -> str:
    label, overdue = _relative_amount_label(value)
    return f'{label} overdue' if overdue else f'in {label}'


def _format_time_ago(value: datetime) -> str:
    label, _overdue = _relative_amount_label(value)
    return f'{label} ago'


_STATUS_STYLES = {
    'pending': (tokens.ACCENT, 'PENDING'),
    'posted': (tokens.SUCCESS, 'POSTED'),
    'failed': (tokens.DANGER, 'FAILED'),
}


def _status_label(state: str) -> QLabel:
    color, text = _STATUS_STYLES.get(state, (tokens.TEXT_SECONDARY, state.upper()))
    label = QLabel(text)
    label.setStyleSheet(
        f'color: {color}; border: 1px solid {color}; '
        'border-radius: 8px; padding: 2px 7px; font-weight: bold;'
    )
    return label


def _danger_button_style() -> str:
    return (
        f'color: {tokens.DANGER}; border: 1px solid {tokens.DANGER}; '
        'background: transparent; padding: 5px 12px; border-radius: 4px;'
    )


def _section_heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(
        f'color: {tokens.TEXT_SECONDARY}; font-weight: bold; font-size: 12px; margin-top: 6px;'
    )
    return label


_BADGE_BORDER = 3  # reserved on all sides so failed/ok badges share one footprint


def _platform_badge(platform_key: str, size: int = 30, *, failed: bool = False) -> QPixmap:
    spec = PLATFORM_SPECS_MAP.get(platform_key)
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
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(spec.platform_color if spec else tokens.BORDER))
    painter.drawEllipse(_BADGE_BORDER + 1, _BADGE_BORDER + 1, size - 2, size - 2)

    icon_name = _BRAND_ICON_FILES.get(platform_key)
    if icon_name:
        icon_size = max(14, size - 13)
        icon = _render_svg_colored(_BRAND_ICONS_DIR / icon_name, icon_size, QColor(tokens.TEXT))
        offset = _BADGE_BORDER + (size - icon_size) // 2
        painter.drawPixmap(offset, offset, icon)
    else:
        font = QFont()
        font.setBold(True)
        font.setPixelSize(max(12, size // 2))
        painter.setFont(font)
        painter.setPen(QColor(tokens.TEXT))
        badge_rect = pixmap.rect().adjusted(
            _BADGE_BORDER, _BADGE_BORDER, -_BADGE_BORDER, -_BADGE_BORDER
        )
        painter.drawText(badge_rect, int(Qt.AlignmentFlag.AlignCenter), platform_key[:1].upper())
    painter.end()
    return pixmap


def _target_summary(names: list[str], keys: list[str], failed: list[bool] | None = None) -> QWidget:
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(5)
    failed = failed if failed is not None else [False] * len(names)
    for name, key, is_failed in zip(names, keys, failed, strict=True):
        badge = QLabel()
        badge.setPixmap(_platform_badge(key, failed=is_failed))
        badge.setToolTip(f'{name} — failed to post' if is_failed else name)
        layout.addWidget(badge)
    names_label = QLabel(', '.join(names))
    names_label.setWordWrap(True)
    layout.addWidget(names_label)
    layout.addStretch()
    return widget


class ScheduleDialog(QDialog):
    """Pick a future due time after reviewing the post summary."""

    def __init__(
        self,
        *,
        text: str,
        account_names: list[str],
        media_count: int,
        autostart_enabled: bool,
        account_keys: list[str] | None = None,
        due_at: datetime | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle('Schedule Post')
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)

        warning = QLabel(
            'GaleFling must be running when this post is due. Start at login keeps '
            'the queue working after a reboot.'
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            f'background: {tokens.SURFACE_RAISED}; color: {tokens.WARNING}; '
            f'border: 1px solid {tokens.WARNING}; border-radius: 4px; padding: 8px;'
        )
        layout.addWidget(warning)

        form = QFormLayout()
        form.addRow('Post to:', _target_summary(account_names, account_keys or account_names))
        preview = text.strip().replace('\n', ' ')
        if len(preview) > 110:
            preview = preview[:107] + '…'
        caption = QLabel(preview)
        caption.setWordWrap(True)
        form.addRow('Caption:', caption)
        form.addRow('Media:', QLabel(f'{media_count} attachment(s)' if media_count else 'None'))

        minimum = datetime.now().astimezone() + timedelta(minutes=5)
        initial = _local_datetime(due_at) if due_at else minimum + timedelta(minutes=25)
        if initial < minimum:
            initial = minimum
        self._due_edit = QDateTimeEdit(QDateTime(initial))
        self._due_edit.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._due_edit.setDisplayFormat('ddd, MMM d, yyyy  h:mm AP')
        self._due_edit.setMinimumDateTime(QDateTime(minimum))
        self._due_edit.setToolTip('Choose when GaleFling should publish this post')
        self._due_edit.setStyleSheet('QDateTimeEdit { padding: 7px 9px; }')
        date_picker = QWidget()
        date_picker_layout = QHBoxLayout(date_picker)
        date_picker_layout.setContentsMargins(0, 0, 0, 0)
        date_picker_layout.setSpacing(5)
        date_picker_layout.addWidget(self._due_edit)
        calendar_button = QToolButton()
        calendar_button.setIcon(tinted_icon(_CALENDAR_ICON, tokens.TEXT, 24))
        calendar_button.setIconSize(QSize(24, 24))
        calendar_button.setFixedSize(38, self._due_edit.sizeHint().height() + 8)
        calendar_button.setToolTip('Open calendar')
        calendar_button.clicked.connect(self._open_calendar)
        date_picker_layout.addWidget(calendar_button)
        form.addRow('Publish at:', date_picker)
        layout.addLayout(form)

        self._autostart_cb: QCheckBox | None = None
        if not autostart_enabled:
            self._autostart_cb = QCheckBox('Start GaleFling automatically when I log in')
            self._autostart_cb.setChecked(True)
            layout.addWidget(self._autostart_cb)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        save = buttons.button(QDialogButtonBox.StandardButton.Save)
        assert save is not None
        save.setText('Schedule Post')
        save.setStyleSheet(
            f'background-color: {tokens.SUCCESS}; color: {tokens.CANVAS}; '
            'font-weight: bold; padding: 7px 18px; border-radius: 4px;'
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def due_at(self) -> datetime:
        return self._due_edit.dateTime().toPyDateTime().astimezone()

    @property
    def enable_autostart(self) -> bool:
        return bool(self._autostart_cb and self._autostart_cb.isChecked())

    def _validate_and_accept(self) -> None:
        minimum = datetime.now().astimezone() + timedelta(minutes=5)
        if self.due_at < minimum:
            QMessageBox.warning(
                self,
                'Choose a Later Time',
                'Scheduled posts must be at least 5 minutes in the future.',
            )
            return
        self.accept()

    def _open_calendar(self) -> None:
        menu = QMenu(self)
        calendar = QCalendarWidget(menu)
        calendar.setMinimumDate(self._due_edit.minimumDate())
        calendar.setSelectedDate(self._due_edit.date())
        action = QWidgetAction(menu)
        action.setDefaultWidget(calendar)
        menu.addAction(action)

        def select_date(date) -> None:
            self._due_edit.setDate(date)
            menu.close()

        calendar.clicked.connect(select_date)
        menu.exec(self._due_edit.mapToGlobal(self._due_edit.rect().bottomLeft()))


class ScheduledPostsDialog(QDialog):
    """View, edit, and cancel pending scheduled posts."""

    edit_requested = pyqtSignal(object)
    new_requested = pyqtSignal()
    queue_changed = pyqtSignal()
    view_results_requested = pyqtSignal(object)

    def __init__(
        self,
        queue: ScheduledPostQueue,
        display_name,
        parent: QWidget | None = None,
        *,
        platform_key=lambda account_id: account_id,
    ) -> None:
        super().__init__(parent)
        self._queue = queue
        self._display_name = display_name
        self._platform_key = platform_key
        self.setWindowTitle('Scheduled Posts')
        self.setMinimumSize(620, 360)
        self._layout = QVBoxLayout(self)

        heading = QLabel('<b>Scheduled Posts</b>')
        heading.setStyleSheet('font-size: 18px;')
        self._layout.addWidget(heading)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._layout.addWidget(self._scroll)

        footer = QHBoxLayout()
        new_button = QPushButton('New Scheduled Post…')
        new_button.clicked.connect(self.new_requested.emit)
        footer.addWidget(new_button)
        footer.addStretch()
        close_button = QPushButton('Close')
        close_button.clicked.connect(self.accept)
        footer.addWidget(close_button)
        self._layout.addLayout(footer)
        self.refresh()

    def refresh(self) -> None:
        container = QWidget()
        rows = QVBoxLayout(container)
        pending = self._queue.list_pending()
        history = self._queue.list_history()
        if not pending and not history:
            empty = QLabel('No posts scheduled')
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            rows.addStretch()
            rows.addWidget(empty)
            rows.addStretch()
        else:
            if pending:
                if history:
                    rows.addWidget(_section_heading('Pending'))
                for post in pending:
                    rows.addWidget(self._build_row(post))
            if history:
                rows.addWidget(_section_heading('Recent Activity'))
                for post in history:
                    rows.addWidget(self._build_row(post))
        rows.addStretch()
        old = self._scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        self._scroll.setWidget(container)

    def _build_row(self, post: ScheduledPost) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(frame)
        account_names = [self._display_name(account_id) for account_id in post.account_ids]
        account_keys = [self._platform_key(account_id) for account_id in post.account_ids]
        failed_ids = {
            result.get('account_id') for result in post.results if not result.get('success')
        }
        account_failed = [account_id in failed_ids for account_id in post.account_ids]
        layout.addWidget(_target_summary(account_names, account_keys, account_failed))
        preview = post.text.replace('\n', ' ')
        if len(preview) > 120:
            preview = preview[:117] + '…'
        caption = QLabel(preview)
        caption.setWordWrap(True)
        layout.addWidget(caption)
        if post.state == 'pending':
            due_text = f'{_format_due(post.due_at)} · {_format_relative_due(post.due_at)}'
        else:
            due_text = (
                f'Was due {_format_due(post.due_at)} · updated {_format_time_ago(post.updated_at)}'
            )
        due = QLabel(due_text)
        due.setStyleSheet(f'color: {tokens.TEXT_SECONDARY};')
        layout.addWidget(due)
        actions = QHBoxLayout()
        actions.addWidget(_status_label(post.state))
        actions.addStretch()
        if post.state == 'pending':
            edit = QPushButton('Edit')
            edit.clicked.connect(lambda _=False, item=post: self.edit_requested.emit(item))
            actions.addWidget(edit)
            cancel = QPushButton('Cancel')
            cancel.setStyleSheet(_danger_button_style())
            cancel.clicked.connect(lambda _=False, item=post: self._remove(item))
            actions.addWidget(cancel)
        else:
            view = QPushButton('View Results')
            view.clicked.connect(lambda _=False, item=post: self.view_results_requested.emit(item))
            actions.addWidget(view)
            if post.state == 'failed':
                retry = QPushButton('Edit && Retry')
                retry.clicked.connect(lambda _=False, item=post: self.edit_requested.emit(item))
                actions.addWidget(retry)
            dismiss = QPushButton('Dismiss')
            dismiss.setStyleSheet(_danger_button_style())
            dismiss.clicked.connect(lambda _=False, item=post: self._remove(item))
            actions.addWidget(dismiss)
        layout.addLayout(actions)
        return frame

    def _remove(self, post: ScheduledPost) -> None:
        if post.state == 'pending':
            title = 'Cancel Scheduled Post'
            message = 'Remove this scheduled post from the queue? This cannot be undone.'
        else:
            title = 'Dismiss Post Record'
            message = 'Remove this record from the queue? This cannot be undone.'
        answer = QMessageBox.question(self, title, message)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._queue.delete(post.id)
        self.queue_changed.emit()
        self.refresh()


class MissedPostDialog(QDialog):
    """Ask what to do with one post that became due while GaleFling was closed."""

    def __init__(
        self,
        post: ScheduledPost,
        *,
        index: int,
        total: int,
        display_name,
        platform_key=lambda account_id: account_id,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.action = 'leave'
        self.setWindowTitle('Missed Scheduled Post')
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f'<b>Post {index} of {total}</b>'))
        account_names = [display_name(account_id) for account_id in post.account_ids]
        account_keys = [platform_key(account_id) for account_id in post.account_ids]
        layout.addWidget(_target_summary(account_names, account_keys))
        caption = QLabel(post.text)
        caption.setWordWrap(True)
        caption.setStyleSheet(
            f'background: {tokens.SURFACE_INSET}; border: 1px solid {tokens.BORDER}; padding: 9px;'
        )
        layout.addWidget(caption)
        if post.media_paths:
            media = QLabel(f'{len(post.media_paths)} saved media attachment(s)')
            media.setAlignment(Qt.AlignmentFlag.AlignCenter)
            media.setStyleSheet(
                f'background: {tokens.SURFACE_INSET}; color: {tokens.TEXT_SECONDARY}; '
                f'border: 1px dashed {tokens.BORDER}; padding: 12px;'
            )
            layout.addWidget(media)
        due = _local_datetime(post.due_at)
        overdue = datetime.now().astimezone() - due
        minutes = max(1, int(overdue.total_seconds() // 60))
        layout.addWidget(
            QLabel(
                f'<span style="color:{tokens.DANGER}">Was due: '
                f'{_format_due(due)} — {minutes} minutes ago</span>'
            )
        )
        actions = QHBoxLayout()
        for label, action in (('Post Now', 'post'), ('Edit', 'edit'), ('Delete', 'delete')):
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, value=action: self._choose(value))
            actions.addWidget(button)
        layout.addLayout(actions)
        if total - index > 0:
            all_button = QPushButton(f'Post All Remaining ({total - index + 1})')
            all_button.clicked.connect(lambda: self._choose('post_all'))
            layout.addWidget(all_button)

    def _choose(self, action: str) -> None:
        self.action = action
        self.accept()
