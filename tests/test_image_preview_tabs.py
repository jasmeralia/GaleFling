"""Tests for image preview tabs and dialog."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QLabel

from src.core.image_processor import ProcessedImage
from src.core.video_processor import ProcessedVideo, VideoInfo
from src.gui.image_preview_tabs import (
    ImagePreviewDialog,
    ImagePreviewTab,
    VideoPreviewTab,
    _describe_video_changes,
    _format_attachment_summary,
    _format_duration,
    _format_frame_rate,
    _format_size,
    _ImageProcessWorker,
    _VideoProcessWorker,
)
from src.utils.constants import SNAPCHAT_SPECS, TWITTER_SPECS


def _write_image(path: Path, size=(10, 10), color=(255, 0, 0)) -> Path:
    image = Image.new('RGB', size, color)
    image.save(path)
    return path


def test_format_size():
    assert _format_size(10) == '10 B'
    assert _format_size(2048).endswith('KB')
    assert _format_size(5 * 1024 * 1024).endswith('MB')


def test_cached_preview_tab_loads_cached_image(qtbot, tmp_path):
    original = _write_image(tmp_path / 'original.png')
    cached = _write_image(tmp_path / 'cached.png', size=(20, 20))

    tab = ImagePreviewTab(original, TWITTER_SPECS, cached_path=cached)
    qtbot.addWidget(tab)

    tab.load_preview()

    assert tab.get_processed_path() == cached
    assert tab._progress.value() == 100
    assert 'Cached preview' in tab._status_label.text()
    assert 'Cached' in tab._details_label.text()

    pixmap = tab._preview_label.pixmap()
    assert pixmap is not None
    assert pixmap.width() > 0


def test_preview_dialog_with_cached_paths_enables_ok(qtbot, tmp_path):
    original = _write_image(tmp_path / 'original.png')
    cached_tw = _write_image(tmp_path / 'tw.png', size=(30, 30))
    cached_bs = _write_image(tmp_path / 'bs.png', size=(40, 40))

    dialog = ImagePreviewDialog(
        original,
        ['twitter', 'bluesky'],
        existing_paths={'twitter': cached_tw, 'bluesky': cached_bs},
    )
    qtbot.addWidget(dialog)

    assert dialog._ok_btn.isEnabled()
    paths = dialog.get_processed_paths()
    assert paths['twitter'] == cached_tw
    assert paths['bluesky'] == cached_bs


def test_preview_dialog_without_platforms_enables_ok(qtbot, tmp_path):
    original = _write_image(tmp_path / 'original.png')

    dialog = ImagePreviewDialog(original, [])
    qtbot.addWidget(dialog)

    assert dialog._ok_btn.isEnabled()


def test_preview_dialog_uses_video_tab_for_cached_video_output(qtbot, tmp_path, monkeypatch):
    original = _write_image(tmp_path / 'original.png')
    cached_video = tmp_path / 'snapchat_cached.mp4'
    cached_video.write_bytes(b'mp4')

    monkeypatch.setattr('src.gui.image_preview_tabs.QtMultimediaModule', None)
    monkeypatch.setattr('src.gui.image_preview_tabs.QtMultimediaWidgetsModule', None)
    monkeypatch.setattr(
        'src.core.video_processor.extract_thumbnail', lambda *_args, **_kwargs: None
    )

    dialog = ImagePreviewDialog(
        original,
        ['snapchat'],
        existing_paths={'snapchat': cached_video},
    )
    qtbot.addWidget(dialog)

    assert isinstance(dialog._tabs['snapchat'][0], VideoPreviewTab)
    assert dialog._tabs['snapchat'][0].get_processed_path() == cached_video


def test_preview_dialog_collapses_snapchat_multi_image_to_single_video_tab(
    qtbot, tmp_path, monkeypatch
):
    original_1 = _write_image(tmp_path / 'original_1.png')
    original_2 = _write_image(tmp_path / 'original_2.png')
    cached_video = tmp_path / 'snapchat_cached.mp4'
    cached_video.write_bytes(b'mp4')
    monkeypatch.setattr('src.gui.image_preview_tabs.QtMultimediaModule', None)
    monkeypatch.setattr('src.gui.image_preview_tabs.QtMultimediaWidgetsModule', None)
    monkeypatch.setattr(
        'src.core.video_processor.extract_thumbnail', lambda *_args, **_kwargs: None
    )

    dialog = ImagePreviewDialog(
        [original_1, original_2],
        ['snapchat'],
        existing_paths={'snapchat': [cached_video, cached_video]},
    )
    qtbot.addWidget(dialog)

    assert len(dialog._tabs['snapchat']) == 1
    assert dialog._platform_attachment_tabs['snapchat'] is None


def test_cached_preview_scales_with_resize(qtbot, tmp_path):
    original = _write_image(tmp_path / 'original.png')
    cached = _write_image(tmp_path / 'cached.png', size=(1200, 800))

    tab = ImagePreviewTab(original, TWITTER_SPECS, cached_path=cached)
    qtbot.addWidget(tab)
    tab.resize(900, 900)
    tab.show()
    tab.load_preview()
    qtbot.wait(10)

    initial = tab._preview_label.pixmap()
    assert initial is not None

    tab.resize(320, 320)
    qtbot.wait(10)
    resized = tab._preview_label.pixmap()
    assert resized is not None
    assert resized.width() <= tab._preview_label.width()
    assert resized.height() <= tab._preview_label.height()


def test_video_preview_tab_has_playback_controls(qtbot, tmp_path, monkeypatch):
    video_path = tmp_path / 'sample.mp4'
    video_path.write_bytes(b'fake')
    monkeypatch.setattr('src.gui.image_preview_tabs.QtMultimediaModule', None)
    monkeypatch.setattr('src.gui.image_preview_tabs.QtMultimediaWidgetsModule', None)

    tab = VideoPreviewTab(video_path, SNAPCHAT_SPECS, cached_path=video_path)
    qtbot.addWidget(tab)

    assert tab._play_btn.text() == 'Play'
    assert tab._fullscreen_btn.text() == 'Fullscreen'
    assert tab._position_slider.orientation() == Qt.Orientation.Horizontal


def test_preview_dialog_info_text_uses_platform_limit_wording(qtbot, tmp_path):
    original = _write_image(tmp_path / 'original.png')
    cached = _write_image(tmp_path / 'cached.png', size=(20, 20))

    dialog = ImagePreviewDialog(
        original,
        ['twitter'],
        existing_paths={'twitter': cached},
    )
    qtbot.addWidget(dialog)

    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert any(
        'Aspect ratios are preserved as best as possible within platform limitations.' in text
        for text in labels
    )


def test_describe_video_changes_reports_key_differences():
    original = VideoInfo(
        width=1920,
        height=1080,
        duration_seconds=65.0,
        codec='h264',
        file_size=40 * 1024 * 1024,
        format_name='mov',
    )
    processed = VideoInfo(
        width=1080,
        height=1920,
        duration_seconds=60.0,
        codec='h264',
        file_size=20 * 1024 * 1024,
        format_name='mp4',
    )

    changes = _describe_video_changes(original, processed)

    assert any('Length clipped' in line for line in changes)
    assert any('Resolution changed' in line for line in changes)
    assert any('File size reduced' in line for line in changes)
    assert any('Format changed' in line for line in changes)


def test_describe_video_changes_omits_unchanged_fields():
    original = VideoInfo(
        width=1080,
        height=1920,
        duration_seconds=10.0,
        codec='h264',
        file_size=4 * 1024 * 1024,
        format_name='mp4',
        frame_rate=30.0,
    )
    processed = VideoInfo(
        width=1080,
        height=1920,
        duration_seconds=10.0,
        codec='h264',
        file_size=4 * 1024 * 1024,
        format_name='mp4',
        frame_rate=30.0,
    )

    changes = _describe_video_changes(original, processed)

    assert changes == []


def test_preview_dialog_video_attachment_header_includes_metadata(qtbot, tmp_path, monkeypatch):
    video = tmp_path / 'sample.mp4'
    video.write_bytes(b'mp4')
    monkeypatch.setattr(
        'src.core.video_processor.get_video_info',
        lambda _path: VideoInfo(
            width=1280,
            height=720,
            duration_seconds=12.3,
            codec='h264',
            file_size=video.stat().st_size,
            format_name='mp4',
            frame_rate=29.97,
        ),
    )

    dialog = ImagePreviewDialog(video, [])
    qtbot.addWidget(dialog)

    labels = [label.text() for label in dialog.findChildren(QLabel) if label.text()]
    assert any(
        'sample.mp4' in text and '1280x720' in text and '29.97 fps' in text for text in labels
    )


def test_preview_dialog_close_timeout_unblocks_modal_loop(qtbot, tmp_path):
    original = _write_image(tmp_path / 'original.png')
    cached = _write_image(tmp_path / 'cached.png')
    dialog = ImagePreviewDialog(original, ['twitter'], existing_paths={'twitter': cached})
    qtbot.addWidget(dialog)

    tab = dialog._tabs['twitter'][0]
    callbacks: list[object] = []

    tab.has_active_worker = lambda: True  # type: ignore[assignment]

    def delayed_shutdown(on_done=None):
        if on_done is not None:
            callbacks.append(on_done)

    tab.begin_shutdown = delayed_shutdown  # type: ignore[assignment]
    dialog.SHUTDOWN_CLOSE_TIMEOUT_MS = 10
    ImagePreviewDialog._retained_dialogs = []

    dialog._request_close(QDialog.DialogCode.Rejected)

    qtbot.waitUntil(lambda: dialog.result() == int(QDialog.DialogCode.Rejected), timeout=1000)
    assert dialog in ImagePreviewDialog._retained_dialogs
    assert len(callbacks) == 1

    callbacks[0]()
    qtbot.waitUntil(lambda: dialog not in ImagePreviewDialog._retained_dialogs, timeout=1000)


def test_preview_dialog_close_releases_retention_after_immediate_shutdown(qtbot, tmp_path):
    original = _write_image(tmp_path / 'original.png')
    cached = _write_image(tmp_path / 'cached.png')
    dialog = ImagePreviewDialog(original, ['twitter'], existing_paths={'twitter': cached})
    qtbot.addWidget(dialog)

    tab = dialog._tabs['twitter'][0]
    tab.has_active_worker = lambda: False  # type: ignore[assignment]
    tab.begin_shutdown = lambda on_done=None: on_done() if on_done is not None else None  # type: ignore[assignment]
    dialog.SHUTDOWN_CLOSE_TIMEOUT_MS = 10
    ImagePreviewDialog._retained_dialogs = []

    dialog._request_close(QDialog.DialogCode.Accepted)

    qtbot.waitUntil(lambda: dialog.result() == int(QDialog.DialogCode.Accepted), timeout=1000)
    assert dialog not in ImagePreviewDialog._retained_dialogs


def test_format_duration_includes_hours_when_needed():
    assert _format_duration(59) == '0:59'
    assert _format_duration(3661) == '1:01:01'


def test_format_frame_rate_handles_unknown_and_valid_values():
    assert _format_frame_rate(None) == 'unknown fps'
    assert _format_frame_rate(0) == 'unknown fps'
    assert _format_frame_rate(29.97) == '29.97 fps'


def test_format_attachment_summary_for_image(tmp_path):
    image = _write_image(tmp_path / 'still.png')

    summary = _format_attachment_summary(image)

    assert summary.startswith('still.png (')
    assert 'B)' in summary


def test_format_attachment_summary_for_video_with_metadata(tmp_path, monkeypatch):
    video = tmp_path / 'clip.mp4'
    video.write_bytes(b'mp4')

    monkeypatch.setattr(
        'src.core.video_processor.get_video_info',
        lambda _path: VideoInfo(
            width=1280,
            height=720,
            duration_seconds=12.3,
            codec='h264',
            file_size=video.stat().st_size,
            format_name='mp4',
            frame_rate=29.97,
        ),
    )

    summary = _format_attachment_summary(video)

    assert 'clip.mp4' in summary
    assert 'MP4' in summary
    assert '1280x720' in summary
    assert '29.97 fps' in summary


def test_format_attachment_summary_handles_video_metadata_error(tmp_path, monkeypatch):
    video = tmp_path / 'clip.mp4'
    video.write_bytes(b'mp4')

    monkeypatch.setattr(
        'src.core.video_processor.get_video_info',
        lambda _path: (_ for _ in ()).throw(RuntimeError('probe failed')),
    )

    summary = _format_attachment_summary(video)

    assert 'metadata unavailable' in summary


class _DummySignal:
    def __init__(self):
        self._callbacks = []

    def connect(self, callback):
        self._callbacks.append(callback)

    def disconnect(self, callback):
        self._callbacks.remove(callback)

    def emit(self, *args, **kwargs):
        for callback in list(self._callbacks):
            callback(*args, **kwargs)


class _DummyThread:
    def __init__(self, *_args, running=True, **_kwargs):
        self.started = _DummySignal()
        self.finished = _DummySignal()
        self._running = running
        self.requested_interruption = False
        self.quit_called = False
        self.deleted = False

    def start(self):
        self._running = True

    def isRunning(self):  # noqa: N802
        return self._running

    def requestInterruption(self):  # noqa: N802
        self.requested_interruption = True

    def quit(self):
        self.quit_called = True
        self._running = False

    def deleteLater(self):  # noqa: N802
        self.deleted = True


class _DummyWorker:
    def __init__(self, *_args, **_kwargs):
        self.progress = _DummySignal()
        self.finished = _DummySignal()
        self.error = _DummySignal()
        self.moved_to = None
        self.deleted = False

    def moveToThread(self, thread):  # noqa: N802
        self.moved_to = thread

    def run(self):
        return

    def deleteLater(self):  # noqa: N802
        self.deleted = True


def _make_processed_image(path: Path) -> ProcessedImage:
    return ProcessedImage(
        path=path,
        original_size=(800, 600),
        processed_size=(640, 480),
        original_file_size=200_000,
        processed_file_size=100_000,
        format='JPEG',
        quality=85,
        meets_requirements=True,
    )


def _make_video_info(width=1280, height=720, duration=12.0, file_size=2_000_000) -> VideoInfo:
    return VideoInfo(
        width=width,
        height=height,
        duration_seconds=duration,
        codec='h264',
        file_size=file_size,
        format_name='mp4',
        frame_rate=30.0,
    )


def test_image_preview_tab_thread_and_error_paths(qtbot, tmp_path, monkeypatch):
    original = _write_image(tmp_path / 'original.png')
    tab = ImagePreviewTab(original, TWITTER_SPECS)
    qtbot.addWidget(tab)

    monkeypatch.setattr('src.gui.image_preview_tabs.QThread', _DummyThread)
    monkeypatch.setattr('src.gui.image_preview_tabs._ImageProcessWorker', _DummyWorker)

    tab.load_preview()
    tab.load_preview()  # no-op when already loaded

    assert isinstance(tab._thread, _DummyThread)
    assert isinstance(tab._worker, _DummyWorker)

    emitted = []
    tab.preview_done.connect(emitted.append)
    tab._on_preview_error('boom')
    assert emitted == [False]
    assert 'Error: boom' in tab._status_label.text()

    callback_called = []
    tab.begin_shutdown(lambda: callback_called.append(True))
    assert tab._thread.requested_interruption is True
    assert tab._thread.quit_called is True
    assert callback_called == []

    tab._on_thread_finished()
    assert callback_called == [True]


def test_image_preview_tab_preview_ready_updates_details(qtbot, tmp_path):
    original = _write_image(tmp_path / 'original.png')
    processed_path = _write_image(tmp_path / 'processed.jpg', size=(640, 480))
    tab = ImagePreviewTab(original, TWITTER_SPECS)
    qtbot.addWidget(tab)

    emitted = []
    tab.preview_done.connect(emitted.append)
    tab._on_preview_ready(_make_processed_image(processed_path))

    assert emitted == [True]
    assert tab.get_processed_path() == processed_path
    assert 'Will resize to' in tab._details_label.text()


def test_image_process_worker_success_and_error_paths(tmp_path, monkeypatch):
    image_path = _write_image(tmp_path / 'original.png')
    processed_path = _write_image(tmp_path / 'processed.jpg')
    processed = _make_processed_image(processed_path)

    worker = _ImageProcessWorker(image_path, TWITTER_SPECS)
    finished = []
    errors = []
    worker.finished.connect(finished.append)
    worker.error.connect(errors.append)

    monkeypatch.setattr('src.gui.image_preview_tabs.is_animated_gif', lambda _p: False)
    monkeypatch.setattr('src.gui.image_preview_tabs.process_image', lambda *_a, **_k: processed)
    worker.run()

    assert finished == [processed]
    assert errors == []

    worker = _ImageProcessWorker(image_path, TWITTER_SPECS)
    errors = []
    worker.error.connect(errors.append)
    monkeypatch.setattr(
        'src.gui.image_preview_tabs.process_image',
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError('processing failed')),
    )
    worker.run()

    assert errors == ['processing failed']


def test_video_process_worker_success_and_error_paths(tmp_path, monkeypatch):
    video = tmp_path / 'input.mp4'
    video.write_bytes(b'mp4')
    processed = ProcessedVideo(
        path=video,
        original_info=_make_video_info(),
        processed_info=_make_video_info(),
        meets_requirements=True,
    )

    worker = _VideoProcessWorker(video, SNAPCHAT_SPECS, generate_thumbnail=True)
    finished = []
    errors = []
    worker.finished.connect(finished.append)
    worker.error.connect(errors.append)

    monkeypatch.setattr('src.core.video_processor.process_video', lambda *_a, **_k: processed)
    monkeypatch.setattr('src.core.video_processor.extract_thumbnail', lambda *_a, **_k: video)
    worker.run()

    assert finished and finished[0]['processed'] == processed
    assert finished[0]['thumbnail'] == video
    assert errors == []

    worker = _VideoProcessWorker(video, SNAPCHAT_SPECS, generate_thumbnail=False)
    errors = []
    worker.error.connect(errors.append)
    monkeypatch.setattr(
        'src.core.video_processor.process_video',
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError('video failed')),
    )
    worker.run()

    assert errors == ['video failed']


def test_video_preview_tab_load_cached_fallback_text(qtbot, tmp_path, monkeypatch):
    video = tmp_path / 'cached.mp4'
    video.write_bytes(b'mp4')
    tab = VideoPreviewTab(video, SNAPCHAT_SPECS, cached_path=video)
    qtbot.addWidget(tab)

    monkeypatch.setattr(tab, '_load_video_source', lambda _path: False)
    monkeypatch.setattr('src.core.video_processor.extract_thumbnail', lambda *_a, **_k: None)

    tab.load_preview()

    assert '(cached video)' in tab._preview_label.text()
    assert tab._progress.value() == 100


def test_video_preview_tab_media_controls_and_shutdown_with_fake_multimedia(
    qtbot, tmp_path, monkeypatch
):
    class FakeAudioOutput:
        def __init__(self, *_args, **_kwargs):
            self.deleted = False

        def setVolume(self, _value):  # noqa: N802
            return

        def deleteLater(self):  # noqa: N802
            self.deleted = True

    class FakePlaybackState:
        PlayingState = 1
        PausedState = 0

    class FakeMediaPlayer:
        PlaybackState = FakePlaybackState

        def __init__(self, *_args, **_kwargs):
            self.positionChanged = _DummySignal()
            self.durationChanged = _DummySignal()
            self.playbackStateChanged = _DummySignal()
            self._state = self.PlaybackState.PausedState
            self.source = None
            self.position = 0
            self.deleted = False

        def setAudioOutput(self, _audio):  # noqa: N802
            return

        def setVideoOutput(self, _output):  # noqa: N802
            return

        def setSource(self, source):  # noqa: N802
            self.source = source

        def pause(self):
            self._state = self.PlaybackState.PausedState
            self.playbackStateChanged.emit(self._state)

        def play(self):
            self._state = self.PlaybackState.PlayingState
            self.playbackStateChanged.emit(self._state)

        def stop(self):
            self._state = self.PlaybackState.PausedState

        def setPosition(self, value):  # noqa: N802
            self.position = value
            self.positionChanged.emit(value)

        def playbackState(self):  # noqa: N802
            return self._state

        def deleteLater(self):  # noqa: N802
            self.deleted = True

    class FakeVideoWidget(QLabel):
        def __init__(self, *_args, **_kwargs):
            super().__init__()
            self._fullscreen = False
            self.fullScreenChanged = _DummySignal()

        def setFullScreen(self, value):  # noqa: N802
            self._fullscreen = value
            self.fullScreenChanged.emit(value)

        def isFullScreen(self):  # noqa: N802
            return self._fullscreen

    monkeypatch.setattr(
        'src.gui.image_preview_tabs.QtMultimediaModule',
        SimpleNamespace(QMediaPlayer=FakeMediaPlayer, QAudioOutput=FakeAudioOutput),
    )
    monkeypatch.setattr(
        'src.gui.image_preview_tabs.QtMultimediaWidgetsModule',
        SimpleNamespace(QVideoWidget=FakeVideoWidget),
    )

    video = tmp_path / 'clip.mp4'
    video.write_bytes(b'mp4')
    tab = VideoPreviewTab(video, SNAPCHAT_SPECS, cached_path=video)
    qtbot.addWidget(tab)

    assert tab._load_video_source(video) is True
    tab._toggle_playback()
    assert tab._play_btn.text() == 'Pause'
    tab._toggle_playback()
    assert tab._play_btn.text() == 'Play'

    tab._on_duration_changed(12_000)
    tab._on_position_changed(2_000)
    tab._on_slider_pressed()
    tab._position_slider.setValue(3_000)
    tab._on_slider_released()
    tab._on_slider_moved(4_000)
    tab._toggle_fullscreen()
    assert tab._fullscreen_btn.text() == 'Exit Fullscreen'

    callback_called = []
    tab.begin_shutdown(lambda: callback_called.append(True))
    assert callback_called == [True]
    assert tab._media_player is None


def test_video_preview_tab_ready_and_error_paths(qtbot, tmp_path, monkeypatch):
    source_video = tmp_path / 'source.mp4'
    source_video.write_bytes(b'mp4')
    processed_video = tmp_path / 'processed.mp4'
    processed_video.write_bytes(b'mp4')
    thumb = _write_image(tmp_path / 'thumb.png')

    tab = VideoPreviewTab(source_video, SNAPCHAT_SPECS)
    qtbot.addWidget(tab)
    monkeypatch.setattr(tab, '_load_video_source', lambda _path: False)

    result = {
        'processed': ProcessedVideo(
            path=processed_video,
            original_info=_make_video_info(
                width=1920, height=1080, duration=20.0, file_size=8_000_000
            ),
            processed_info=_make_video_info(
                width=1080, height=1920, duration=10.0, file_size=4_000_000
            ),
            meets_requirements=True,
        ),
        'thumbnail': thumb,
    }
    emitted = []
    tab.preview_done.connect(emitted.append)
    tab._on_preview_ready(result)
    assert emitted == [True]
    assert 'Changes:' in tab._details_label.text()

    tab = VideoPreviewTab(source_video, SNAPCHAT_SPECS)
    qtbot.addWidget(tab)
    emitted = []
    tab.preview_done.connect(emitted.append)
    tab._on_preview_error('bad video')
    assert emitted == [False]
    assert 'Error: bad video' in tab._status_label.text()


def test_preview_dialog_queue_and_done_states(qtbot, tmp_path, monkeypatch):
    original = _write_image(tmp_path / 'original.png')
    processed = _write_image(tmp_path / 'processed.png')

    monkeypatch.setattr(
        'src.gui.image_preview_tabs.ImagePreviewTab.load_preview', lambda _self: None
    )

    dialog = ImagePreviewDialog(original, ['twitter'])
    qtbot.addWidget(dialog)
    tab = dialog._tabs['twitter'][0]
    tab._result_path = processed
    tab.preview_done.emit(True)
    assert dialog._ok_btn.isEnabled() is True

    dialog_err = ImagePreviewDialog(original, ['twitter'])
    qtbot.addWidget(dialog_err)
    tab_err = dialog_err._tabs['twitter'][0]
    tab_err.preview_done.emit(False)
    assert dialog_err.had_errors is True
    assert dialog_err._ok_btn.isEnabled() is False


def test_preview_dialog_handles_unknown_platform_and_multi_processed_paths(qtbot, tmp_path):
    media_1 = _write_image(tmp_path / 'm1.png')
    media_2 = _write_image(tmp_path / 'm2.png')
    dialog = ImagePreviewDialog([media_1, media_2], ['unknown-platform'])
    qtbot.addWidget(dialog)

    assert dialog._tabs == {}
    assert dialog.get_processed_paths() == {}
    assert dialog.get_processed_media_paths() == {}


def test_preview_dialog_shutdown_timeout_noop_when_nothing_pending(qtbot, tmp_path, monkeypatch):
    original = _write_image(tmp_path / 'original.png')
    cached = _write_image(tmp_path / 'cached.png')
    dialog = ImagePreviewDialog(original, ['twitter'], existing_paths={'twitter': cached})
    qtbot.addWidget(dialog)

    called = []
    monkeypatch.setattr(dialog, '_close_modal_loop', lambda: called.append(True))
    dialog._pending_shutdown_tabs = 0
    dialog._on_shutdown_timeout()

    assert called == []


def test_preview_dialog_close_event_requests_close_when_not_closing(qtbot, tmp_path, monkeypatch):
    original = _write_image(tmp_path / 'original.png')
    cached = _write_image(tmp_path / 'cached.png')
    dialog = ImagePreviewDialog(original, ['twitter'], existing_paths={'twitter': cached})
    qtbot.addWidget(dialog)

    requested = []
    monkeypatch.setattr(dialog, '_request_close', lambda code: requested.append(code))

    class DummyEvent:
        def __init__(self):
            self.ignored = False

        def ignore(self):
            self.ignored = True

    event = DummyEvent()
    dialog.closeEvent(event)

    assert event.ignored is True
    assert requested == [QDialog.DialogCode.Rejected]
