"""Tests for PostComposer text warning and character counters."""

import pytest

from src.gui.post_composer import PostComposer


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
