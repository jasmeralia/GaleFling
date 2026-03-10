"""Tests for image preview tabs and dialog."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel

from src.core.video_processor import VideoInfo
from src.gui.image_preview_tabs import (
    ImagePreviewDialog,
    ImagePreviewTab,
    VideoPreviewTab,
    _describe_video_changes,
    _format_size,
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

    assert isinstance(dialog._tabs['snapchat'], VideoPreviewTab)
    assert dialog._tabs['snapchat'].get_processed_path() == cached_video


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
