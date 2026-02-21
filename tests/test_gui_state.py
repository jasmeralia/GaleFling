from src.gui.platform_selector import PlatformSelector
from src.gui.post_composer import PostComposer
from src.utils.constants import AccountConfig


def _sample_accounts():
    """Create sample accounts for testing."""
    return [
        AccountConfig(platform_id='twitter', account_id='twitter_1', profile_name='jasmeralia'),
        AccountConfig(
            platform_id='bluesky', account_id='bluesky_1', profile_name='jas.bsky.social'
        ),
        AccountConfig(
            platform_id='bluesky', account_id='bluesky_alt', profile_name='alt.bsky.social'
        ),
    ]


def test_platform_selector_disables_checkboxes(qtbot):
    selector = PlatformSelector()
    qtbot.addWidget(selector)
    selector.set_accounts(_sample_accounts())

    selector.set_platform_enabled('twitter_1', False)
    selector.set_platform_enabled('bluesky_1', True)
    selector.set_platform_enabled('bluesky_alt', True)

    assert 'twitter_1' not in selector.get_enabled()
    assert 'bluesky_1' in selector.get_enabled()
    assert 'bluesky_alt' in selector.get_enabled()
    assert 'twitter_1' not in selector.get_selected()

    selector.set_selected(['twitter_1', 'bluesky_1', 'bluesky_alt'])
    assert 'twitter_1' not in selector.get_selected()
    assert 'bluesky_1' in selector.get_selected()
    assert 'bluesky_alt' in selector.get_selected()


def test_post_composer_counters_and_attach_button(qtbot):
    composer = PostComposer()
    qtbot.addWidget(composer)
    composer.show()
    qtbot.waitExposed(composer)

    composer.set_account_platform_map(
        {
            'twitter_1': 'twitter',
            'bluesky_1': 'bluesky',
        }
    )

    composer.set_platform_state([], ['twitter_1', 'bluesky_1'])
    assert not composer._choose_btn.isEnabled()
    assert not composer._preview_btn.isEnabled()
    # No counters visible when nothing selected
    assert len(composer._counter_labels) == 0

    composer.set_platform_state(['twitter_1'], ['twitter_1', 'bluesky_1'])
    assert composer._choose_btn.isEnabled()
    assert not composer._preview_btn.isEnabled()
    # Twitter counter should be visible
    assert 'twitter' in composer._counter_labels


def test_theme_label_styles_follow_palette(qtbot):
    composer = PostComposer()
    selector = PlatformSelector()
    qtbot.addWidget(composer)
    qtbot.addWidget(selector)

    assert 'palette(text)' in composer._text_label.styleSheet()
    assert 'palette(text)' in composer._img_label.styleSheet()
    assert 'palette(text)' in selector._label.styleSheet()


def test_platform_selector_usernames(qtbot):
    selector = PlatformSelector()
    qtbot.addWidget(selector)
    selector.set_accounts(_sample_accounts())

    selector.set_platform_username('twitter_1', 'jasmeralia')
    selector.set_platform_username('bluesky_1', 'jasmeralia.bsky.social')
    selector.set_platform_username('bluesky_alt', 'alt.bsky.social')
    assert selector.get_platform_label('twitter_1') == 'Twitter (jasmeralia)'
    assert selector.get_platform_label('bluesky_1') == 'Bluesky (jasmeralia)'
    assert selector.get_platform_label('bluesky_alt') == 'Bluesky (alt)'

    # When username_override is empty, falls back to account profile_name
    selector.set_platform_username('twitter_1', '')
    selector.set_platform_username('bluesky_1', None)
    selector.set_platform_username('bluesky_alt', '')
    # Profile names from accounts are used as fallback
    assert selector.get_platform_label('twitter_1') == 'Twitter (jasmeralia)'
    assert selector.get_platform_label('bluesky_1') == 'Bluesky (jas)'
    assert selector.get_platform_label('bluesky_alt') == 'Bluesky (alt)'


def test_preview_button_enabled_when_image_present(qtbot, tmp_path):
    composer = PostComposer()
    qtbot.addWidget(composer)

    composer.set_platform_state(['twitter_1'], ['twitter_1'])
    assert not composer._preview_btn.isEnabled()

    image_path = tmp_path / 'image.png'
    image_path.write_bytes(b'fake')
    composer.set_image_path(image_path)
    assert composer._preview_btn.isEnabled()
