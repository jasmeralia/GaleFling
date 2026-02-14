"""Text input widget with character counter and image selection."""

from pathlib import Path

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.utils.constants import BLUESKY_SPECS, TWITTER_SPECS


class PostComposer(QWidget):
    """Text input with live character count and image chooser."""

    text_changed = pyqtSignal(str)
    image_changed = pyqtSignal(object)  # Path or None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image_path: Path | None = None
        self._last_image_dir = ""
        self._init_ui()

    def set_last_image_dir(self, path: str):
        self._last_image_dir = path

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Text label
        text_label = QLabel("Post Text:")
        text_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(text_label)

        # Text edit
        self._text_edit = QTextEdit()
        self._text_edit.setPlaceholderText("What's on your mind?")
        self._text_edit.setMinimumHeight(120)
        self._text_edit.setMaximumHeight(200)
        self._text_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._text_edit)

        # Character counters
        counter_layout = QHBoxLayout()
        self._char_count_label = QLabel("0 characters")
        counter_layout.addWidget(self._char_count_label)
        counter_layout.addStretch()

        self._tw_counter = QLabel()
        self._bs_counter = QLabel()
        counter_layout.addWidget(self._tw_counter)
        counter_layout.addSpacing(15)
        counter_layout.addWidget(self._bs_counter)
        layout.addLayout(counter_layout)

        layout.addSpacing(10)

        # Image section
        img_label = QLabel("Image:")
        img_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(img_label)

        img_row = QHBoxLayout()
        self._choose_btn = QPushButton("Choose Image...")
        self._choose_btn.clicked.connect(self._choose_image)
        img_row.addWidget(self._choose_btn)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.clicked.connect(self._clear_image)
        self._clear_btn.setEnabled(False)
        img_row.addWidget(self._clear_btn)

        img_row.addStretch()
        layout.addLayout(img_row)

        self._image_label = QLabel("No image selected")
        self._image_label.setStyleSheet("color: #666; padding: 4px;")
        layout.addWidget(self._image_label)

        self._update_counters()

    def _on_text_changed(self):
        text = self._text_edit.toPlainText()
        self.text_changed.emit(text)
        self._update_counters()

    def _update_counters(self):
        text = self._text_edit.toPlainText()
        length = len(text)

        self._char_count_label.setText(f"{length} characters")

        tw_max = TWITTER_SPECS.max_text_length
        bs_max = BLUESKY_SPECS.max_text_length

        tw_ok = length <= tw_max
        bs_ok = length <= bs_max

        tw_symbol = "\u2713" if tw_ok else "\u26A0"
        bs_symbol = "\u2713" if bs_ok else "\u26A0"

        tw_color = "#4CAF50" if tw_ok else "#F44336"
        bs_color = "#4CAF50" if bs_ok else "#F44336"

        self._tw_counter.setText(f'{tw_symbol} Twitter: {length}/{tw_max}')
        self._tw_counter.setStyleSheet(f"color: {tw_color}; font-weight: bold;")

        self._bs_counter.setText(f'{bs_symbol} Bluesky: {length}/{bs_max}')
        self._bs_counter.setStyleSheet(f"color: {bs_color}; font-weight: bold;")

    def _choose_image(self):
        start_dir = self._last_image_dir or ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Image", start_dir,
            "Images (*.jpg *.jpeg *.png *.gif *.webp *.bmp);;All Files (*)"
        )
        if path:
            self._image_path = Path(path)
            self._last_image_dir = str(self._image_path.parent)
            self._image_label.setText(f"{self._image_path.name}")
            self._image_label.setStyleSheet("color: #333; padding: 4px;")
            self._clear_btn.setEnabled(True)
            self.image_changed.emit(self._image_path)

    def _clear_image(self):
        self._image_path = None
        self._image_label.setText("No image selected")
        self._image_label.setStyleSheet("color: #666; padding: 4px;")
        self._clear_btn.setEnabled(False)
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
            self._image_label.setText(f"{path.name}")
            self._image_label.setStyleSheet("color: #333; padding: 4px;")
            self._clear_btn.setEnabled(True)
            self.image_changed.emit(path)
        else:
            self._clear_image()
