"""Tabbed platform-specific media preview dialog (images and videos)."""

from pathlib import Path
from types import ModuleType

from PyQt6.QtCore import QObject, Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSlider,
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
from src.utils.constants import PLATFORM_SPECS_MAP, VIDEO_EXTENSIONS, PlatformSpecs

QtMultimediaModule: ModuleType | None
QtMultimediaWidgetsModule: ModuleType | None
try:
    from PyQt6 import QtMultimedia as QtMultimediaModule
    from PyQt6 import QtMultimediaWidgets as QtMultimediaWidgetsModule
except Exception:  # pragma: no cover - runtime fallback when multimedia isn't available
    QtMultimediaModule = None
    QtMultimediaWidgetsModule = None


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f'{size_bytes} B'
    elif size_bytes < 1024 * 1024:
        return f'{size_bytes / 1024:.1f} KB'
    else:
        return f'{size_bytes / (1024 * 1024):.2f} MB'


def _format_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f'{h}:{m:02d}:{s:02d}'
    return f'{m}:{s:02d}'


def _is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


def _describe_video_changes(original, processed) -> list[str]:
    """Return human-readable change summaries for a processed video."""
    changes: list[str] = []

    if abs(processed.duration_seconds - original.duration_seconds) >= 0.05:
        if processed.duration_seconds < original.duration_seconds:
            changes.append(
                f'Length clipped: {_format_duration(original.duration_seconds)} '
                f'-> {_format_duration(processed.duration_seconds)}.'
            )
        else:
            changes.append(
                f'Length increased: {_format_duration(original.duration_seconds)} '
                f'-> {_format_duration(processed.duration_seconds)}.'
            )
    else:
        changes.append(f'Length unchanged: {_format_duration(processed.duration_seconds)}.')

    if (original.width, original.height) != (processed.width, processed.height):
        changes.append(
            f'Resolution changed: {original.width}x{original.height} '
            f'-> {processed.width}x{processed.height}.'
        )
    else:
        changes.append(f'Resolution unchanged: {processed.width}x{processed.height}.')

    size_delta = processed.file_size - original.file_size
    if abs(size_delta) >= 1024 and original.file_size > 0:
        delta_pct = (abs(size_delta) / original.file_size) * 100
        if size_delta < 0:
            changes.append(
                f'File size reduced: {_format_size(original.file_size)} '
                f'-> {_format_size(processed.file_size)} ({delta_pct:.1f}% smaller).'
            )
        else:
            changes.append(
                f'File size increased: {_format_size(original.file_size)} '
                f'-> {_format_size(processed.file_size)} ({delta_pct:.1f}% larger).'
            )
    else:
        changes.append(f'File size unchanged: {_format_size(processed.file_size)}.')

    original_format = (original.format_name or '').upper()
    processed_format = (processed.format_name or '').upper()
    if original_format and processed_format and original_format != processed_format:
        changes.append(f'Format changed: {original_format} -> {processed_format}.')
    else:
        shown_format = processed_format or 'UNKNOWN'
        changes.append(f'Format unchanged: {shown_format}.')

    return changes


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
        self._source_pixmap: QPixmap | None = None

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
        self._preview_label.setMinimumSize(220, 220)
        self._preview_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
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
        self._set_preview_pixmap(QPixmap(str(result.path)))

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
        self._set_preview_pixmap(pixmap)
        proc = f'{pixmap.width()}x{pixmap.height()}'
        proc_size = _format_size(self._cached_path.stat().st_size)
        self._details_label.setText(
            f'<b>Cached:</b> {proc} ({proc_size})<br>'
            f'<b>Format:</b> {self._cached_path.suffix.lstrip(".").upper()}'
        )
        self._status_label.setText(f'Cached preview for {self._specs.platform_name}')
        self._progress.setValue(100)

    def _set_preview_pixmap(self, pixmap: QPixmap):
        if pixmap.isNull():
            self._source_pixmap = None
            self._preview_label.clear()
            return
        self._source_pixmap = pixmap
        self._preview_label.setText('')
        self._update_preview_pixmap()

    def _update_preview_pixmap(self):
        if self._source_pixmap is None:
            return
        target_w = max(1, self._preview_label.contentsRect().width())
        target_h = max(1, self._preview_label.contentsRect().height())
        scaled = self._source_pixmap.scaled(
            target_w,
            target_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview_label.setPixmap(scaled)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._update_preview_pixmap()


class VideoPreviewTab(QWidget):
    """Single platform video preview tab with lazy loading."""

    preview_done = pyqtSignal(bool)

    def __init__(
        self,
        video_path: Path,
        specs: PlatformSpecs,
        parent=None,
        cached_path: Path | None = None,
    ):
        super().__init__(parent)
        self._video_path = video_path
        self._specs = specs
        self._loaded = False
        self._cached_path = cached_path if cached_path and cached_path.exists() else None
        self._result_path: Path | None = self._cached_path
        self._thread: QThread | None = None
        self._worker: _VideoProcessWorker | None = None
        self._source_pixmap: QPixmap | None = None
        self._duration_ms = 0
        self._seeking = False
        self._media_player = None
        self._audio_output = None
        self._video_widget = None

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
        self._preview_label.setMinimumSize(220, 220)
        self._preview_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self._preview_label)

        if QtMultimediaWidgetsModule is not None:
            self._video_widget = QtMultimediaWidgetsModule.QVideoWidget(self)
            self._video_widget.setMinimumSize(220, 220)
            self._video_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            self._video_widget.hide()
            layout.addWidget(self._video_widget)

        controls_layout = QHBoxLayout()
        self._play_btn = QPushButton('Play')
        self._play_btn.clicked.connect(self._toggle_playback)
        controls_layout.addWidget(self._play_btn)

        self._position_slider = QSlider(Qt.Orientation.Horizontal)
        self._position_slider.setRange(0, 0)
        self._position_slider.sliderPressed.connect(self._on_slider_pressed)
        self._position_slider.sliderReleased.connect(self._on_slider_released)
        self._position_slider.sliderMoved.connect(self._on_slider_moved)
        controls_layout.addWidget(self._position_slider, 1)

        self._time_label = QLabel('0:00 / 0:00')
        controls_layout.addWidget(self._time_label)

        self._fullscreen_btn = QPushButton('Fullscreen')
        self._fullscreen_btn.clicked.connect(self._toggle_fullscreen)
        controls_layout.addWidget(self._fullscreen_btn)
        layout.addLayout(controls_layout)

        self._details_label = QLabel()
        self._details_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._details_label)

        self._init_media_player()
        self._set_controls_visible(False)

    def load_preview(self):
        """Generate and display the video preview (lazy loaded)."""
        if self._loaded:
            return
        if self._cached_path is not None:
            self._load_cached()
            return

        self._loaded = True
        self._status_label.setText('Processing video...')
        self._progress.setValue(0)

        self._thread = QThread(self)
        self._worker = _VideoProcessWorker(
            self._video_path,
            self._specs,
            generate_thumbnail=not self._has_media_player(),
        )
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

    def _on_preview_ready(self, result: dict):
        """Handle video processing completion."""
        from src.core.video_processor import ProcessedVideo

        processed: ProcessedVideo = result['processed']
        thumb_path: Path | None = result.get('thumbnail')
        self._result_path = processed.path

        video_loaded = self._load_video_source(processed.path)
        if not video_loaded:
            # Fallback preview when QtMultimedia backend is unavailable
            if thumb_path and thumb_path.exists():
                self._set_preview_pixmap(QPixmap(str(thumb_path)))
            else:
                self._preview_label.setText('(no thumbnail available)')

        orig = processed.original_info
        proc = processed.processed_info
        orig_res = f'{orig.width}x{orig.height}'
        proc_res = f'{proc.width}x{proc.height}'
        orig_size = _format_size(orig.file_size)
        proc_size = _format_size(proc.file_size)
        orig_dur = _format_duration(orig.duration_seconds)
        proc_dur = _format_duration(proc.duration_seconds)
        proc_fmt = (
            proc.format_name.upper() if proc.format_name else processed.path.suffix.lstrip('.')
        )
        conversion_note = (
            'No conversion required.'
            if processed.path == self._video_path
            else 'Converted to fit platform limits.'
        )
        changes_html = '<br>'.join(f'- {line}' for line in _describe_video_changes(orig, proc))

        if processed.meets_requirements:
            status = (
                '<span style="color: #4CAF50; font-weight: bold;">\u2713 Meets requirements</span>'
            )
        else:
            status = (
                f'<span style="color: #F44336; font-weight: bold;">'
                f'\u26a0 {processed.warning}</span>'
            )

        self._details_label.setText(
            f'<b>Original:</b> {orig_res} ({orig_size}), {orig_dur}, {orig.codec}<br>'
            f'<b>Processed:</b> {proc_res} ({proc_size}), {proc_dur}<br>'
            f'<b>Format:</b> {proc_fmt} ({proc.codec})<br>'
            f'<b>Output:</b> {conversion_note}<br>'
            f'<b>Changes:</b><br>{changes_html}<br><br>'
            f'{status}'
        )
        self._status_label.setText(f'Video preview for {self._specs.platform_name}')
        self.preview_done.emit(True)

    def _on_preview_error(self, message: str):
        self._progress.setValue(0)
        self._status_label.setText(f'Error: {message}')
        get_logger().error(
            'Video preview processing failed',
            extra={
                'platform': self._specs.platform_name,
                'video_path': str(self._video_path),
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
        if not self._load_video_source(self._cached_path):
            from src.core.video_processor import extract_thumbnail

            thumb = extract_thumbnail(self._cached_path)
            if thumb and thumb.exists():
                self._set_preview_pixmap(QPixmap(str(thumb)))
            else:
                self._preview_label.setText('(cached video)')
        proc_size = _format_size(self._cached_path.stat().st_size)
        self._details_label.setText(
            f'<b>Cached:</b> ({proc_size})<br>'
            f'<b>Format:</b> {self._cached_path.suffix.lstrip(".").upper()}'
        )
        self._status_label.setText(f'Cached video for {self._specs.platform_name}')
        self._progress.setValue(100)

    def _set_preview_pixmap(self, pixmap: QPixmap):
        if pixmap.isNull():
            self._source_pixmap = None
            self._preview_label.clear()
            return
        self._source_pixmap = pixmap
        self._preview_label.setText('')
        self._update_preview_pixmap()

    def _update_preview_pixmap(self):
        if self._source_pixmap is None:
            return
        target_w = max(1, self._preview_label.contentsRect().width())
        target_h = max(1, self._preview_label.contentsRect().height())
        scaled = self._source_pixmap.scaled(
            target_w,
            target_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview_label.setPixmap(scaled)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._update_preview_pixmap()

    def _init_media_player(self):
        if QtMultimediaModule is None or self._video_widget is None:
            return
        self._media_player = QtMultimediaModule.QMediaPlayer(self)
        self._audio_output = QtMultimediaModule.QAudioOutput(self)
        self._audio_output.setVolume(0.0)
        self._media_player.setAudioOutput(self._audio_output)
        self._media_player.setVideoOutput(self._video_widget)
        self._media_player.positionChanged.connect(self._on_position_changed)
        self._media_player.durationChanged.connect(self._on_duration_changed)
        self._media_player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._video_widget.fullScreenChanged.connect(self._on_fullscreen_changed)

    def _has_media_player(self) -> bool:
        return self._media_player is not None and self._video_widget is not None

    def _set_controls_visible(self, visible: bool):
        self._play_btn.setVisible(visible)
        self._position_slider.setVisible(visible)
        self._time_label.setVisible(visible)
        self._fullscreen_btn.setVisible(visible)
        self._play_btn.setEnabled(visible)
        self._position_slider.setEnabled(visible)
        self._fullscreen_btn.setEnabled(visible)

    def _load_video_source(self, video_path: Path) -> bool:
        if not self._has_media_player():
            self._set_controls_visible(False)
            return False
        assert self._media_player is not None
        assert self._video_widget is not None
        self._preview_label.hide()
        self._video_widget.show()
        self._set_controls_visible(True)
        self._duration_ms = 0
        self._position_slider.setRange(0, 0)
        self._time_label.setText('0:00 / 0:00')
        self._media_player.setSource(QUrl.fromLocalFile(str(video_path)))
        self._media_player.pause()
        self._media_player.setPosition(0)
        return True

    def _toggle_playback(self):
        if not self._has_media_player():
            return
        assert self._media_player is not None
        playing_state = type(self._media_player).PlaybackState.PlayingState
        if self._media_player.playbackState() == playing_state:
            self._media_player.pause()
        else:
            self._media_player.play()

    def _on_duration_changed(self, duration_ms: int):
        self._duration_ms = max(0, duration_ms)
        self._position_slider.setRange(0, self._duration_ms)
        self._time_label.setText(
            f'{_format_duration(0)} / {_format_duration(self._duration_ms / 1000)}'
        )

    def _on_position_changed(self, position_ms: int):
        if not self._seeking:
            self._position_slider.setValue(max(0, position_ms))
        self._time_label.setText(
            f'{_format_duration(max(0, position_ms) / 1000)} / '
            f'{_format_duration(self._duration_ms / 1000)}'
        )

    def _on_playback_state_changed(self, state):
        if self._media_player is None:
            return
        playing_state = type(self._media_player).PlaybackState.PlayingState
        if state == playing_state:
            self._play_btn.setText('Pause')
        else:
            self._play_btn.setText('Play')

    def _on_slider_pressed(self):
        self._seeking = True

    def _on_slider_released(self):
        self._seeking = False
        if self._has_media_player():
            assert self._media_player is not None
            self._media_player.setPosition(self._position_slider.value())

    def _on_slider_moved(self, value: int):
        self._time_label.setText(
            f'{_format_duration(max(0, value) / 1000)} / '
            f'{_format_duration(self._duration_ms / 1000)}'
        )

    def _toggle_fullscreen(self):
        if self._video_widget is None:
            return
        self._video_widget.setFullScreen(not self._video_widget.isFullScreen())

    def _on_fullscreen_changed(self, is_fullscreen: bool):
        self._fullscreen_btn.setText('Exit Fullscreen' if is_fullscreen else 'Fullscreen')


class ImagePreviewDialog(QDialog):
    """Tabbed dialog showing per-platform media previews."""

    def __init__(
        self,
        image_path: Path,
        platforms: list[str],
        parent=None,
        existing_paths: dict[str, Path | None] | None = None,
    ):
        super().__init__(parent)
        self._image_path = image_path
        self._tabs: dict[str, ImagePreviewTab | VideoPreviewTab] = {}
        self._processed_paths: dict[str, Path | None] = {}
        self._had_errors = False
        self._pending_tabs = 0
        self._existing_paths = existing_paths or {}
        self._is_video = _is_video(image_path)
        self._has_video_tabs = self._is_video

        title = 'Video Preview' if self._is_video else 'Media Preview'
        self.setWindowTitle(title)
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
                cached_is_video = bool(cached_path and _is_video(cached_path))
                if self._is_video or cached_is_video:
                    video_source = image_path if self._is_video else (cached_path or image_path)
                    preview_tab: ImagePreviewTab | VideoPreviewTab = VideoPreviewTab(
                        video_source,
                        specs,
                        self,
                        cached_path=cached_path,
                    )
                    self._has_video_tabs = True
                else:
                    preview_tab = ImagePreviewTab(image_path, specs, self, cached_path=cached_path)
                self._tabs[platform] = preview_tab
                self._tab_widget.addTab(preview_tab, specs.platform_name)

        layout.addWidget(self._tab_widget)

        # Info label
        if self._is_video:
            info_text = (
                '<i>Videos are automatically resized and compressed for each platform. '
                'Aspect ratios are preserved as best as possible within platform limitations. '
                'Output format is MP4 (H.264).</i>'
            )
        elif self._has_video_tabs:
            info_text = (
                '<i>This preview includes both image and video outputs. '
                'Video-only platforms display their converted MP4 output.</i>'
            )
        else:
            info_text = (
                '<i>Images are automatically optimized for each platform. '
                'Aspect ratios are preserved as best as possible within platform limitations.</i>'
            )
        info = QLabel(info_text)
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
        if isinstance(widget, (ImagePreviewTab, VideoPreviewTab)):
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
        """Return {platform: processed_media_path} for all loaded tabs."""
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


class _VideoProcessWorker(QObject):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(self, video_path: Path, specs: PlatformSpecs, generate_thumbnail: bool = True):
        super().__init__()
        self._video_path = video_path
        self._specs = specs
        self._generate_thumbnail = generate_thumbnail

    def run(self):
        from src.core.video_processor import extract_thumbnail, process_video

        logger = get_logger()
        try:
            logger.info(
                'Video preview processing started',
                extra={
                    'platform': self._specs.platform_name,
                    'video_path': str(self._video_path),
                },
            )
            processed = process_video(self._video_path, self._specs, progress_cb=self.progress.emit)
            thumbnail = extract_thumbnail(processed.path) if self._generate_thumbnail else None
            logger.info(
                'Video preview processing finished',
                extra={
                    'platform': self._specs.platform_name,
                    'processed_path': str(processed.path),
                },
            )
            self.finished.emit({'processed': processed, 'thumbnail': thumbnail})
        except Exception as exc:
            logger.exception(
                'Video preview processing failed',
                extra={
                    'platform': self._specs.platform_name,
                    'video_path': str(self._video_path),
                    'error': str(exc),
                },
            )
            self.error.emit(str(exc))
