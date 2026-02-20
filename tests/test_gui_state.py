from src.gui.platform_selector import PlatformSelector
from src.gui.post_composer import PostComposer


def test_platform_selector_disables_checkboxes(qtbot):
    selector = PlatformSelector()
    qtbot.addWidget(selector)

    selector.set_platform_enabled('twitter', False)
    selector.set_platform_enabled('bluesky', True)
    selector.set_platform_enabled('bluesky_alt', True)

    assert 'twitter' not in selector.get_enabled()
    assert 'bluesky' in selector.get_enabled()
    assert 'bluesky_alt' in selector.get_enabled()
    assert 'twitter' not in selector.get_selected()

    selector.set_selected(['twitter', 'bluesky', 'bluesky_alt'])
    assert 'twitter' not in selector.get_selected()
    assert 'bluesky' in selector.get_selected()
    assert 'bluesky_alt' in selector.get_selected()


def test_post_composer_counters_and_attach_button(qtbot):
    composer = PostComposer()
    qtbot.addWidget(composer)
    composer.show()
    qtbot.waitExposed(composer)

    composer.set_platform_state([], ['twitter', 'bluesky'])
    assert not composer._choose_btn.isEnabled()
    assert not composer._preview_btn.isEnabled()
    assert not composer._tw_counter.isVisible()
    assert not composer._bs_counter.isVisible()

    composer.set_platform_state(['twitter'], ['twitter', 'bluesky'])
    assert composer._choose_btn.isEnabled()
    assert not composer._preview_btn.isEnabled()


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

    selector.set_platform_username('twitter', 'jasmeralia')
    selector.set_platform_username('bluesky', 'jasmeralia.bsky.social')
    selector.set_platform_username('bluesky_alt', 'alt.bsky.social')
    assert selector.get_platform_label('twitter') == 'Twitter (jasmeralia)'
    assert selector.get_platform_label('bluesky') == 'Bluesky (jasmeralia)'
    assert selector.get_platform_label('bluesky_alt') == 'Bluesky (alt)'

    selector.set_platform_username('twitter', '')
    selector.set_platform_username('bluesky', None)
    selector.set_platform_username('bluesky_alt', '')
    assert selector.get_platform_label('twitter') == 'Twitter'
    assert selector.get_platform_label('bluesky') == 'Bluesky'
    assert selector.get_platform_label('bluesky_alt') == 'Bluesky'


def test_preview_button_enabled_when_image_present(qtbot, tmp_path):
    composer = PostComposer()
    qtbot.addWidget(composer)

    composer.set_platform_state(['twitter'], ['twitter'])
    assert not composer._preview_btn.isEnabled()

    image_path = tmp_path / 'image.png'
    image_path.write_bytes(b'fake')
    composer.set_image_path(image_path)
    assert composer._preview_btn.isEnabled()
