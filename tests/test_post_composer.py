"""Tests for PostComposer text warning, character counters, and multi-attachment."""

import tempfile
from pathlib import Path

import pytest

from src.core.video_processor import VideoInfo
from src.gui.post_composer import PostComposer
from src.utils.constants import MAX_MEDIA_ATTACHMENTS


@pytest.fixture
def composer(qtbot):
    """Create a PostComposer with account platform mapping."""
    comp = PostComposer()
    qtbot.addWidget(comp)
    comp.set_account_platform_map(
        {
            'twitter_1': 'twitter',
            'bluesky_1': 'bluesky',
            'snapchat_1': 'snapchat',
            'fetlife_1': 'fetlife',
        }
    )
    return comp


class TestTextWarning:
    def test_no_warning_without_text(self, composer):
        """No warning shown when text is empty."""
        composer.set_platform_state(selected=['snapchat_1'], enabled=['snapchat_1'])
        assert composer._text_warning.isHidden()

    def test_warning_shown_for_snapchat_with_text(self, composer):
        """Warning shown when Snapchat selected and text entered."""
        composer.set_platform_state(selected=['snapchat_1'], enabled=['snapchat_1'])
        composer.set_text('Hello world')
        assert not composer._text_warning.isHidden()
        assert 'Snapchat' in composer._text_warning.text()

    def test_warning_hidden_when_snapchat_deselected(self, composer):
        """Warning hidden when Snapchat is deselected."""
        composer.set_platform_state(selected=['snapchat_1'], enabled=['snapchat_1'])
        composer.set_text('Hello world')
        assert not composer._text_warning.isHidden()
        # Deselect Snapchat
        composer.set_platform_state(selected=['twitter_1'], enabled=['twitter_1', 'snapchat_1'])
        assert composer._text_warning.isHidden()

    def test_warning_hidden_when_text_cleared(self, composer):
        """Warning hidden when text is cleared."""
        composer.set_platform_state(selected=['snapchat_1'], enabled=['snapchat_1'])
        composer.set_text('Hello world')
        assert not composer._text_warning.isHidden()
        composer.set_text('')
        assert composer._text_warning.isHidden()

    def test_warning_with_mixed_platforms(self, composer):
        """Warning shown when Snapchat + other platforms selected."""
        composer.set_platform_state(
            selected=['twitter_1', 'snapchat_1'],
            enabled=['twitter_1', 'snapchat_1'],
        )
        composer.set_text('Hello world')
        assert not composer._text_warning.isHidden()
        assert 'Snapchat' in composer._text_warning.text()

    def test_no_warning_for_text_supporting_platforms(self, composer):
        """No warning when only text-supporting platforms are selected."""
        composer.set_platform_state(
            selected=['twitter_1', 'bluesky_1'],
            enabled=['twitter_1', 'bluesky_1'],
        )
        composer.set_text('Hello world')
        assert composer._text_warning.isHidden()

    def test_warning_shown_for_fetlife_with_media_and_text(self, composer):
        """FetLife should warn that text is ignored when media is attached."""
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
            media = Path(f.name)
        composer.set_media_paths([media])
        composer.set_platform_state(selected=['fetlife_1'], enabled=['fetlife_1'])
        composer.set_text('Hello world')

        assert not composer._text_warning.isHidden()
        assert 'FetLife' in composer._text_warning.text()
        assert 'media is attached' in composer._text_warning.text()
        media.unlink(missing_ok=True)

    def test_no_warning_for_fetlife_text_only(self, composer):
        """FetLife text-only posts should not show the media text warning."""
        composer.set_platform_state(selected=['fetlife_1'], enabled=['fetlife_1'])
        composer.set_text('Hello world')
        assert composer._text_warning.isHidden()


class TestCharacterCounters:
    def test_shows_counter_for_twitter(self, composer):
        """Twitter counter should appear when Twitter selected."""
        composer.set_platform_state(selected=['twitter_1'], enabled=['twitter_1'])
        assert 'twitter' in composer._counter_labels

    def test_counter_updates_on_text_change(self, composer):
        """Counter text updates when text changes."""
        composer.set_platform_state(selected=['twitter_1'], enabled=['twitter_1'])
        composer.set_text('Hello')
        lbl = composer._counter_labels['twitter']
        assert '5/280' in lbl.text()

    def test_no_counter_for_snapchat(self, composer):
        """Snapchat has no text limit, so no counter."""
        composer.set_platform_state(selected=['snapchat_1'], enabled=['snapchat_1'])
        assert 'snapchat' not in composer._counter_labels

    def test_counter_removed_when_deselected(self, composer):
        """Counter removed when platform is deselected."""
        composer.set_platform_state(selected=['twitter_1'], enabled=['twitter_1'])
        assert 'twitter' in composer._counter_labels
        composer.set_platform_state(selected=[], enabled=['twitter_1'])
        assert 'twitter' not in composer._counter_labels


class TestMultiAttachment:
    def test_get_media_paths_empty(self, composer):
        """Empty by default."""
        assert composer.get_media_paths() == []

    def test_set_media_paths(self, composer):
        """Can set multiple paths."""
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f1:
            p1 = Path(f1.name)
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f2:
            p2 = Path(f2.name)
        composer.set_media_paths([p1, p2])
        assert composer.get_media_paths() == [p1, p2]
        p1.unlink(missing_ok=True)
        p2.unlink(missing_ok=True)

    def test_set_media_paths_caps_at_max(self, composer):
        """Paths beyond MAX_MEDIA_ATTACHMENTS are dropped."""
        paths = []
        for _i in range(MAX_MEDIA_ATTACHMENTS + 2):
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
                paths.append(Path(f.name))
        composer.set_media_paths(paths)
        assert len(composer.get_media_paths()) == MAX_MEDIA_ATTACHMENTS
        for p in paths:
            p.unlink(missing_ok=True)

    def test_remove_media(self, composer):
        """Can remove a media item by index."""
        paths = []
        for _i in range(3):
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
                paths.append(Path(f.name))
        composer.set_media_paths(paths)
        composer._remove_media(1)
        remaining = composer.get_media_paths()
        assert len(remaining) == 2
        assert remaining[0] == paths[0]
        assert remaining[1] == paths[2]
        for p in paths:
            p.unlink(missing_ok=True)

    def test_clear_all_media(self, composer):
        """Clear all removes everything."""
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
            p = Path(f.name)
        composer.set_media_paths([p])
        assert composer.get_media_paths() == [p]
        composer._clear_all_media()
        assert composer.get_media_paths() == []
        p.unlink(missing_ok=True)

    def test_get_image_path_backward_compat(self, composer):
        """get_image_path returns first path for backward compat."""
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f1:
            p1 = Path(f1.name)
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f2:
            p2 = Path(f2.name)
        composer.set_media_paths([p1, p2])
        assert composer.get_image_path() == p1
        p1.unlink(missing_ok=True)
        p2.unlink(missing_ok=True)

    def test_get_image_path_none_when_empty(self, composer):
        """get_image_path returns None when no media."""
        assert composer.get_image_path() is None

    def test_media_item_rows_created(self, composer):
        """Media item rows are created for each attachment."""
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f1:
            p1 = Path(f1.name)
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f2:
            p2 = Path(f2.name)
        composer.set_media_paths([p1, p2])
        assert len(composer._media_item_rows) == 2
        p1.unlink(missing_ok=True)
        p2.unlink(missing_ok=True)

    def test_placeholder_hidden_when_media_attached(self, composer):
        """Placeholder hidden when media is present."""
        assert not composer._placeholder_label.isHidden()
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
            p = Path(f.name)
        composer.set_media_paths([p])
        assert composer._placeholder_label.isHidden()
        p.unlink(missing_ok=True)

    def test_placeholder_visible_when_cleared(self, composer):
        """Placeholder visible again after clearing."""
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
            p = Path(f.name)
        composer.set_media_paths([p])
        composer._clear_all_media()
        assert not composer._placeholder_label.isHidden()
        p.unlink(missing_ok=True)

    def test_format_restriction_notice_toggle(self, composer):
        composer.set_format_restriction_notice('\u26a0 Image attached')
        assert not composer._format_restriction_notice.isHidden()
        assert 'Image attached' in composer._format_restriction_notice.text()

        composer.set_format_restriction_notice('')
        assert composer._format_restriction_notice.isHidden()

    def test_count_restriction_notice_toggle(self, composer):
        composer.set_count_restriction_notice('\u26a0 4 attachments')
        assert not composer._count_restriction_notice.isHidden()
        assert 'attachments' in composer._count_restriction_notice.text()

        composer.set_count_restriction_notice('')
        assert composer._count_restriction_notice.isHidden()


class TestSnapchatLandscapeMode:
    def test_mode_visible_for_snapchat_single_image(self, composer):
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
            image = Path(f.name)

        composer.set_media_paths([image])
        composer.set_platform_state(selected=['snapchat_1'], enabled=['snapchat_1'])

        assert composer._snapchat_landscape_row is not None
        assert not composer._snapchat_landscape_row.isHidden()
        image.unlink(missing_ok=True)

    def test_mode_visible_for_snapchat_landscape_video(self, composer, monkeypatch):
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
            video = Path(f.name)

        monkeypatch.setattr(
            'src.core.video_processor.get_video_info',
            lambda _p: VideoInfo(
                width=1280,
                height=720,
                duration_seconds=10.0,
                codec='h264',
                file_size=1024,
                format_name='mp4',
            ),
        )

        composer.set_media_paths([video])
        composer.set_platform_state(selected=['snapchat_1'], enabled=['snapchat_1'])

        assert composer._snapchat_landscape_row is not None
        assert not composer._snapchat_landscape_row.isHidden()
        video.unlink(missing_ok=True)

    def test_mode_hidden_for_vertical_video(self, composer, monkeypatch):
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
            video = Path(f.name)

        monkeypatch.setattr(
            'src.core.video_processor.get_video_info',
            lambda _p: VideoInfo(
                width=720,
                height=1280,
                duration_seconds=10.0,
                codec='h264',
                file_size=1024,
                format_name='mp4',
            ),
        )

        composer.set_media_paths([video])
        composer.set_platform_state(selected=['snapchat_1'], enabled=['snapchat_1'])

        assert composer._snapchat_landscape_row is not None
        assert composer._snapchat_landscape_row.isHidden()
        video.unlink(missing_ok=True)

    def test_mode_changes_emit_signal(self, composer):
        seen = []
        composer.snapchat_landscape_mode_changed.connect(seen.append)

        composer.set_snapchat_landscape_mode('rotate')

        assert composer.get_snapchat_landscape_mode() == 'rotate'
        assert 'rotate' in seen

    def test_multi_image_mode_visible_for_snapchat_multiple_images(self, composer):
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f1:
            p1 = Path(f1.name)
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f2:
            p2 = Path(f2.name)

        composer.set_media_paths([p1, p2])
        composer.set_platform_state(selected=['snapchat_1'], enabled=['snapchat_1'])

        assert composer._snapchat_multi_image_row is not None
        assert not composer._snapchat_multi_image_row.isHidden()
        p1.unlink(missing_ok=True)
        p2.unlink(missing_ok=True)

    def test_multi_image_mode_changes_emit_signal(self, composer):
        seen = []
        composer.snapchat_multi_image_mode_changed.connect(seen.append)

        composer.set_snapchat_multi_image_mode('slideshow')

        assert composer.get_snapchat_multi_image_mode() == 'slideshow'
        assert 'slideshow' in seen
