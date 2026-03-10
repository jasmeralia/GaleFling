"""Text input widget with character counter and media selection."""

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.utils.constants import (
    IMAGE_EXTENSIONS,
    MAX_MEDIA_ATTACHMENTS,
    PLATFORM_SPECS_MAP,
    VIDEO_EXTENSIONS,
)


class PostComposer(QWidget):
    """Text input with live character count and multi-media chooser."""

    text_changed = pyqtSignal(str)
    media_changed = pyqtSignal(object)  # list[Path]
    # Keep old signal name as alias for backward compatibility in tests/connections
    image_changed = pyqtSignal(object)  # emitted alongside media_changed
    preview_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._media_paths: list[Path] = []
        self._last_image_dir = ''
        self._selected_platforms: set[str] = set()
        self._enabled_platforms: set[str] = set()
        # Maps account_id -> platform_id for counter grouping
        self._account_platform_map: dict[str, str] = {}
        self._counter_labels: dict[str, QLabel] = {}
        self._media_item_rows: list[QWidget] = []
        self._format_restriction_notice: QLabel | None = None
        self._count_restriction_notice: QLabel | None = None
        self._init_ui()

    def set_last_image_dir(self, path: str) -> None:
        self._last_image_dir = path

    def set_account_platform_map(self, mapping: dict[str, str]) -> None:
        """Set the mapping from account_id to platform_id."""
        self._account_platform_map = mapping

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Text label
        self._text_label = QLabel('Post Text:')
        self._text_label.setStyleSheet('font-weight: bold; font-size: 13px; color: palette(text);')
        layout.addWidget(self._text_label)

        # Text edit
        self._text_edit = QTextEdit()
        self._text_edit.setPlaceholderText("What's on your mind?")
        self._text_edit.setMinimumHeight(120)
        self._text_edit.setMaximumHeight(200)
        self._text_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._text_edit)

        # Character counters — dynamic row
        self._counter_layout = QHBoxLayout()
        self._char_count_label = QLabel('0 characters')
        self._counter_layout.addWidget(self._char_count_label)
        self._counter_layout.addStretch()
        layout.addLayout(self._counter_layout)

        # Snapchat text warning (hidden by default)
        self._text_warning = QLabel()
        self._text_warning.setStyleSheet(
            'color: #FF9800; font-size: 12px; font-style: italic; padding: 2px 0;'
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
        self._choose_btn.clicked.connect(self._choose_media)
        img_row.addWidget(self._choose_btn)

        self._preview_btn = QPushButton('Preview Media')
        self._preview_btn.setEnabled(False)
        self._preview_btn.clicked.connect(self.preview_requested.emit)
        img_row.addWidget(self._preview_btn)

        self._clear_btn = QPushButton('Clear All')
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
        # Container for media item rows
        self._media_list_layout = QVBoxLayout()
        self._media_list_layout.setContentsMargins(0, 0, 0, 0)
        self._media_list_layout.setSpacing(2)
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
            'color: #FF9800; font-size: 12px; font-style: italic; padding: 2px 0;'
        )
        self._format_restriction_notice.setWordWrap(True)
        self._format_restriction_notice.setVisible(False)
        notice_col.addWidget(self._format_restriction_notice)

        self._count_restriction_notice = QLabel()
        self._count_restriction_notice.setStyleSheet(
            'color: #FF9800; font-size: 12px; font-style: italic; padding: 2px 0;'
        )
        self._count_restriction_notice.setWordWrap(True)
        self._count_restriction_notice.setVisible(False)
        notice_col.addWidget(self._count_restriction_notice)
        notice_col.addStretch()
        media_body.addLayout(notice_col, 1)

        layout.addLayout(media_body)

        self._update_counters()

    def _set_placeholder_style(self) -> None:
        muted = self.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text).name()
        self._placeholder_label.setStyleSheet(f'color: {muted}; padding: 4px;')

    def set_platform_state(self, selected: list[str], enabled: list[str]) -> None:
        self._selected_platforms = set(selected)
        self._enabled_platforms = set(enabled)
        has_targets = bool(self._enabled_platforms and self._selected_platforms)
        self._update_add_btn_state()
        self._preview_btn.setEnabled(bool(self._media_paths and has_targets))
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
        for pid in list(self._counter_labels.keys()):
            if pid not in active_platforms:
                label = self._counter_labels.pop(pid)
                self._counter_layout.removeWidget(label)
                label.deleteLater()

        # Add/update counters for active platforms
        for platform_id, (platform_name, max_len) in sorted(active_platforms.items()):
            ok = length <= max_len
            symbol = '\u2713' if ok else '\u26a0'
            color = '#4CAF50' if ok else '#F44336'

            if platform_id not in self._counter_labels:
                lbl = QLabel()
                self._counter_labels[platform_id] = lbl
                # Insert before the stretch
                self._counter_layout.insertWidget(self._counter_layout.count() - 1, lbl)

            lbl = self._counter_labels[platform_id]
            lbl.setText(f'{symbol} {platform_name}: {length}/{max_len}')
            lbl.setStyleSheet(f'color: {color}; font-weight: bold;')

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

        self._refresh_media_list()
        self._emit_media_changed()

    def _remove_media(self, index: int):
        """Remove a single media attachment by index."""
        if 0 <= index < len(self._media_paths):
            self._media_paths.pop(index)
        self._refresh_media_list()
        self._emit_media_changed()

    def _clear_all_media(self):
        self._media_paths.clear()
        self._refresh_media_list()
        self._emit_media_changed()

    def _emit_media_changed(self):
        has_targets = bool(self._selected_platforms and self._enabled_platforms)
        self._clear_btn.setEnabled(bool(self._media_paths))
        self._preview_btn.setEnabled(bool(self._media_paths and has_targets))
        self._update_add_btn_state()
        self.media_changed.emit(list(self._media_paths))
        # Emit on legacy signal for backward compat
        self.image_changed.emit(self._media_paths[0] if self._media_paths else None)

    def _refresh_media_list(self):
        """Rebuild the list of media item rows."""
        # Remove existing rows
        for row in self._media_item_rows:
            self._media_list_layout.removeWidget(row)
            row.deleteLater()
        self._media_item_rows.clear()

        self._placeholder_label.setVisible(not self._media_paths)

        for i, path in enumerate(self._media_paths):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(4, 1, 4, 1)

            name_label = QLabel(path.name)
            name_label.setStyleSheet('padding: 2px;')
            row_layout.addWidget(name_label)

            remove_btn = QPushButton('\u2715')
            remove_btn.setFixedSize(22, 22)
            remove_btn.setToolTip('Remove this attachment')
            remove_btn.setStyleSheet('font-size: 12px; padding: 0px;')
            remove_btn.clicked.connect(lambda _checked, idx=i: self._remove_media(idx))
            row_layout.addWidget(remove_btn)

            row_layout.addStretch()
            self._media_list_layout.addWidget(row)
            self._media_item_rows.append(row)

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

    def set_image_path(self, path: Path | None):
        """Set a single media path (backward compat)."""
        if path and path.exists():
            self._media_paths = [path]
        else:
            self._media_paths = []
        self._refresh_media_list()
        self._emit_media_changed()

    def set_media_paths(self, paths: list[Path]):
        """Set multiple media paths."""
        self._media_paths = [p for p in paths if p.exists()][:MAX_MEDIA_ATTACHMENTS]
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
