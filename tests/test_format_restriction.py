"""Tests for media format platform restriction in PlatformSelector."""

import pytest

from src.gui.platform_selector import PlatformSelector
from src.utils.constants import AccountConfig


@pytest.fixture
def selector(qtbot):
    """Create a PlatformSelector with mixed format-support accounts."""
    sel = PlatformSelector()
    qtbot.addWidget(sel)
    accounts = [
        AccountConfig('twitter', 'twitter_1', 'user1'),
        AccountConfig('bluesky', 'bluesky_1', 'user2'),
        AccountConfig('instagram', 'instagram_1', 'user3'),
        AccountConfig('onlyfans', 'onlyfans_1', 'user4'),
    ]
    sel.set_accounts(accounts)
    for a in accounts:
        sel.set_platform_enabled(a.account_id, True)
    return sel


GIF_NOTICE = '\u26a0 Animated GIF attached \u2014 only platforms that support GIFs are available.'
WEBP_NOTICE = '\u26a0 WEBP image attached \u2014 some platforms do not support this format.'


class TestFormatRestriction:
    def test_restriction_unchecks_unsupported_platforms(self, selector):
        """Platforms that don't support the format should be unchecked."""
        selector.set_selected(['twitter_1', 'bluesky_1', 'instagram_1'])
        # GIF: only Twitter supports it
        selector.set_format_restriction({'bluesky_1', 'instagram_1', 'onlyfans_1'}, GIF_NOTICE)
        selected = selector.get_selected()
        assert 'twitter_1' in selected
        assert 'bluesky_1' not in selected
        assert 'instagram_1' not in selected

    def test_restriction_prevents_checking(self, selector):
        """Restricted platforms cannot be checked by clicking."""
        selector.set_format_restriction({'bluesky_1'}, GIF_NOTICE)
        cb = selector._checkboxes['bluesky_1']
        cb.setChecked(True)
        selector._on_checkbox_clicked('bluesky_1')
        assert not cb.isChecked()

    def test_restriction_shows_notice(self, selector):
        """The format notice should be visible when restriction is active."""
        assert selector._format_notice.isHidden()
        selector.set_format_restriction({'bluesky_1'}, GIF_NOTICE)
        assert not selector._format_notice.isHidden()
        assert 'GIF' in selector._format_notice.text()

    def test_clearing_restriction_hides_notice(self, selector):
        """Clearing restriction should hide the notice."""
        selector.set_format_restriction({'bluesky_1'}, GIF_NOTICE)
        assert not selector._format_notice.isHidden()
        selector.set_format_restriction(set())
        assert selector._format_notice.isHidden()

    def test_restricted_platforms_have_tooltip(self, selector):
        """Restricted platforms should have an explanatory tooltip."""
        selector.set_format_restriction({'bluesky_1'}, GIF_NOTICE)
        cb = selector._checkboxes['bluesky_1']
        assert 'format' in cb.toolTip().lower()

    def test_unrestricted_platforms_no_tooltip(self, selector):
        """Unrestricted platforms should have no tooltip."""
        selector.set_format_restriction({'bluesky_1'}, GIF_NOTICE)
        cb = selector._checkboxes['twitter_1']
        assert cb.toolTip() == ''

    def test_clearing_restriction_clears_tooltip(self, selector):
        """Clearing restriction should remove the tooltip."""
        selector.set_format_restriction({'bluesky_1'}, GIF_NOTICE)
        selector.set_format_restriction(set())
        cb = selector._checkboxes['bluesky_1']
        assert cb.toolTip() == ''

    def test_restricted_platforms_styled_grey(self, selector):
        """Restricted platforms should be styled grey/italic."""
        selector.set_format_restriction({'bluesky_1'}, GIF_NOTICE)
        cb = selector._checkboxes['bluesky_1']
        assert '#888888' in cb.styleSheet()
        assert 'italic' in cb.styleSheet()

    def test_empty_restriction_is_noop(self, selector):
        """Passing an empty set should not change selection."""
        selector.set_selected(['twitter_1', 'bluesky_1'])
        selector.set_format_restriction(set())
        selected = selector.get_selected()
        assert 'twitter_1' in selected
        assert 'bluesky_1' in selected

    def test_webp_restricts_bluesky_and_instagram(self, selector):
        """WEBP should restrict Bluesky/Instagram/FetLife but not Twitter/OnlyFans/Fansly."""
        selector.set_selected(['twitter_1', 'bluesky_1', 'instagram_1', 'onlyfans_1'])
        # Bluesky and Instagram don't support WEBP
        selector.set_format_restriction({'bluesky_1', 'instagram_1'}, WEBP_NOTICE)
        selected = selector.get_selected()
        assert 'twitter_1' in selected
        assert 'onlyfans_1' in selected
        assert 'bluesky_1' not in selected
        assert 'instagram_1' not in selected

    def test_notice_text_changes_per_format(self, selector):
        """Notice text should reflect the specific format."""
        selector.set_format_restriction({'bluesky_1'}, GIF_NOTICE)
        assert 'GIF' in selector._format_notice.text()

        selector.set_format_restriction({'bluesky_1'}, WEBP_NOTICE)
        assert 'WEBP' in selector._format_notice.text()


VIDEO_NOTICE = '\u26a0 Video attached \u2014 some platforms do not support this video format.'
IMAGE_ON_VIDEO_ONLY = '\u26a0 Image attached \u2014 this platform only supports video.'


@pytest.fixture
def selector_with_snapchat(qtbot):
    """Create a PlatformSelector with Snapchat (video-only, no text)."""
    sel = PlatformSelector()
    qtbot.addWidget(sel)
    accounts = [
        AccountConfig('twitter', 'twitter_1', 'user1'),
        AccountConfig('bluesky', 'bluesky_1', 'user2'),
        AccountConfig('snapchat', 'snapchat_1', 'user3'),
    ]
    sel.set_accounts(accounts)
    for a in accounts:
        sel.set_platform_enabled(a.account_id, True)
    return sel


class TestVideoFormatRestriction:
    def test_video_restricts_unsupported_platforms(self, selector_with_snapchat):
        """Platforms that don't support the video format should be restricted."""
        sel = selector_with_snapchat
        sel.set_selected(['twitter_1', 'bluesky_1', 'snapchat_1'])
        # Restrict bluesky (hypothetical unsupported video format)
        sel.set_format_restriction({'bluesky_1'}, VIDEO_NOTICE)
        selected = sel.get_selected()
        assert 'twitter_1' in selected
        assert 'snapchat_1' in selected
        assert 'bluesky_1' not in selected

    def test_image_restricts_video_only_platform(self, selector_with_snapchat):
        """Snapchat (video-only) should be restricted when an image is attached."""
        sel = selector_with_snapchat
        sel.set_selected(['twitter_1', 'snapchat_1'])
        sel.set_format_restriction({'snapchat_1'}, IMAGE_ON_VIDEO_ONLY)
        selected = sel.get_selected()
        assert 'twitter_1' in selected
        assert 'snapchat_1' not in selected

    def test_video_restriction_shows_notice(self, selector_with_snapchat):
        """Video format restriction shows the notice label."""
        sel = selector_with_snapchat
        assert sel._format_notice.isHidden()
        sel.set_format_restriction({'bluesky_1'}, VIDEO_NOTICE)
        assert not sel._format_notice.isHidden()
        assert 'video' in sel._format_notice.text().lower()

    def test_image_on_video_only_notice(self, selector_with_snapchat):
        """Image restriction on video-only platform shows correct notice."""
        sel = selector_with_snapchat
        sel.set_format_restriction({'snapchat_1'}, IMAGE_ON_VIDEO_ONLY)
        assert not sel._format_notice.isHidden()
        assert 'video' in sel._format_notice.text().lower()

    def test_video_restriction_prevents_checking(self, selector_with_snapchat):
        """Restricted platform cannot be checked."""
        sel = selector_with_snapchat
        sel.set_format_restriction({'snapchat_1'}, VIDEO_NOTICE)
        cb = sel._checkboxes['snapchat_1']
        cb.setChecked(True)
        sel._on_checkbox_clicked('snapchat_1')
        assert not cb.isChecked()
