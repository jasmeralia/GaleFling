"""Text input widget with character counter and media selection."""

from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.core.logger import get_logger
from src.gui.emoji_picker import EmojiPickerButton
from src.gui.icon_utils import tinted_icon
from src.utils import tokens
from src.utils.constants import (
    IMAGE_EXTENSIONS,
    MAX_MEDIA_ATTACHMENTS,
    PLATFORM_SPECS_MAP,
    VIDEO_EXTENSIONS,
)

_UI_ICONS_DIR = Path(__file__).resolve().parent.parent / 'resources' / 'icons' / 'ui'
_MEDIA_CHIP_SIZE = 74
_COUNTER_RING_SIZE = 20


def _icon(name: str) -> QIcon:
    return tinted_icon(_UI_ICONS_DIR / name, tokens.TEXT_SECONDARY)


def _pil_to_pixmap(img) -> QPixmap:
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    data = img.tobytes('raw', 'RGBA')
    qimg = QImage(
        data,
        img.width,
        img.height,
        img.width * 4,
        QImage.Format.Format_RGBA8888,
    )
    return QPixmap.fromImage(qimg.copy())


def _load_chip_pixmap(path: Path) -> QPixmap | None:
    suffix = path.suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        return None
    try:
        from PIL import Image

        with Image.open(path) as img:
            img.thumbnail((_MEDIA_CHIP_SIZE, _MEDIA_CHIP_SIZE))
            return _pil_to_pixmap(img)
    except Exception:
        return None


class _CounterRing(QWidget):
    """Compact circular progress indicator for platform character limits."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(_COUNTER_RING_SIZE, _COUNTER_RING_SIZE)
        self._current = 0
        self._maximum = 1
        self._over_limit = False

    def set_values(self, current: int, maximum: int, over_limit: bool) -> None:
        self._current = current
        self._maximum = max(maximum, 1)
        self._over_limit = over_limit
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(2, 2, -2, -2)
        start_angle = 90 * 16
        full_span = -360 * 16

        track_pen = QPen(QColor(tokens.BORDER))
        track_pen.setWidth(2)
        painter.setPen(track_pen)
        painter.drawArc(rect, start_angle, full_span)

        ratio = min(self._current / self._maximum, 1.0)
        if ratio > 0:
            fill_color = tokens.DANGER if self._over_limit else tokens.SUCCESS
            fill_pen = QPen(QColor(fill_color))
            fill_pen.setWidth(2)
            painter.setPen(fill_pen)
            painter.drawArc(rect, start_angle, int(full_span * ratio))

        painter.end()


class _CounterWidget(QWidget):
    """Per-platform character counter: ring progress plus numeric label."""

    def __init__(self, platform_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._platform_name = platform_name
        self._current_length = 0
        self._max_length = 0
        self._is_over_limit = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(4)

        self._ring = _CounterRing()
        layout.addWidget(self._ring)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(0)

        self._name_label = QLabel(platform_name)
        self._name_label.setStyleSheet(
            f'color: {tokens.TEXT_SECONDARY}; font-size: 11px; font-weight: 600;'
        )

        self._count_label = QLabel()
        self._count_label.setStyleSheet(
            f'color: {tokens.TEXT}; font-size: 11px; font-weight: bold;'
        )

        text_col.addWidget(self._name_label)
        text_col.addWidget(self._count_label)
        layout.addLayout(text_col)

        self.setToolTip(f'{platform_name} character limit')

    @property
    def current_length(self) -> int:
        return self._current_length

    @property
    def max_length(self) -> int:
        return self._max_length

    @property
    def is_over_limit(self) -> bool:
        return self._is_over_limit

    def update_count(self, current: int, maximum: int) -> None:
        self._current_length = current
        self._max_length = maximum
        self._is_over_limit = current > maximum
        self._count_label.setText(f'{current}/{maximum}')
        self._ring.set_values(current, maximum, self._is_over_limit)


class _MediaChip(QWidget):
    """Square thumbnail chip for one media attachment."""

    def __init__(
        self,
        path: Path,
        index: int,
        on_remove: Callable[[int], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._path = path
        self._index = index

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(2)

        is_video = path.suffix.lower() in VIDEO_EXTENSIONS
        badge_text = 'VID' if is_video else 'IMG'

        thumb = QWidget()
        thumb.setFixedSize(_MEDIA_CHIP_SIZE, _MEDIA_CHIP_SIZE)
        thumb.setStyleSheet(
            f'background-color: {tokens.SURFACE_RAISED}; border: 1px solid {tokens.BORDER};'
        )

        thumb_label = QLabel(thumb)
        thumb_label.setGeometry(0, 0, _MEDIA_CHIP_SIZE, _MEDIA_CHIP_SIZE)
        thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        pixmap = None if is_video else _load_chip_pixmap(path)
        if pixmap is not None and not pixmap.isNull():
            thumb_label.setPixmap(
                pixmap.scaled(
                    _MEDIA_CHIP_SIZE,
                    _MEDIA_CHIP_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        badge = QLabel(badge_text, thumb)
        badge.setStyleSheet(
            f'background-color: {tokens.SURFACE_INSET}; color: {tokens.TEXT_MUTED}; '
            'font-size: 9px; padding: 1px 3px;'
        )
        badge.adjustSize()
        badge.move(2, 2)

        remove_btn = QToolButton(thumb)
        remove_btn.setIcon(_icon('close.svg'))
        remove_btn.setIconSize(QSize(12, 12))
        remove_btn.setFixedSize(18, 18)
        remove_btn.setToolTip('Remove this attachment')
        remove_btn.setStyleSheet(
            f'background-color: {tokens.SURFACE_INSET}; border: none; border-radius: 2px;'
        )
        remove_btn.move(_MEDIA_CHIP_SIZE - 20, 2)
        remove_btn.clicked.connect(lambda _checked, idx=index: on_remove(idx))

        layout.addWidget(thumb)

        name_label = QLabel()
        name_label.setFixedWidth(_MEDIA_CHIP_SIZE)
        elided = name_label.fontMetrics().elidedText(
            path.name,
            Qt.TextElideMode.ElideMiddle,
            _MEDIA_CHIP_SIZE,
        )
        name_label.setText(elided)
        name_label.setStyleSheet(f'color: {tokens.TEXT_SECONDARY}; font-size: 10px;')
        name_label.setToolTip(path.name)
        layout.addWidget(name_label)


class PostComposer(QWidget):
    """Text input with live character count and multi-media chooser."""

    text_changed = pyqtSignal(str)
    media_changed = pyqtSignal(object)  # list[Path]
    # Keep old signal name as alias for backward compatibility in tests/connections
    image_changed = pyqtSignal(object)  # emitted alongside media_changed
    preview_requested = pyqtSignal()
    recent_emoji_changed = pyqtSignal(list)
    snapchat_landscape_mode_changed = pyqtSignal(str)
    snapchat_multi_image_mode_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._media_paths: list[Path] = []
        self._last_image_dir = ''
        self._selected_platforms: set[str] = set()
        self._enabled_platforms: set[str] = set()
        # Maps account_id -> platform_id for counter grouping
        self._account_platform_map: dict[str, str] = {}
        self._counter_widgets: dict[str, _CounterWidget] = {}
        self._media_item_rows: list[QWidget] = []
        self._format_restriction_notice: QLabel | None = None
        self._count_restriction_notice: QLabel | None = None
        self._snapchat_landscape_row: QWidget | None = None
        self._snapchat_landscape_combo: QComboBox | None = None
        self._snapchat_multi_image_row: QWidget | None = None
        self._snapchat_multi_image_combo: QComboBox | None = None
        self._video_landscape_cache: dict[Path, bool] = {}
        self._image_landscape_cache: dict[Path, bool] = {}
        self._init_ui()

    def set_last_image_dir(self, path: str) -> None:
        self._last_image_dir = path

    def set_recent_emoji(self, recent: list[str]) -> None:
        self._emoji_button.set_recent_emoji(recent)

    def set_account_platform_map(self, mapping: dict[str, str]) -> None:
        """Set the mapping from account_id to platform_id."""
        self._account_platform_map = mapping

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setMinimumHeight(420)

        # Text label
        text_label_row = QHBoxLayout()
        self._text_label = QLabel('Post Text:')
        self._text_label.setStyleSheet('font-weight: bold; font-size: 13px; color: palette(text);')
        text_label_row.addWidget(self._text_label)
        text_label_row.addStretch()
        layout.addLayout(text_label_row)

        # Text edit
        self._text_edit = QTextEdit()
        self._text_edit.setPlaceholderText("What's on your mind?")
        self._text_edit.setStyleSheet('font-size: 15pt;')
        self._text_edit.setMinimumHeight(120)
        self._text_edit.setMaximumHeight(200)
        self._text_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._text_edit)

        # Emoji picker — anchored below and to the right of the text box
        emoji_row = QHBoxLayout()
        emoji_row.addStretch()
        self._emoji_button = EmojiPickerButton()
        self._emoji_button.setToolTip('Insert emoji')
        self._emoji_button.clicked.connect(self._on_emoji_picker_opened)
        self._emoji_button.emoji_selected.connect(self._on_emoji_selected)
        emoji_row.addWidget(self._emoji_button)
        layout.addLayout(emoji_row)

        # Character counters — dynamic row
        self._counter_layout = QHBoxLayout()
        self._char_count_label = QLabel('0 characters')
        self._counter_layout.addWidget(self._char_count_label)
        self._counter_layout.addStretch()
        layout.addLayout(self._counter_layout)

        # Snapchat text warning (hidden by default)
        self._text_warning = QLabel()
        self._text_warning.setStyleSheet(
            f'color: {tokens.WARNING}; font-size: 12px; font-style: italic; padding: 2px 0;'
        )
        self._text_warning.setWordWrap(True)
        self._text_warning.setVisible(False)
        layout.addWidget(self._text_warning)

        layout.addSpacing(10)

        # Media section
        self._img_label = QLabel('Media:')
        self._img_label.setStyleSheet('font-weight: bold; font-size: 13px; color: palette(text);')
        layout.addWidget(self._img_label)

        img_row = QHBoxLayout()
        self._choose_btn = QPushButton('Add Media...')
        self._choose_btn.setToolTip('Attach images or a video to this post')
        self._choose_btn.clicked.connect(self._choose_media)
        img_row.addWidget(self._choose_btn)

        self._preview_btn = QPushButton('Preview Media')
        self._preview_btn.setToolTip('Preview how the attached media will look on each platform')
        self._preview_btn.setEnabled(False)
        self._preview_btn.clicked.connect(self.preview_requested.emit)
        img_row.addWidget(self._preview_btn)

        self._clear_btn = QPushButton('Clear All')
        self._clear_btn.setToolTip('Remove all attached media')
        self._clear_btn.clicked.connect(self._clear_all_media)
        self._clear_btn.setEnabled(False)
        img_row.addWidget(self._clear_btn)

        img_row.addStretch()
        layout.addLayout(img_row)

        media_body = QHBoxLayout()
        media_body.setSpacing(12)

        media_list_col = QVBoxLayout()
        media_list_col.setContentsMargins(0, 0, 0, 0)
        media_list_col.setSpacing(2)
        # Container for media thumbnail chips
        self._media_list_layout = QHBoxLayout()
        self._media_list_layout.setContentsMargins(0, 0, 0, 0)
        self._media_list_layout.setSpacing(6)
        media_list_col.addLayout(self._media_list_layout)

        # Placeholder label
        self._placeholder_label = QLabel('No media selected')
        self._set_placeholder_style()
        media_list_col.addWidget(self._placeholder_label)
        media_body.addLayout(media_list_col, 1)

        notice_col = QVBoxLayout()
        notice_col.setContentsMargins(0, 0, 0, 0)
        notice_col.setSpacing(2)
        self._format_restriction_notice = QLabel()
        self._format_restriction_notice.setStyleSheet(
            f'color: {tokens.WARNING}; font-size: 12px; font-style: italic; padding: 2px 0;'
        )
        self._format_restriction_notice.setWordWrap(True)
        self._format_restriction_notice.setVisible(False)
        notice_col.addWidget(self._format_restriction_notice)

        self._count_restriction_notice = QLabel()
        self._count_restriction_notice.setStyleSheet(
            f'color: {tokens.WARNING}; font-size: 12px; font-style: italic; padding: 2px 0;'
        )
        self._count_restriction_notice.setWordWrap(True)
        self._count_restriction_notice.setVisible(False)
        notice_col.addWidget(self._count_restriction_notice)

        self._snapchat_multi_image_row = QWidget()
        snapchat_multi_layout = QHBoxLayout(self._snapchat_multi_image_row)
        snapchat_multi_layout.setContentsMargins(0, 0, 0, 0)
        snapchat_multi_layout.setSpacing(6)
        snapchat_multi_layout.addWidget(QLabel('Snapchat multi-image handling:'))
        self._snapchat_multi_image_combo = QComboBox()
        self._snapchat_multi_image_combo.setToolTip(
            'Snapchat accepts only one image per post — choose how to handle multiple'
        )
        self._snapchat_multi_image_combo.addItem('Use first image only', 'first')
        self._snapchat_multi_image_combo.addItem('Create slideshow video', 'slideshow')
        self._snapchat_multi_image_combo.currentIndexChanged.connect(
            self._on_snapchat_multi_image_mode_changed
        )
        snapchat_multi_layout.addWidget(self._snapchat_multi_image_combo)
        snapchat_multi_layout.addStretch()
        self._snapchat_multi_image_row.setVisible(False)
        notice_col.addWidget(self._snapchat_multi_image_row)

        self._snapchat_landscape_row = QWidget()
        snapchat_mode_layout = QHBoxLayout(self._snapchat_landscape_row)
        snapchat_mode_layout.setContentsMargins(0, 0, 0, 0)
        snapchat_mode_layout.setSpacing(6)
        snapchat_mode_layout.addWidget(QLabel('Snapchat landscape handling:'))
        self._snapchat_landscape_combo = QComboBox()
        self._snapchat_landscape_combo.setToolTip(
            'Snapchat expects vertical media — choose how to handle a landscape attachment'
        )
        self._snapchat_landscape_combo.addItem('Crop to vertical', 'crop')
        self._snapchat_landscape_combo.addItem('Rotate to vertical', 'rotate')
        self._snapchat_landscape_combo.currentIndexChanged.connect(
            self._on_snapchat_landscape_mode_changed
        )
        snapchat_mode_layout.addWidget(self._snapchat_landscape_combo)
        snapchat_mode_layout.addStretch()
        self._snapchat_landscape_row.setVisible(False)
        notice_col.addWidget(self._snapchat_landscape_row)

        notice_col.addStretch()
        media_body.addLayout(notice_col, 1)

        layout.addLayout(media_body)

        self._update_counters()

    def _set_placeholder_style(self) -> None:
        self._placeholder_label.setStyleSheet(f'color: {tokens.TEXT_SECONDARY}; padding: 4px;')

    def set_platform_state(self, selected: list[str], enabled: list[str]) -> None:
        self._selected_platforms = set(selected)
        self._enabled_platforms = set(enabled)
        has_targets = bool(self._enabled_platforms and self._selected_platforms)
        self._update_add_btn_state()
        self._preview_btn.setEnabled(bool(self._media_paths and has_targets))
        self._update_snapchat_landscape_mode_visibility()
        self._update_counters()

    def _update_add_btn_state(self) -> None:
        """Enable/disable the Add Media button based on current state."""
        has_targets = bool(self._enabled_platforms and self._selected_platforms)
        has_video = any(p.suffix.lower() in VIDEO_EXTENSIONS for p in self._media_paths)
        at_capacity = len(self._media_paths) >= MAX_MEDIA_ATTACHMENTS
        # If a video is attached, no more attachments allowed (video = 1 attachment)
        at_capacity = at_capacity or has_video
        self._choose_btn.setEnabled(has_targets and not at_capacity)

    def _on_text_changed(self) -> None:
        text = self._text_edit.toPlainText()
        self.text_changed.emit(text)
        self._update_counters()

    def _on_emoji_picker_opened(self) -> None:
        get_logger().info('User selected Post Composer > Open Emoji Picker')

    def _on_emoji_selected(self, emoji_char: str) -> None:
        self._text_edit.insertPlainText(emoji_char)
        self._text_edit.setFocus()
        self.recent_emoji_changed.emit(self._emoji_button.get_recent_emoji())
        get_logger().info('User selected Post Composer > Insert Emoji')

    def _update_counters(self) -> None:
        text = self._text_edit.toPlainText()
        length = len(text)

        self._char_count_label.setText(f'{length} characters')

        # Determine which platform types are active (deduplicate by platform_id)
        active_platforms: dict[str, tuple[str, int]] = {}  # platform_id -> (platform_name, max_len)
        has_no_text_platform = False
        no_text_names: list[str] = []
        no_text_with_media_names: list[str] = []
        for account_id in self._selected_platforms & self._enabled_platforms:
            platform_id = self._account_platform_map.get(account_id, account_id)
            specs = PLATFORM_SPECS_MAP.get(platform_id)
            if not specs:
                continue
            if not specs.supports_text:
                has_no_text_platform = True
                if specs.platform_name not in no_text_names:
                    no_text_names.append(specs.platform_name)
            elif self._media_paths and not specs.supports_text_with_media:
                if specs.platform_name not in no_text_with_media_names:
                    no_text_with_media_names.append(specs.platform_name)
            if specs.max_text_length is not None:
                active_platforms[platform_id] = (specs.platform_name, specs.max_text_length)

        # Show text warning for platforms that ignore text entirely or with media attached.
        if length > 0 and (has_no_text_platform or no_text_with_media_names):
            messages = []
            if no_text_names:
                names = ', '.join(no_text_names)
                verb = 'does' if len(no_text_names) == 1 else 'do'
                messages.append(
                    f'{names} {verb} not support text in posts \u2014 '
                    'your text will not be included on that platform.'
                )
            if no_text_with_media_names:
                names = ', '.join(no_text_with_media_names)
                verb = 'does' if len(no_text_with_media_names) == 1 else 'do'
                messages.append(
                    f'{names} {verb} not support text when media is attached \u2014 '
                    'your text will not be included on that platform.'
                )
            self._text_warning.setText(f'\u26a0 {" ".join(messages)}')
            self._text_warning.setVisible(True)
        else:
            self._text_warning.setVisible(False)

        # Remove counters for inactive platforms
        for pid in list(self._counter_widgets.keys()):
            if pid not in active_platforms:
                widget = self._counter_widgets.pop(pid)
                self._counter_layout.removeWidget(widget)
                widget.deleteLater()

        # Add/update counters for active platforms
        for platform_id, (platform_name, max_len) in sorted(active_platforms.items()):
            if platform_id not in self._counter_widgets:
                counter = _CounterWidget(platform_name)
                self._counter_widgets[platform_id] = counter
                # Insert before the stretch
                self._counter_layout.insertWidget(self._counter_layout.count() - 1, counter)

            counter = self._counter_widgets[platform_id]
            counter.update_count(length, max_len)

    def _choose_media(self):
        start_dir = self._last_image_dir or ''
        has_video = any(p.suffix.lower() in VIDEO_EXTENSIONS for p in self._media_paths)
        remaining = MAX_MEDIA_ATTACHMENTS - len(self._media_paths)

        if has_video or remaining <= 0:
            return

        # If we already have images, only allow images (no mixing with video)
        if self._media_paths:
            img_exts = ' '.join(f'*{ext}' for ext in sorted(IMAGE_EXTENSIONS))
            filter_str = f'Images ({img_exts});;All Files (*)'
        else:
            img_exts = ' '.join(f'*{ext}' for ext in sorted(IMAGE_EXTENSIONS))
            vid_exts = ' '.join(f'*{ext}' for ext in sorted(VIDEO_EXTENSIONS))
            filter_str = (
                f'Media ({img_exts} {vid_exts});;Images ({img_exts});;'
                f'Videos ({vid_exts});;All Files (*)'
            )

        paths, _ = QFileDialog.getOpenFileNames(
            self,
            'Add Media',
            start_dir,
            filter_str,
        )
        if not paths:
            return

        for p_str in paths:
            p = Path(p_str)
            if p in self._media_paths:
                continue
            is_video = p.suffix.lower() in VIDEO_EXTENSIONS
            # Video: only allow as sole attachment
            if is_video and self._media_paths:
                continue
            # If adding a video, only add 1
            if is_video:
                self._media_paths = [p]
                break
            if len(self._media_paths) >= MAX_MEDIA_ATTACHMENTS:
                break
            self._media_paths.append(p)

        if self._media_paths:
            self._last_image_dir = str(self._media_paths[-1].parent)
        self._video_landscape_cache.clear()
        self._image_landscape_cache.clear()

        self._refresh_media_list()
        self._emit_media_changed()

    def _remove_media(self, index: int):
        """Remove a single media attachment by index."""
        if 0 <= index < len(self._media_paths):
            self._media_paths.pop(index)
        self._video_landscape_cache.clear()
        self._image_landscape_cache.clear()
        self._refresh_media_list()
        self._emit_media_changed()

    def _clear_all_media(self):
        self._media_paths.clear()
        self._video_landscape_cache.clear()
        self._image_landscape_cache.clear()
        self._refresh_media_list()
        self._emit_media_changed()

    def _emit_media_changed(self):
        has_targets = bool(self._selected_platforms and self._enabled_platforms)
        self._clear_btn.setEnabled(bool(self._media_paths))
        self._preview_btn.setEnabled(bool(self._media_paths and has_targets))
        self._update_add_btn_state()
        self._update_snapchat_landscape_mode_visibility()
        self.media_changed.emit(list(self._media_paths))
        # Emit on legacy signal for backward compat
        self.image_changed.emit(self._media_paths[0] if self._media_paths else None)

    def _refresh_media_list(self):
        """Rebuild the list of media thumbnail chips."""
        # Remove existing chips
        for row in self._media_item_rows:
            self._media_list_layout.removeWidget(row)
            row.deleteLater()
        self._media_item_rows.clear()

        self._placeholder_label.setVisible(not self._media_paths)

        for i, path in enumerate(self._media_paths):
            chip = _MediaChip(path, i, self._remove_media)
            self._media_list_layout.addWidget(chip)
            self._media_item_rows.append(chip)

    def get_text(self) -> str:
        return self._text_edit.toPlainText()

    def set_text(self, text: str):
        self._text_edit.setPlainText(text)

    def get_image_path(self) -> Path | None:
        """Return the first media path (backward compat)."""
        return self._media_paths[0] if self._media_paths else None

    def get_media_paths(self) -> list[Path]:
        """Return all attached media paths."""
        return list(self._media_paths)

    def get_snapchat_landscape_mode(self) -> str:
        if self._snapchat_landscape_combo is None:
            return 'crop'
        mode = self._snapchat_landscape_combo.currentData()
        if isinstance(mode, str) and mode in {'crop', 'rotate'}:
            return mode
        return 'crop'

    def set_snapchat_landscape_mode(self, mode: str) -> None:
        if self._snapchat_landscape_combo is None:
            return
        normalized = mode if mode in {'crop', 'rotate'} else 'crop'
        index = self._snapchat_landscape_combo.findData(normalized)
        if index >= 0:
            self._snapchat_landscape_combo.setCurrentIndex(index)

    def get_snapchat_multi_image_mode(self) -> str:
        if self._snapchat_multi_image_combo is None:
            return 'first'
        mode = self._snapchat_multi_image_combo.currentData()
        if isinstance(mode, str) and mode in {'first', 'slideshow'}:
            return mode
        return 'first'

    def set_snapchat_multi_image_mode(self, mode: str) -> None:
        if self._snapchat_multi_image_combo is None:
            return
        normalized = mode if mode in {'first', 'slideshow'} else 'first'
        index = self._snapchat_multi_image_combo.findData(normalized)
        if index >= 0:
            self._snapchat_multi_image_combo.setCurrentIndex(index)

    def set_image_path(self, path: Path | None):
        """Set a single media path (backward compat)."""
        if path and path.exists():
            self._media_paths = [path]
        else:
            self._media_paths = []
        self._video_landscape_cache.clear()
        self._image_landscape_cache.clear()
        self._refresh_media_list()
        self._emit_media_changed()

    def set_media_paths(self, paths: list[Path]):
        """Set multiple media paths."""
        self._media_paths = [p for p in paths if p.exists()][:MAX_MEDIA_ATTACHMENTS]
        self._video_landscape_cache.clear()
        self._image_landscape_cache.clear()
        self._refresh_media_list()
        self._emit_media_changed()

    def set_format_restriction_notice(self, text: str = ''):
        if not self._format_restriction_notice:
            return
        self._format_restriction_notice.setText(text)
        self._format_restriction_notice.setVisible(bool(text))

    def set_count_restriction_notice(self, text: str = ''):
        if not self._count_restriction_notice:
            return
        self._count_restriction_notice.setText(text)
        self._count_restriction_notice.setVisible(bool(text))

    def clear(self):
        self._text_edit.clear()
        self._clear_all_media()

    # Kept for backward compat with draft save/restore
    def _clear_image(self):
        self._clear_all_media()

    def _is_snapchat_selected(self) -> bool:
        for account_id in self._selected_platforms & self._enabled_platforms:
            platform_id = self._account_platform_map.get(account_id, account_id)
            if platform_id == 'snapchat':
                return True
        return False

    def _is_landscape_video(self, video_path: Path) -> bool:
        if video_path in self._video_landscape_cache:
            return self._video_landscape_cache[video_path]
        try:
            from src.core.video_processor import get_video_info

            info = get_video_info(video_path)
            landscape = info.width > info.height
        except Exception:
            landscape = False
        self._video_landscape_cache[video_path] = landscape
        return landscape

    def _is_landscape_image(self, image_path: Path) -> bool:
        if image_path in self._image_landscape_cache:
            return self._image_landscape_cache[image_path]
        try:
            from PIL import Image

            with Image.open(image_path) as img:
                landscape = img.width > img.height
        except Exception:
            landscape = False
        self._image_landscape_cache[image_path] = landscape
        return landscape

    def _update_snapchat_landscape_mode_visibility(self) -> None:
        if self._snapchat_landscape_row is None:
            return
        if self._snapchat_multi_image_row is None:
            return

        self._snapchat_landscape_row.setVisible(False)
        self._snapchat_multi_image_row.setVisible(False)

        if not self._media_paths:
            return

        if not self._is_snapchat_selected():
            return

        has_video = any(p.suffix.lower() in VIDEO_EXTENSIONS for p in self._media_paths)
        if has_video:
            if len(self._media_paths) != 1:
                return
            media_path = self._media_paths[0]
            if media_path.suffix.lower() not in VIDEO_EXTENSIONS:
                return
            self._snapchat_landscape_row.setVisible(self._is_landscape_video(media_path))
            return

        if len(self._media_paths) > 1:
            self._snapchat_multi_image_row.setVisible(True)
            self._snapchat_landscape_row.setVisible(True)
            return

        media_path = self._media_paths[0]
        if media_path.suffix.lower() in VIDEO_EXTENSIONS:
            self._snapchat_landscape_row.setVisible(False)
            return

        self._snapchat_landscape_row.setVisible(True)

    def _on_snapchat_landscape_mode_changed(self, _index: int) -> None:
        self.snapchat_landscape_mode_changed.emit(self.get_snapchat_landscape_mode())

    def _on_snapchat_multi_image_mode_changed(self, _index: int) -> None:
        self._update_snapchat_landscape_mode_visibility()
        self.snapchat_multi_image_mode_changed.emit(self.get_snapchat_multi_image_mode())
