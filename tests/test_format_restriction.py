"""Tests for media format platform restriction in PlatformSelector."""

import pytest

from src.gui.platform_selector import PlatformSelector
from src.utils import tokens
from src.utils.constants import AccountConfig


@pytest.fixture
def selector(qtbot):
    """Create a PlatformSelector with mixed format-support accounts."""
    sel = PlatformSelector()
    qtbot.addWidget(sel)
    accounts = [
        AccountConfig('twitter', 'twitter_1', 'user1'),
        AccountConfig('bluesky', 'bluesky_1', 'user2'),
        AccountConfig('meta_instagram', 'meta_instagram_1', 'user3'),
        AccountConfig('fetlife', 'fetlife_1', 'user4'),
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
        selector.set_selected(['twitter_1', 'bluesky_1', 'meta_instagram_1'])
        # GIF: only Twitter supports it
        selector.set_format_restriction({'bluesky_1', 'meta_instagram_1', 'fetlife_1'}, GIF_NOTICE)
        selected = selector.get_selected()
        assert 'twitter_1' in selected
        assert 'bluesky_1' not in selected
        assert 'meta_instagram_1' not in selected

    def test_restriction_prevents_checking(self, selector):
        """Restricted platforms cannot be checked by clicking."""
        selector.set_format_restriction({'bluesky_1'}, GIF_NOTICE)
        cb = selector._checkboxes['bluesky_1']
        cb.setChecked(True)
        selector._on_checkbox_clicked('bluesky_1')
        assert not cb.isChecked()

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
        name_label = selector._rows['bluesky_1'].name_label
        assert tokens.TEXT_MUTED in name_label.styleSheet()
        assert 'italic' in name_label.styleSheet()

    def test_empty_restriction_is_noop(self, selector):
        """Passing an empty set should not change selection."""
        selector.set_selected(['twitter_1', 'bluesky_1'])
        selector.set_format_restriction(set())
        selected = selector.get_selected()
        assert 'twitter_1' in selected
        assert 'bluesky_1' in selected

    def test_webp_restricts_bluesky_and_instagram(self, selector):
        """WEBP should restrict Bluesky/Instagram but not Twitter/FetLife."""
        selector.set_selected(['twitter_1', 'bluesky_1', 'meta_instagram_1', 'fetlife_1'])
        # Bluesky and Instagram don't support WEBP
        selector.set_format_restriction({'bluesky_1', 'meta_instagram_1'}, WEBP_NOTICE)
        selected = selector.get_selected()
        assert 'twitter_1' in selected
        assert 'fetlife_1' in selected
        assert 'bluesky_1' not in selected
        assert 'meta_instagram_1' not in selected


VIDEO_NOTICE = '\u26a0 Video attached \u2014 some platforms do not support this video format.'
IMAGE_ON_VIDEO_ONLY = '\u26a0 Image attached \u2014 this platform only supports video.'


@pytest.fixture
def selector_with_restricted(qtbot):
    """Create a PlatformSelector with a third account to restrict.

    The restriction sets are passed explicitly, so the platform is
    incidental — it only has to be one users can actually select.
    """
    sel = PlatformSelector()
    qtbot.addWidget(sel)
    accounts = [
        AccountConfig('twitter', 'twitter_1', 'user1'),
        AccountConfig('bluesky', 'bluesky_1', 'user2'),
        AccountConfig('fetlife', 'fetlife_1', 'user3'),
    ]
    sel.set_accounts(accounts)
    for a in accounts:
        sel.set_platform_enabled(a.account_id, True)
    return sel


class TestVideoFormatRestriction:
    def test_video_restricts_unsupported_platforms(self, selector_with_restricted):
        """Platforms that don't support the video format should be restricted."""
        sel = selector_with_restricted
        sel.set_selected(['twitter_1', 'bluesky_1', 'fetlife_1'])
        # Restrict bluesky (hypothetical unsupported video format)
        sel.set_format_restriction({'bluesky_1'}, VIDEO_NOTICE)
        selected = sel.get_selected()
        assert 'twitter_1' in selected
        assert 'fetlife_1' in selected
        assert 'bluesky_1' not in selected

    def test_image_restricts_video_only_platform(self, selector_with_restricted):
        """A video-only platform should be restricted when an image is attached."""
        sel = selector_with_restricted
        sel.set_selected(['twitter_1', 'fetlife_1'])
        sel.set_format_restriction({'fetlife_1'}, IMAGE_ON_VIDEO_ONLY)
        selected = sel.get_selected()
        assert 'twitter_1' in selected
        assert 'fetlife_1' not in selected

    def test_video_restriction_prevents_checking(self, selector_with_restricted):
        """Restricted platform cannot be checked."""
        sel = selector_with_restricted
        sel.set_format_restriction({'fetlife_1'}, VIDEO_NOTICE)
        cb = sel._checkboxes['fetlife_1']
        cb.setChecked(True)
        sel._on_checkbox_clicked('fetlife_1')
        assert not cb.isChecked()


COUNT_NOTICE = '\u26a0 3 attachments \u2014 some platforms support fewer attachments.'


class TestCountRestriction:
    def test_count_restricts_single_attachment_platforms(self, selector_with_restricted):
        """Platforms that only support 1 attachment should be restricted with 2+ files."""
        sel = selector_with_restricted
        sel.set_selected(['twitter_1', 'bluesky_1', 'fetlife_1'])
        # FetLife supports 1 attachment, Twitter/Bluesky support 4
        sel.set_count_restriction({'fetlife_1'}, COUNT_NOTICE)
        selected = sel.get_selected()
        assert 'twitter_1' in selected
        assert 'bluesky_1' in selected
        assert 'fetlife_1' not in selected

    def test_count_restriction_prevents_checking(self, selector_with_restricted):
        """Count-restricted platform cannot be checked."""
        sel = selector_with_restricted
        sel.set_count_restriction({'fetlife_1'}, COUNT_NOTICE)
        cb = sel._checkboxes['fetlife_1']
        cb.setChecked(True)
        sel._on_checkbox_clicked('fetlife_1')
        assert not cb.isChecked()

    def test_count_restriction_tooltip(self, selector_with_restricted):
        """Count-restricted platform shows tooltip."""
        sel = selector_with_restricted
        sel.set_count_restriction({'fetlife_1'}, COUNT_NOTICE)
        cb = sel._checkboxes['fetlife_1']
        assert 'attachments' in cb.toolTip().lower()

    def test_count_and_format_restriction_independent(self, selector_with_restricted):
        """Count and format restrictions can coexist."""
        sel = selector_with_restricted
        sel.set_selected(['twitter_1', 'bluesky_1', 'fetlife_1'])
        sel.set_format_restriction({'bluesky_1'}, VIDEO_NOTICE)
        sel.set_count_restriction({'fetlife_1'}, COUNT_NOTICE)
        selected = sel.get_selected()
        assert 'twitter_1' in selected
        assert 'bluesky_1' not in selected
        assert 'fetlife_1' not in selected


def test_unavailable_platform_is_not_selectable(qtbot):
    """A platform marked unavailable must not appear as a post target.

    Its specs stay resolvable so stored accounts and config still load, but a
    user must not be able to select it and queue a post that cannot succeed.
    """
    from src.utils.constants import PLATFORM_SPECS_MAP

    assert PLATFORM_SPECS_MAP['snapchat'].available is False, 'guard for this test'

    sel = PlatformSelector()
    qtbot.addWidget(sel)
    sel.set_accounts(
        [
            AccountConfig('twitter', 'twitter_1', 'user1'),
            AccountConfig('snapchat', 'snapchat_1', 'user2'),
        ]
    )
    assert 'twitter_1' in sel._checkboxes
    assert 'snapchat_1' not in sel._checkboxes

    sel.set_platform_enabled('twitter_1', True)
    sel.set_platform_enabled('snapchat_1', True)
    sel.set_selected(['twitter_1', 'snapchat_1'])
    assert sel.get_selected() == ['twitter_1']
