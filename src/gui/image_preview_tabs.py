"""Tabbed platform-specific image preview dialog."""

from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.image_processor import (
    ProcessedImage,
    is_animated_gif,
    process_animated_gif,
    process_image,
)
from src.core.logger import get_logger
from src.utils.constants import PLATFORM_SPECS_MAP, PlatformSpecs


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f'{size_bytes} B'
    elif size_bytes < 1024 * 1024:
        return f'{size_bytes / 1024:.1f} KB'
    else:
        return f'{size_bytes / (1024 * 1024):.2f} MB'


class ImagePreviewTab(QWidget):
    """Single platform preview tab with lazy loading."""

    preview_done = pyqtSignal(bool)

    def __init__(
        self,
        image_path: Path,
        specs: PlatformSpecs,
        parent=None,
        cached_path: Path | None = None,
    ):
        super().__init__(parent)
        self._image_path = image_path
        self._specs = specs
        self._loaded = False
        self._result: ProcessedImage | None = None
        self._cached_path = cached_path if cached_path and cached_path.exists() else None
        self._result_path: Path | None = self._cached_path
        self._thread: QThread | None = None
        self._worker: _ImageProcessWorker | None = None

        layout = QVBoxLayout(self)
        self._status_label = QLabel('Click this tab to generate preview...')
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status_label)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        layout.addWidget(self._progress)

        self._preview_label = QLabel()
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setMinimumSize(400, 400)
        layout.addWidget(self._preview_label)

        self._details_label = QLabel()
        self._details_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._details_label)

    def load_preview(self):
        """Generate and display the preview (lazy loaded)."""
        if self._loaded:
            return
        if self._cached_path is not None:
            self._load_cached()
            return

        self._loaded = True
        self._status_label.setText('Processing...')
        self._progress.setValue(0)

        self._thread = QThread(self)
        self._worker = _ImageProcessWorker(self._image_path, self._specs)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._progress.setValue)
        self._worker.finished.connect(self._on_preview_ready)
        self._worker.error.connect(self._on_preview_error)
        self._worker.finished.connect(self._cleanup_worker)
        self._worker.error.connect(self._cleanup_worker)

        self._thread.start()

    def _cleanup_worker(self):
        if self._thread is None:
            return
        self._thread.quit()
        self._thread.wait()
        self._thread.deleteLater()
        self._thread = None
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None

    def _on_preview_ready(self, result: ProcessedImage):
        self._result = result
        self._result_path = result.path

        # Show thumbnail
        pixmap = QPixmap(str(result.path))
        if pixmap.width() > 400 or pixmap.height() > 400:
            pixmap = pixmap.scaled(
                400,
                400,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self._preview_label.setPixmap(pixmap)

        # Status
        orig = f'{result.original_size[0]}x{result.original_size[1]}'
        proc = f'{result.processed_size[0]}x{result.processed_size[1]}'
        orig_size = _format_size(result.original_file_size)
        proc_size = _format_size(result.processed_file_size)

        if result.meets_requirements:
            status = (
                '<span style="color: #4CAF50; font-weight: bold;">\u2713 Meets requirements</span>'
            )
        else:
            status = (
                f'<span style="color: #F44336; font-weight: bold;">\u26a0 {result.warning}</span>'
            )

        self._details_label.setText(
            f'<b>Original:</b> {orig} ({orig_size})<br>'
            f'<b>Will resize to:</b> {proc} ({proc_size})<br>'
            f'<b>Format:</b> {result.format} (quality {result.quality})<br><br>'
            f'{status}'
        )
        self._status_label.setText(f'Preview for {self._specs.platform_name}')
        self.preview_done.emit(True)

    def _on_preview_error(self, message: str):
        self._progress.setValue(0)
        self._status_label.setText(f'Error: {message}')
        get_logger().error(
            'Image preview processing failed',
            extra={
                'platform': self._specs.platform_name,
                'image_path': str(self._image_path),
                'error': message,
            },
        )
        self.preview_done.emit(False)

    def get_processed_path(self) -> Path | None:
        if self._result_path:
            return self._result_path
        return None

    def _load_cached(self):
        if not self._cached_path:
            return
        self._loaded = True
        pixmap = QPixmap(str(self._cached_path))
        if pixmap.width() > 400 or pixmap.height() > 400:
            pixmap = pixmap.scaled(
                400,
                400,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self._preview_label.setPixmap(pixmap)
        proc = f'{pixmap.width()}x{pixmap.height()}'
        proc_size = _format_size(self._cached_path.stat().st_size)
        self._details_label.setText(
            f'<b>Cached:</b> {proc} ({proc_size})<br>'
            f'<b>Format:</b> {self._cached_path.suffix.lstrip(".").upper()}'
        )
        self._status_label.setText(f'Cached preview for {self._specs.platform_name}')
        self._progress.setValue(100)


class ImagePreviewDialog(QDialog):
    """Tabbed dialog showing per-platform image previews."""

    def __init__(
        self,
        image_path: Path,
        platforms: list[str],
        parent=None,
        existing_paths: dict[str, Path | None] | None = None,
    ):
        super().__init__(parent)
        self._image_path = image_path
        self._tabs: dict[str, ImagePreviewTab] = {}
        self._processed_paths: dict[str, Path | None] = {}
        self._had_errors = False
        self._pending_tabs = 0
        self._existing_paths = existing_paths or {}

        self.setWindowTitle('Image Resize Preview')
        self.setMinimumSize(550, 600)

        layout = QVBoxLayout(self)

        # Original file info
        orig_label = QLabel(
            f'<b>Original:</b> {image_path.name}<br>'
            f'<b>Size:</b> {_format_size(image_path.stat().st_size)}'
        )
        layout.addWidget(orig_label)
        layout.addSpacing(10)

        # Tab widget
        self._tab_widget = QTabWidget()
        self._tab_widget.currentChanged.connect(self._on_tab_changed)

        for platform in platforms:
            specs = PLATFORM_SPECS_MAP.get(platform)
            if specs:
                cached_path = self._existing_paths.get(platform)
                tab = ImagePreviewTab(image_path, specs, self, cached_path=cached_path)
                self._tabs[platform] = tab
                self._tab_widget.addTab(tab, specs.platform_name)

        layout.addWidget(self._tab_widget)

        # Info label
        info = QLabel(
            '<i>Images are automatically optimized for each platform. '
            'Aspect ratios are preserved.</i>'
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # OK button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._ok_btn = QPushButton('OK')
        self._ok_btn.setMinimumWidth(100)
        self._ok_btn.setEnabled(False)
        self._ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self._ok_btn)
        cancel_btn = QPushButton('Cancel')
        cancel_btn.setMinimumWidth(100)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        # Load all tabs and enable OK when complete
        self._pending_tabs = 0
        for tab in self._tabs.values():
            if tab.get_processed_path() is None:
                tab.preview_done.connect(self._on_tab_done)
                self._pending_tabs += 1
                tab.load_preview()
            else:
                tab.load_preview()
        if not self._tabs:
            self._ok_btn.setEnabled(True)
        else:
            self._refresh_ok_state()

    def _on_tab_changed(self, index: int):
        widget = self._tab_widget.widget(index)
        if isinstance(widget, ImagePreviewTab):
            widget.load_preview()

    def _on_tab_done(self, _success: bool):
        self._pending_tabs = max(0, self._pending_tabs - 1)
        if not _success:
            self._had_errors = True
        self._refresh_ok_state()

    def _refresh_ok_state(self):
        if self._pending_tabs > 0:
            self._ok_btn.setEnabled(False)
            return
        if self._had_errors:
            self._ok_btn.setEnabled(False)
            return
        all_ready = all(tab.get_processed_path() for tab in self._tabs.values())
        self._ok_btn.setEnabled(all_ready)

    def get_processed_paths(self) -> dict[str, Path | None]:
        """Return {platform: processed_image_path} for all loaded tabs."""
        result = {}
        for platform, tab in self._tabs.items():
            result[platform] = tab.get_processed_path()
        return result

    @property
    def had_errors(self) -> bool:
        return self._had_errors


class _ImageProcessWorker(QObject):
    finished = pyqtSignal(ProcessedImage)
    error = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(self, image_path: Path, specs: PlatformSpecs):
        super().__init__()
        self._image_path = image_path
        self._specs = specs

    def run(self):
        logger = get_logger()
        try:
            logger.info(
                'Preview processing started',
                extra={
                    'platform': self._specs.platform_name,
                    'image_path': str(self._image_path),
                },
            )
            if is_animated_gif(self._image_path):
                result = process_animated_gif(
                    self._image_path, self._specs, progress_cb=self.progress.emit
                )
            else:
                result = process_image(
                    self._image_path, self._specs, progress_cb=self.progress.emit
                )
            logger.info(
                'Preview processing finished',
                extra={
                    'platform': self._specs.platform_name,
                    'processed_path': str(result.path),
                },
            )
            self.finished.emit(result)
        except Exception as exc:
            logger.exception(
                'Preview processing failed',
                extra={
                    'platform': self._specs.platform_name,
                    'image_path': str(self._image_path),
                    'error': str(exc),
                },
            )
            self.error.emit(str(exc))
