"""Text input widget with character counter and image selection."""

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

from src.utils.constants import PLATFORM_SPECS_MAP


class PostComposer(QWidget):
    """Text input with live character count and image chooser."""

    text_changed = pyqtSignal(str)
    image_changed = pyqtSignal(object)  # Path or None
    preview_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image_path: Path | None = None
        self._last_image_dir = ''
        self._selected_platforms: set[str] = set()
        self._enabled_platforms: set[str] = set()
        # Maps account_id -> platform_id for counter grouping
        self._account_platform_map: dict[str, str] = {}
        self._counter_labels: dict[str, QLabel] = {}
        self._init_ui()

    def set_last_image_dir(self, path: str):
        self._last_image_dir = path

    def set_account_platform_map(self, mapping: dict[str, str]):
        """Set the mapping from account_id to platform_id."""
        self._account_platform_map = mapping

    def _init_ui(self):
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

        layout.addSpacing(10)

        # Image section
        self._img_label = QLabel('Image:')
        self._img_label.setStyleSheet('font-weight: bold; font-size: 13px; color: palette(text);')
        layout.addWidget(self._img_label)

        img_row = QHBoxLayout()
        self._choose_btn = QPushButton('Choose Image...')
        self._choose_btn.clicked.connect(self._choose_image)
        img_row.addWidget(self._choose_btn)

        self._preview_btn = QPushButton('Preview Images')
        self._preview_btn.setEnabled(False)
        self._preview_btn.clicked.connect(self.preview_requested.emit)
        img_row.addWidget(self._preview_btn)

        self._clear_btn = QPushButton('Clear')
        self._clear_btn.clicked.connect(self._clear_image)
        self._clear_btn.setEnabled(False)
        img_row.addWidget(self._clear_btn)

        img_row.addStretch()
        layout.addLayout(img_row)

        self._image_label = QLabel('No image selected')
        self._set_image_label('No image selected', is_placeholder=True)
        layout.addWidget(self._image_label)

        self._update_counters()

    def set_platform_state(self, selected: list[str], enabled: list[str]):
        self._selected_platforms = set(selected)
        self._enabled_platforms = set(enabled)
        has_targets = bool(self._enabled_platforms and self._selected_platforms)
        self._choose_btn.setEnabled(has_targets)
        self._preview_btn.setEnabled(bool(self._image_path and has_targets))
        self._update_counters()

    def _on_text_changed(self):
        text = self._text_edit.toPlainText()
        self.text_changed.emit(text)
        self._update_counters()

    def _update_counters(self):
        text = self._text_edit.toPlainText()
        length = len(text)

        self._char_count_label.setText(f'{length} characters')

        # Determine which platform types are active (deduplicate by platform_id)
        active_platforms: dict[str, str] = {}  # platform_id -> platform_name
        for account_id in self._selected_platforms & self._enabled_platforms:
            platform_id = self._account_platform_map.get(account_id, account_id)
            specs = PLATFORM_SPECS_MAP.get(platform_id)
            if specs and specs.max_text_length is not None:
                active_platforms[platform_id] = specs.platform_name

        # Remove counters for inactive platforms
        for pid in list(self._counter_labels.keys()):
            if pid not in active_platforms:
                label = self._counter_labels.pop(pid)
                self._counter_layout.removeWidget(label)
                label.deleteLater()

        # Add/update counters for active platforms
        for platform_id, platform_name in sorted(active_platforms.items()):
            specs = PLATFORM_SPECS_MAP[platform_id]
            max_len = specs.max_text_length
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

    def _choose_image(self):
        start_dir = self._last_image_dir or ''
        path, _ = QFileDialog.getOpenFileName(
            self,
            'Choose Image',
            start_dir,
            'Images (*.jpg *.jpeg *.png *.gif *.webp *.bmp);;All Files (*)',
        )
        if path:
            self._image_path = Path(path)
            self._last_image_dir = str(self._image_path.parent)
            self._set_image_label(f'{self._image_path.name}', is_placeholder=False)
            self._clear_btn.setEnabled(True)
            self._preview_btn.setEnabled(bool(self._selected_platforms and self._enabled_platforms))
            self.image_changed.emit(self._image_path)

    def _clear_image(self):
        self._image_path = None
        self._set_image_label('No image selected', is_placeholder=True)
        self._clear_btn.setEnabled(False)
        self._preview_btn.setEnabled(False)
        self.image_changed.emit(None)

    def get_text(self) -> str:
        return self._text_edit.toPlainText()

    def set_text(self, text: str):
        self._text_edit.setPlainText(text)

    def get_image_path(self) -> Path | None:
        return self._image_path

    def set_image_path(self, path: Path | None):
        if path and path.exists():
            self._image_path = path
            self._set_image_label(f'{path.name}', is_placeholder=False)
            self._clear_btn.setEnabled(True)
            self._preview_btn.setEnabled(bool(self._selected_platforms and self._enabled_platforms))
            self.image_changed.emit(path)
        else:
            self._clear_image()

    def clear(self):
        self._text_edit.clear()
        self._clear_image()

    def _set_image_label(self, text: str, is_placeholder: bool):
        self._image_label.setText(text)
        if is_placeholder:
            muted = (
                self.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text).name()
            )
            self._image_label.setStyleSheet(f'color: {muted}; padding: 4px;')
        else:
            self._image_label.setStyleSheet('padding: 4px;')
