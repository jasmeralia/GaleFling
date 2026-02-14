"""Tabbed platform-specific image preview dialog."""

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.image_processor import ProcessedImage, process_image
from src.utils.constants import BLUESKY_SPECS, TWITTER_SPECS, PlatformSpecs


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


class ImagePreviewTab(QWidget):
    """Single platform preview tab with lazy loading."""

    def __init__(self, image_path: Path, specs: PlatformSpecs, parent=None):
        super().__init__(parent)
        self._image_path = image_path
        self._specs = specs
        self._loaded = False
        self._result: ProcessedImage | None = None

        layout = QVBoxLayout(self)
        self._status_label = QLabel("Click this tab to generate preview...")
        self._status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._status_label)

        self._preview_label = QLabel()
        self._preview_label.setAlignment(Qt.AlignCenter)
        self._preview_label.setMinimumSize(400, 400)
        layout.addWidget(self._preview_label)

        self._details_label = QLabel()
        self._details_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._details_label)

    def load_preview(self):
        """Generate and display the preview (lazy loaded)."""
        if self._loaded:
            return

        self._loaded = True
        self._status_label.setText("Processing...")

        try:
            self._result = process_image(self._image_path, self._specs)
            result = self._result

            # Show thumbnail
            pixmap = QPixmap(str(result.path))
            if pixmap.width() > 400 or pixmap.height() > 400:
                pixmap = pixmap.scaled(400, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._preview_label.setPixmap(pixmap)

            # Status
            orig = f"{result.original_size[0]}x{result.original_size[1]}"
            proc = f"{result.processed_size[0]}x{result.processed_size[1]}"
            orig_size = _format_size(result.original_file_size)
            proc_size = _format_size(result.processed_file_size)

            if result.meets_requirements:
                status = '<span style="color: #4CAF50; font-weight: bold;">\u2713 Meets requirements</span>'
            else:
                status = f'<span style="color: #F44336; font-weight: bold;">\u26A0 {result.warning}</span>'

            self._details_label.setText(
                f"<b>Original:</b> {orig} ({orig_size})<br>"
                f"<b>Will resize to:</b> {proc} ({proc_size})<br>"
                f"<b>Format:</b> {result.format} (quality {result.quality})<br><br>"
                f"{status}"
            )
            self._status_label.setText(f"Preview for {self._specs.platform_name}")

        except Exception as e:
            self._status_label.setText(f"Error: {e}")

    def get_processed_path(self) -> Path | None:
        if self._result:
            return self._result.path
        return None


class ImagePreviewDialog(QDialog):
    """Tabbed dialog showing per-platform image previews."""

    def __init__(self, image_path: Path, platforms: list[str], parent=None):
        super().__init__(parent)
        self._image_path = image_path
        self._tabs: dict[str, ImagePreviewTab] = {}
        self._processed_paths: dict[str, Path | None] = {}

        self.setWindowTitle("Image Resize Preview")
        self.setMinimumSize(550, 600)

        layout = QVBoxLayout(self)

        # Original file info
        orig_label = QLabel(
            f"<b>Original:</b> {image_path.name}<br>"
            f"<b>Size:</b> {_format_size(image_path.stat().st_size)}"
        )
        layout.addWidget(orig_label)
        layout.addSpacing(10)

        # Tab widget
        self._tab_widget = QTabWidget()
        self._tab_widget.currentChanged.connect(self._on_tab_changed)

        specs_map = {
            'twitter': TWITTER_SPECS,
            'bluesky': BLUESKY_SPECS,
        }

        for platform in platforms:
            specs = specs_map.get(platform)
            if specs:
                tab = ImagePreviewTab(image_path, specs, self)
                self._tabs[platform] = tab
                self._tab_widget.addTab(tab, specs.platform_name)

        layout.addWidget(self._tab_widget)

        # Info label
        info = QLabel(
            "<i>Images are automatically optimized for each platform. "
            "Aspect ratios are preserved.</i>"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # OK button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.setMinimumWidth(100)
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

        # Load first tab
        if self._tab_widget.count() > 0:
            self._on_tab_changed(0)

    def _on_tab_changed(self, index: int):
        widget = self._tab_widget.widget(index)
        if isinstance(widget, ImagePreviewTab):
            widget.load_preview()

    def get_processed_paths(self) -> dict[str, Path | None]:
        """Return {platform: processed_image_path} for all loaded tabs."""
        result = {}
        for platform, tab in self._tabs.items():
            result[platform] = tab.get_processed_path()
        return result
